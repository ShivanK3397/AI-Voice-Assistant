"""Local Electron-owned runner with a JSON-lines lifecycle channel."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import threading
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def lifecycle(event: str, **payload):
    print(json.dumps({"version": 1, "type": event, **payload}), flush=True)


def preflight():
    load_dotenv(ROOT / ".env.local")
    missing = [
        name
        for name in (
            "LIVEKIT_URL",
            "LIVEKIT_API_KEY",
            "LIVEKIT_API_SECRET",
            "GOOGLE_API_KEY",
        )
        if not os.environ.get(name)
    ]
    if missing:
        raise ValueError("Set " + ", ".join(missing) + " in my-agent/.env.local.")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        engine = os.getenv("BROWSER_ENGINE", "chromium")
        if engine not in {"chromium", "firefox", "webkit"}:
            raise ValueError("Invalid BROWSER_ENGINE.")
        if not Path(getattr(playwright, engine).executable_path).exists():
            raise ValueError(
                f"Browser missing. Run: uv run playwright install {engine}"
            )
    for key, default in {
        "BROWSER_PROFILE_DIR": ".browser/profile",
        "BROWSER_ARTIFACT_DIR": ".browser/artifacts",
        "BROWSER_UPLOAD_DIR": ".browser/uploads",
    }.items():
        configured = Path(os.getenv(key, default))
        os.environ[key] = str((ROOT / configured).resolve())


async def run():
    from agent import create_desktop_server

    server = create_desktop_server()
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()

    def read_commands():
        for line in sys.stdin:
            try:
                if json.loads(line).get("type") == "shutdown":
                    break
            except (ValueError, AttributeError):
                loop.call_soon_threadsafe(lifecycle, "protocol.error")
        loop.call_soon_threadsafe(stop.set)

    threading.Thread(target=read_commands, daemon=True).start()
    server.on("worker_registered", lambda *_: lifecycle("worker.ready"))
    task = asyncio.create_task(server.run(devmode=True))
    stopped = asyncio.create_task(stop.wait())
    try:
        await asyncio.wait([task, stopped], return_when=asyncio.FIRST_COMPLETED)
    finally:
        await server.aclose()
        stopped.cancel()
        await asyncio.gather(stopped, return_exceptions=True)
    await task
    lifecycle("worker.stopped")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    try:
        preflight()
        if "--check" in sys.argv:
            lifecycle("preflight.ok")
        else:
            asyncio.run(run())
    except Exception as exc:
        # Preserve actionable startup errors without exposing provider credentials.
        message = str(exc)
        for name in ("LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "GOOGLE_API_KEY"):
            if value := os.environ.get(name):
                message = message.replace(value, "[redacted]")
        message = f"{type(exc).__name__}: {message}"[:1000]
        logging.getLogger("desktop").error("Agent startup failed: %s", message)
        lifecycle("worker.error", message=message)
        sys.exit(1)
