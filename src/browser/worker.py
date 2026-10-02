"""Playwright worker. Stdin/stdout are private JSON-lines IPC, not a network API.

Approved Python runs with the local user's privileges. This process isolates
latency/failures from voice processing; it is deliberately NOT a sandbox.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import copy
import hashlib
import io
import json
import os
import sys
import textwrap
from collections import deque
from pathlib import Path
from uuid import uuid4

from .config import BrowserConfig


class ScriptExecutionError(RuntimeError):
    pass


class BoundedOutput(io.StringIO):
    def write(self, value: str) -> int:
        # An approved script can print, but output should not exhaust worker RAM.
        available = max(0, 2000 - self.tell())
        super().write(value[:available])
        return len(value)


class ProfileLock:
    def __init__(self, profile: Path) -> None:
        self.path = profile.with_name(profile.name + ".lock")
        self.file = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("a+b")
        try:
            self.file.seek(0)
            if not self.file.read(1):
                self.file.write(b"0")
                self.file.flush()
            self.file.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            self.file = None
            raise ValueError(
                "This browser profile is in use by another voice session."
            ) from None

    def release(self) -> None:
        if self.file:
            self.file.close()  # OS releases the lock, also after process death.
            self.file = None


def contained_file(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root.resolve()) or not candidate.is_file():
        raise ValueError(
            "Choose an existing file inside the configured upload directory."
        )
    return candidate


class BrowserRuntime:
    def __init__(self, config: BrowserConfig) -> None:
        self.config = config
        self.profile_lock = ProfileLock(config.profile_dir)
        self.playwright = None
        self.context = None
        self.pages: dict = {}
        self.frames: dict = {}
        self.dialogs: dict = {}
        self.artifacts: dict = {}
        self.active: str | None = None
        self.registry: dict = {}
        self.pending: dict = {}
        self.events: deque = deque(maxlen=100)
        self.tasks: set[asyncio.Task] = set()
        self.dialog_opened = asyncio.Event()

    def spawn(self, coroutine) -> None:
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.task_finished)

    def task_finished(self, task) -> None:
        self.tasks.discard(task)
        if not task.cancelled() and task.exception():
            self.events.append(
                {"kind": "background_error", "type": type(task.exception()).__name__}
            )

    def dialog_received(self, tab_id, dialog) -> None:
        self.dialogs[tab_id] = dialog
        self.dialog_opened.set()

    async def start(self) -> None:
        if self.context:
            return
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RuntimeError(
                "Playwright is not installed. Run uv sync, then uv run playwright install chromium in my-agent."
            ) from None

        self.profile_lock.acquire()
        try:
            for directory in (
                self.config.profile_dir,
                self.config.artifact_dir,
                self.config.upload_dir,
            ):
                directory.mkdir(parents=True, exist_ok=True)
            self.playwright = await async_playwright().start()
            engine = getattr(self.playwright, self.config.engine)
            self.context = await engine.launch_persistent_context(
                str(self.config.profile_dir),
                headless=self.config.headless,
                accept_downloads=True,
            )
            self.context.set_default_timeout(self.config.action_timeout * 1000)
            self.context.set_default_navigation_timeout(
                self.config.navigation_timeout * 1000
            )
            self.context.on("page", self.register_page)
            for page in self.context.pages:
                self.register_page(page)
            if not self.pages:
                self.register_page(await self.context.new_page())
        except BaseException:
            await self.close()
            raise

    def register_page(self, page) -> str:
        for tab_id, existing in self.pages.items():
            if existing is page:
                return tab_id
        tab_id = "tab_" + uuid4().hex[:10]
        self.pages[tab_id] = page
        self.active = tab_id
        page.on("dialog", lambda dialog: self.dialog_received(tab_id, dialog))
        page.on("download", lambda download: self.spawn(self.save_download(download)))
        page.on(
            "console",
            lambda msg: self.events.append(
                {
                    "tab_id": tab_id,
                    "kind": "console",
                    "level": msg.type,
                    "text": msg.text[:1000],
                }
            ),
        )
        page.on(
            "pageerror",
            lambda error: self.events.append(
                {"tab_id": tab_id, "kind": "pageerror", "text": str(error)[:1000]}
            ),
        )
        page.on(
            "response",
            lambda response: self.events.append(
                {
                    "tab_id": tab_id,
                    "kind": "response",
                    "url": response.url.split("?")[0],
                    "status": response.status,
                }
            ),
        )
        page.on(
            "requestfailed",
            lambda request: self.events.append(
                {
                    "tab_id": tab_id,
                    "kind": "requestfailed",
                    "url": request.url.split("?")[0],
                }
            ),
        )
        return tab_id

    def page(self, tab_id: str = ""):
        tab_id = tab_id or self.active
        page = self.pages.get(tab_id)
        if not page or page.is_closed():
            raise ValueError(
                "This tab is closed or missing. List tabs or open a new one."
            )
        return page

    def tab_id(self, page) -> str:
        return self.register_page(page)

    def scope(self, page, frame_id: str = ""):
        if not frame_id:
            return page
        frame = self.frames.get(frame_id)
        if not frame or frame.is_detached() or frame.page is not page:
            raise ValueError("Frame is missing or detached. Inspect frames again.")
        return frame

    def locator(self, page, target: dict):
        scope = self.scope(page, target.get("frame_id", ""))
        kind, value = target.get("kind", "role"), target.get("value", "")
        exact = target.get("exact", True)
        if kind == "role":
            return scope.get_by_role(
                value, name=target.get("name") or None, exact=exact
            )
        if kind == "label":
            return scope.get_by_label(value, exact=exact)
        if kind == "text":
            return scope.get_by_text(value, exact=exact)
        if kind == "css":
            return scope.locator(value)
        raise ValueError("Unknown locator kind")

    async def unique(self, page, target: dict):
        locator = self.locator(page, target)
        await locator.first.wait_for(state="attached")
        count = await locator.count()
        if count != 1:
            candidates = await locator.evaluate_all(
                "els => els.slice(0, 8).map(e => ({tag:e.tagName, text:(e.innerText || e.getAttribute('aria-label') || '').slice(0,120)}))"
            )
            raise ValueError(
                f"Locator matched {count} elements. Refine it using these candidates: {json.dumps(candidates)}"
            )
        return locator

    async def save_download(self, download) -> None:
        artifact_id = "download_" + uuid4().hex
        filename = (
            Path(download.suggested_filename.replace("\\", "/")).name or "download"
        )
        path = self.config.artifact_dir / f"{artifact_id}_{filename}"
        try:
            await download.save_as(path)
            self.artifacts[artifact_id] = {
                "id": artifact_id,
                "path": str(path),
                "name": filename,
                "kind": "download",
            }
        except Exception:
            self.events.append({"kind": "download_error", "id": artifact_id})

    async def snapshot(self, page) -> dict:
        tab_id = self.tab_id(page)
        result = {"tab_id": tab_id, "url": page.url}
        dialog = self.dialogs.get(tab_id)
        if dialog:
            result["dialog"] = {"type": dialog.type, "message": dialog.message[:1500]}
        else:
            result["title"] = await page.title()
        return result

    async def fingerprint(self, page) -> str:
        """Conservative review version: DOM, form properties, frames, and dialogs."""
        state = [await self.snapshot(page)]
        if self.tab_id(page) not in self.dialogs:
            for frame in page.frames:
                state.append(
                    await frame.evaluate("""() => ({url:location.href, dom:document.documentElement.outerHTML,
                    fields:Array.from(document.querySelectorAll('input,select,textarea')).map(e => [e.value,e.checked])})""")
                )
        return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()

    async def versions(self, command: dict) -> dict:
        if command["kind"] == "script":
            return {
                key: await self.fingerprint(page)
                for key, page in self.pages.items()
                if not page.is_closed()
            }
        page = self.page(command.get("tab_id", ""))
        return {self.tab_id(page): await self.fingerprint(page)}

    async def prepare(self, command: dict) -> dict:
        command = copy.deepcopy(command)
        page = self.page(command.get("tab_id", ""))
        command["tab_id"] = self.tab_id(page)
        target_handle = None
        if command["kind"] == "script":
            if not command.get("code", "").strip():
                raise ValueError("Script is empty")
            compile(
                "async def run():\n" + textwrap.indent(command["code"], "    "),
                "<approved-playwright>",
                "exec",
            )
        elif command.get("target"):
            target_handle = await (
                await self.unique(page, command["target"])
            ).element_handle()
        ticket = uuid4().hex
        self.pending = {
            ticket: {
                "command": command,
                "versions": await self.versions(command),
                "target": target_handle,
            }
        }
        return {
            "ticket": ticket,
            "kind": command["kind"],
            "page": await self.snapshot(page),
        }

    async def execute(self, ticket: str) -> dict:
        pending = self.pending.pop(ticket, None)
        if not pending:
            raise ValueError(
                "Prepared action is missing, invalidated, or already consumed."
            )
        command = pending["command"]
        if await self.versions(command) != pending["versions"]:
            raise ValueError(
                "The reviewed page changed. Inspect it and prepare a new review."
            )
        handle = pending["target"]
        if handle and not await handle.evaluate("e => e.isConnected"):
            raise ValueError("The reviewed element was replaced. Prepare a new review.")
        if command["kind"] == "script":
            return await self.run_script(command)
        return await self.act(command, reviewed_handle=handle)

    async def run_script(self, command: dict) -> dict:
        page = self.page(command["tab_id"])
        namespace = {
            "playwright": self.playwright,
            "context": page.context,
            "page": page,
            "browser": page.context.browser,
            "registry": self.registry,
            "artifact_dir": self.config.artifact_dir,
            "asyncio": asyncio,
            "register_page": self.register_page,
            "register_artifact": self.register_artifact,
        }
        source = "async def run():\n" + textwrap.indent(command["code"], "    ")
        exec(compile(source, "<approved-playwright>", "exec"), namespace)
        before = asyncio.all_tasks()
        # Prevent an ordinary print() from corrupting the IPC stream.
        output = BoundedOutput()
        try:
            with contextlib.redirect_stdout(output):
                result = await asyncio.wait_for(
                    namespace["run"](), self.config.script_timeout
                )
        except Exception as exc:
            raise ScriptExecutionError(
                f"Script failed ({type(exc).__name__}). Browser stopped; some effects may have occurred. Inspect before retrying. {str(exc)[:500]}"
            ) from None
        finally:
            for task in asyncio.all_tasks() - before:
                self.tasks.add(task)
                task.add_done_callback(self.task_finished)
        for candidate in self.context.pages:
            self.register_page(candidate)
        try:
            encoded = json.dumps(result)
        except (TypeError, ValueError):
            encoded = json.dumps(
                {
                    "type": type(result).__name__,
                    "hint": "Store Playwright objects in registry; return JSON-compatible values.",
                }
            )
        return {
            "status": "executed",
            "result": encoded[:12000],
            "truncated": len(encoded) > 12000,
            "output": output.getvalue()[:2000],
        }

    def register_artifact(self, path, kind="file") -> dict:
        path = contained_file(self.config.artifact_dir, str(path))
        artifact_id = "artifact_" + uuid4().hex
        artifact = {
            "id": artifact_id,
            "path": str(path),
            "name": path.name,
            "kind": kind,
        }
        self.artifacts[artifact_id] = artifact
        return artifact

    async def act(self, command: dict, reviewed_handle=None) -> dict:
        page = self.page(command.get("tab_id", ""))
        if self.tab_id(page) in self.dialogs and command["action"] != "dialog":
            raise ValueError("Handle the pending browser dialog first.")
        self.dialog_opened.clear()
        task = asyncio.create_task(self.perform_action(command, reviewed_handle))
        waiter = asyncio.create_task(self.dialog_opened.wait())
        self.tasks.add(task)
        task.add_done_callback(self.task_finished)
        try:
            done, _ = await asyncio.wait(
                [task, waiter], return_when=asyncio.FIRST_COMPLETED
            )
            if task in done:
                return await task
            # Playwright clicks can wait for a dialog to close. Release IPC so the
            # next voice turn can inspect/approve/dismiss it without deadlocking.
            return {"status": "dialog_pending", "page": await self.snapshot(page)}
        finally:
            waiter.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await waiter

    async def perform_action(self, command: dict, reviewed_handle=None) -> dict:
        page = self.page(command.get("tab_id", ""))
        action = command["action"]
        target = command.get("target")
        value = command.get("value", "")
        locator = reviewed_handle or (
            await self.unique(page, target) if target else None
        )
        if (
            action
            in {
                "click",
                "open_popup",
                "double_click",
                "hover",
                "fill",
                "type",
                "select",
                "check",
                "uncheck",
                "drag",
                "upload",
                "choose_files",
            }
            and locator is None
        ):
            raise ValueError("This action requires a target locator")
        if action == "click":
            await locator.click(no_wait_after=True)
        elif action == "open_popup":
            async with page.expect_popup() as popup:
                await locator.click(no_wait_after=True)
            page = await popup.value
            self.register_page(page)
            await page.wait_for_load_state("domcontentloaded")
        elif action == "double_click":
            await locator.dblclick(no_wait_after=True)
        elif action == "hover":
            await locator.hover()
        elif action == "fill":
            await locator.fill(value)
        elif action == "type":
            if reviewed_handle:
                await locator.type(value)
            else:
                await locator.press_sequentially(value)
        elif action == "select":
            await locator.select_option(label=value)
        elif action == "check":
            await locator.check()
        elif action == "uncheck":
            await locator.uncheck()
        elif action == "press":
            await (locator.press(value) if locator else page.keyboard.press(value))
        elif action == "scroll":
            await page.mouse.wheel(0, int(value or "600"))
        elif action == "drag":
            destination = await self.unique(page, command["destination"])
            if reviewed_handle:
                await reviewed_handle.scroll_into_view_if_needed()
                source_box = await reviewed_handle.bounding_box()
                await destination.scroll_into_view_if_needed()
                destination_box = await destination.bounding_box()
                if not source_box or not destination_box:
                    raise ValueError("Drag target is no longer visible")
                await page.mouse.move(
                    source_box["x"] + source_box["width"] / 2,
                    source_box["y"] + source_box["height"] / 2,
                )
                await page.mouse.down()
                try:
                    await page.mouse.move(
                        destination_box["x"] + destination_box["width"] / 2,
                        destination_box["y"] + destination_box["height"] / 2,
                        steps=10,
                    )
                finally:
                    await page.mouse.up()
            else:
                await locator.drag_to(destination)
        elif action in {"upload", "choose_files"}:
            files = [
                str(contained_file(self.config.upload_dir, name))
                for name in command.get("files", [])
            ]
            if not files:
                raise ValueError("Choose at least one upload file")
            if action == "upload":
                await locator.set_input_files(files)
            else:
                async with page.expect_file_chooser() as chooser:
                    await locator.click()
                await (await chooser.value).set_files(files)
        elif action == "dialog":
            dialog = self.dialogs.pop(self.tab_id(page), None)
            if not dialog:
                raise ValueError("There is no pending dialog")
            if value == "dismiss":
                await dialog.dismiss()
            else:
                await dialog.accept(command.get("prompt_text", ""))
        else:
            raise ValueError("Unknown browser action")
        return {
            "status": "executed",
            "page": await self.snapshot(page),
            "verify": "Inspect the resulting page before claiming the task succeeded.",
        }

    async def observe(self, args: dict) -> dict:
        page = self.page(args.get("tab_id", ""))
        mode = args.get("mode", "structure")
        result = {"page": await self.snapshot(page)}
        if "dialog" in result["page"]:
            return result
        scope = self.scope(page, args.get("frame_id", ""))
        if mode == "frames":
            frames = []
            for frame in page.frames:
                frame_id = next(
                    (key for key, value in self.frames.items() if value is frame), None
                )
                if not frame_id:
                    frame_id = "frame_" + uuid4().hex[:10]
                    self.frames[frame_id] = frame
                frames.append(
                    {"frame_id": frame_id, "name": frame.name, "url": frame.url}
                )
            result["frames"] = frames
        elif mode == "screenshot":
            artifact_id = "screenshot_" + uuid4().hex
            path = self.config.artifact_dir / (artifact_id + ".png")
            data = await page.screenshot(path=str(path), full_page=False)
            artifact = {"id": artifact_id, "path": str(path), "kind": "screenshot"}
            self.artifacts[artifact_id] = artifact
            result.update(
                {
                    "artifact": artifact,
                    "image": "data:image/png;base64," + base64.b64encode(data).decode(),
                }
            )
        else:
            target = args.get("target")
            locator = self.locator(page, target) if target else scope.locator("body")
            if mode == "query":
                result["count"] = await locator.count()
                content = json.dumps(
                    await locator.evaluate_all(
                        "els => els.slice(0,50).map(e => ({tag:e.tagName, text:(e.innerText || '').slice(0,300), label:e.getAttribute('aria-label')}))"
                    )
                )
            elif mode == "text":
                content = await locator.inner_text()
            else:
                content = await locator.aria_snapshot()
            offset = max(0, int(args.get("offset", 0)))
            result.update(
                {
                    "content": content[offset : offset + 12000],
                    "offset": offset,
                    "next_offset": offset + 12000
                    if len(content) > offset + 12000
                    else None,
                }
            )
        return result

    async def dispatch(self, operation: str, args: dict) -> dict:
        if operation == "shutdown":
            await self.close()
            return {"status": "closed"}
        await self.start()
        if operation == "prepare":
            return await self.prepare(args["command"])
        if operation == "execute":
            return await self.execute(args["command"]["ticket"])
        if operation == "cancel":
            self.pending.clear()
            return {"status": "cancelled"}
        if operation == "act":
            self.pending.clear()
            return await self.act(args["command"])
        if operation == "observe":
            return await self.observe(args)
        if operation == "tabs":
            action = args.get("action", "list")
            if action != "list":
                self.pending.clear()
            if action == "open":
                page = await self.context.new_page()
                self.active = self.register_page(page)
                if args.get("url"):
                    navigation = await self.navigate(page, "goto", args["url"])
                    if navigation["status"] != "loaded":
                        return navigation
            elif action == "switch":
                page = self.page(args.get("tab_id", ""))
                self.active = self.tab_id(page)
                await page.bring_to_front()
            elif action == "close":
                await self.page(args.get("tab_id", "")).close()
                self.active = next(
                    (key for key, page in self.pages.items() if not page.is_closed()),
                    None,
                )
            elif action != "list":
                raise ValueError("Unknown tab action")
            return {
                "active_tab": self.active,
                "tabs": [
                    await self.snapshot(p)
                    for p in self.pages.values()
                    if not p.is_closed()
                ],
            }
        if operation == "navigate":
            self.pending.clear()
            page = self.page(args.get("tab_id", ""))
            return await self.navigate(
                page, args.get("action", "goto"), args.get("url", "")
            )
        if operation == "wait":
            page = self.page(args.get("tab_id", ""))
            if args.get("target"):
                await self.locator(page, args["target"]).wait_for(
                    state=args.get("state", "visible")
                )
            elif args.get("url"):
                await page.wait_for_url(args["url"], wait_until="domcontentloaded")
            else:
                await page.wait_for_load_state("domcontentloaded")
            return await self.snapshot(page)
        if operation == "diagnostics":
            return {
                "events": list(self.events)[-30:],
                "artifacts": list(self.artifacts.values())[-30:],
                "registry_keys": list(self.registry)[:50],
            }
        if operation == "fixture_state":
            return {"name": await self.page().locator("#name").input_value()}
        raise ValueError("Unknown browser operation")

    async def navigate(self, page, action: str, url: str) -> dict:
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError

        try:
            if action == "goto":
                response = await page.goto(url, wait_until="domcontentloaded")
            elif action in {"back", "forward", "reload"}:
                response = await {
                    "back": page.go_back,
                    "forward": page.go_forward,
                    "reload": page.reload,
                }[action](wait_until="domcontentloaded")
            else:
                raise ValueError("Unknown navigation action")
        except PlaywrightTimeoutError:
            # A page-load timeout does not undo navigation: it may still finish.
            # Don't convert that into a false claim that the site couldn't open.
            return {
                "status": "navigation_unconfirmed",
                "tab_id": self.tab_id(page),
                "url": page.url,
                "requested_url": url,
                "instruction": "Navigation did not finish within the wait limit. The page may still be loading. Inspect or wait; do not claim it failed or cannot be opened, and do not repeat navigation automatically.",
            }
        return {
            "status": "loaded",
            **await self.snapshot(page),
            "http_status": response.status if response else None,
        }

    async def close(self) -> None:
        tasks = list(self.tasks)
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        try:
            if self.context:
                with contextlib.suppress(Exception):
                    await self.context.close()
            if self.playwright:
                with contextlib.suppress(Exception):
                    await self.playwright.stop()
        finally:
            self.context = self.playwright = None
            self.profile_lock.release()


async def main() -> None:
    runtime = None
    protocol_out = sys.stdout
    # Background callbacks may print after the script returns. Never let their
    # output enter the protocol; only explicit protocol_out writes go to IPC.
    sys.stdout = sys.stderr
    try:
        while line := await asyncio.to_thread(sys.stdin.readline):
            request = json.loads(line)
            shutdown = request["op"] == "shutdown"
            try:
                if request["op"] == "initialize":
                    config = {
                        key: value
                        for key, value in request.items()
                        if key not in {"id", "op"}
                    }
                    for key in ("profile_dir", "artifact_dir", "upload_dir"):
                        config[key] = Path(config[key])
                    runtime = BrowserRuntime(BrowserConfig(**config))
                    result = {"status": "ready"}
                elif runtime:
                    result = await runtime.dispatch(request["op"], request)
                else:
                    raise ValueError("Worker is not initialized")
                response = {"id": request["id"], "ok": True, "result": result}
            except Exception as exc:
                # No environment, code, or stack traces in model-facing diagnostics.
                response = {
                    "id": request["id"],
                    "ok": False,
                    "error": f"{type(exc).__name__}: {str(exc)[:1500]}",
                    "reset_required": isinstance(
                        exc, (TimeoutError, asyncio.TimeoutError, ScriptExecutionError)
                    ),
                }
            protocol_out.write(json.dumps(response) + "\n")
            protocol_out.flush()
            if shutdown:
                break
    finally:
        if runtime:
            await runtime.close()


if __name__ == "__main__":
    asyncio.run(main())
