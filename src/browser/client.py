from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

from .config import BrowserConfig

logger = logging.getLogger(__name__)


class BrowserError(RuntimeError):
    pass


class BrowserConnectionError(BrowserError):
    pass


class BrowserClient:
    """One serial JSON-lines channel to a disposable Playwright worker."""

    def __init__(self, config: BrowserConfig) -> None:
        self.config = config
        self.process: asyncio.subprocess.Process | None = None
        self.lock = asyncio.Lock()

    async def _start(self) -> None:
        if self.process and self.process.returncode is None:
            return
        # Don't copy the voice agent's provider credentials into the browser worker.
        allowed = {
            "PATH",
            "SYSTEMROOT",
            "WINDIR",
            "TEMP",
            "TMP",
            "HOME",
            "USERPROFILE",
            "LOCALAPPDATA",
            "APPDATA",
            "DISPLAY",
            "WAYLAND_DISPLAY",
            "XDG_RUNTIME_DIR",
            "PLAYWRIGHT_BROWSERS_PATH",
            "LANG",
            "LD_LIBRARY_PATH",
        }
        env = {k: v for k, v in os.environ.items() if k.upper() in allowed}
        env["PYTHONIOENCODING"] = "utf-8"
        kwargs = (
            {"creationflags": subprocess.CREATE_NO_WINDOW}
            if os.name == "nt"
            else {"start_new_session": True}
        )
        self.process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-u",
            "-m",
            "browser.worker",
            cwd=str(Path(__file__).resolve().parents[1]),
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            limit=8 * 1024 * 1024,
            **kwargs,
        )
        await self._exchange("initialize", self.config.wire(), 45)

    async def _exchange(self, operation: str, payload: dict, timeout: float) -> dict:
        proc = self.process
        if not proc or not proc.stdin or not proc.stdout:
            raise BrowserError("The browser worker is not running.")
        request_id = uuid4().hex
        proc.stdin.write(
            (json.dumps({"id": request_id, "op": operation, **payload}) + "\n").encode()
        )
        await proc.stdin.drain()
        line = await asyncio.wait_for(proc.stdout.readline(), timeout)
        if not line:
            raise BrowserConnectionError(
                "Browser worker stopped. Reopen the browser; do not repeat an uncertain submission."
            )
        response = json.loads(line)
        if response.get("id") != request_id:
            raise BrowserConnectionError(
                "Browser worker protocol was interrupted. Reopen the browser."
            )
        if not response.get("ok"):
            if response.get("reset_required"):
                raise BrowserConnectionError(
                    response.get("error", "Browser must restart")
                )
            raise BrowserError(response.get("error", "Browser operation failed"))
        return response.get("result", {})

    async def request(self, operation: str, **payload: object) -> dict:
        async with self.lock:
            started = time.monotonic()
            try:
                await self._start()
                timeout = (
                    max(self.config.action_timeout, self.config.navigation_timeout) + 15
                )
                if (
                    operation == "execute"
                    and payload.get("command", {}).get("kind") == "script"
                ):
                    timeout = self.config.script_timeout + 15
                return await self._exchange(operation, payload, timeout)
            except BrowserConnectionError:
                await self._terminate()
                raise
            except asyncio.CancelledError:
                await self._terminate()
                raise
            except (TimeoutError, asyncio.TimeoutError):
                await self._terminate()
                raise BrowserError(
                    "Browser timed out and was stopped. Its last action may have completed; inspect before retrying."
                ) from None
            except (
                BrokenPipeError,
                ConnectionError,
                json.JSONDecodeError,
                ValueError,
            ) as exc:
                await self._terminate()
                raise BrowserError(
                    "Browser connection failed. Reopen and inspect the current state."
                ) from exc
            finally:
                logger.info(
                    "Browser operation %s finished in %.2fs",
                    operation,
                    time.monotonic() - started,
                )

    async def _terminate(self) -> None:
        proc, self.process = self.process, None
        if not proc:
            return
        if proc.returncode is None:
            if os.name == "nt":
                killer = await asyncio.create_subprocess_exec(
                    "taskkill",
                    "/PID",
                    str(proc.pid),
                    "/T",
                    "/F",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                await killer.wait()
            else:
                import signal

                with contextlib.suppress(ProcessLookupError):
                    os.killpg(proc.pid, signal.SIGKILL)
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
        await proc.wait()

    async def close(self) -> None:
        async with self.lock:
            if self.process and self.process.returncode is None:
                with contextlib.suppress(Exception):
                    await self._exchange("shutdown", {}, 5)
                    await asyncio.wait_for(self.process.wait(), 2)
            await self._terminate()
