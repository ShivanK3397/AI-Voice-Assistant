"""Isolated, deterministic practice site for simulations and browser tests."""

from __future__ import annotations

import asyncio
import contextlib
import json
import tempfile
from pathlib import Path

from .config import BrowserConfig

PAGE = """<!doctype html><html><head><title>Browser Practice</title></head><body>
<h1>Notebook</h1><p>Price: $20</p>
<form id="order"><label>Name <input id="name" name="name"></label>
<button type="submit">Place order</button></form><p id="result">No order placed</p>
<button onclick="window.open('/popup')">Open popup</button>
<button onclick="alert('Practice dialog')">Show dialog</button>
<button onclick="document.querySelector('#delayed').hidden=false">Show details</button>
<p id="delayed" hidden>Ready for inspection</p>
<label>Attachment <input id="upload" type="file"></label>
<a href="/download" download="practice.txt">Download sample</a>
<iframe title="Practice frame" src="/frame"></iframe>
<script>
document.querySelector('#order').addEventListener('submit',async e=>{
 e.preventDefault(); const name=document.querySelector('#name').value;
 const r=await fetch('/order',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})});
 document.querySelector('#result').textContent=await r.text();
});
</script></body></html>"""


class BrowserPractice:
    def __init__(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="my-agent-browser-")
        root = Path(self.temp.name)
        self.config = BrowserConfig(
            headless=True,
            profile_dir=root / "profile",
            artifact_dir=root / "artifacts",
            upload_dir=root / "uploads",
        )
        self.server: asyncio.Server | None = None
        self.orders: list[dict] = []
        self.url = ""

    async def start(self) -> str:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.url = f"http://127.0.0.1:{self.server.sockets[0].getsockname()[1]}/"
        return self.url

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            headers = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
            lines = headers.decode().split("\r\n")
            method, path, _ = lines[0].split(" ")
            fields = dict(line.split(": ", 1) for line in lines[1:] if ": " in line)
            length = int(
                next(
                    (v for k, v in fields.items() if k.lower() == "content-length"), "0"
                )
            )
            content = await reader.readexactly(length) if length else b""
            extra = ""
            if path == "/slow":
                await asyncio.sleep(5)
                body = PAGE.encode()
            elif path == "/order" and method == "POST":
                self.orders.append(json.loads(content))
                body = b"Order placed"
            elif path == "/frame":
                body = b"<html><body><label>Frame name <input></label></body></html>"
            elif path == "/popup":
                body = b"<html><title>Popup</title><body>Popup opened</body></html>"
            elif path == "/download":
                body = b"Practice download"
                extra = 'Content-Disposition: attachment; filename="practice.txt"\r\n'
            else:
                body = PAGE.encode()
            writer.write(
                (
                    f"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: {len(body)}\r\n{extra}Connection: close\r\n\r\n"
                ).encode()
                + body
            )
            await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError, TimeoutError, ValueError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    async def grade(self, sim, client) -> None:
        expected = sim.userdata()
        if len(self.orders) != expected.get("expected_orders", 0):
            sim.fail(
                f"Expected {expected.get('expected_orders', 0)} orders; received {len(self.orders)}"
            )
        try:
            if name := expected.get("expected_name"):
                # Fixed evaluator-owned read, never exposed as an unapproved script tool.
                result = await client.request("fixture_state")
                if result["name"] != name:
                    sim.fail("The practice name does not match the requested name")
                if any(order.get("name") != name for order in self.orders):
                    sim.fail("An order was submitted for the wrong name")
            if title := expected.get("expected_title"):
                result = await client.request("observe", mode="text")
                if result["page"].get("title") != title:
                    sim.fail("The requested page title was not set")
        except Exception as exc:
            sim.fail(f"Browser final-state inspection failed: {type(exc).__name__}")

    async def close(self) -> None:
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        # Windows may still be releasing browser files during parallel shutdown hooks.
        with contextlib.suppress(PermissionError):
            self.temp.cleanup()
