import asyncio
from dataclasses import replace

import pytest
import pytest_asyncio

from browser.client import BrowserClient, BrowserError
from browser.config import BrowserConfig
from browser.practice import BrowserPractice
from browser.worker import ProfileLock, contained_file


def test_upload_paths_cannot_escape_root(tmp_path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "ok.txt").write_text("allowed")
    (tmp_path / "secret.txt").write_text("not allowed")
    assert contained_file(uploads, "ok.txt") == uploads / "ok.txt"
    with pytest.raises(ValueError):
        contained_file(uploads, "../secret.txt")
    with pytest.raises(ValueError):
        contained_file(uploads, str(tmp_path / "secret.txt"))


def test_profile_lock_excludes_another_session_and_releases(tmp_path):
    first, second = ProfileLock(tmp_path / "profile"), ProfileLock(tmp_path / "profile")
    first.acquire()
    try:
        with pytest.raises(ValueError, match="another voice session"):
            second.acquire()
    finally:
        first.release()
    second.acquire()
    second.release()


def test_configuration_rejects_invalid_engine_or_unbounded_timeout():
    with pytest.raises(ValueError):
        BrowserConfig(engine="chrome")
    with pytest.raises(ValueError):
        BrowserConfig(script_timeout=0)


async def test_practice_server_records_actual_submission():
    site = BrowserPractice()
    try:
        await site.start()
        port = site.server.sockets[0].getsockname()[1]
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        body = b'{"name":"Alex"}'
        writer.write(
            f"POST /order HTTP/1.1\r\nHost: localhost\r\nContent-Length: {len(body)}\r\n\r\n".encode()
            + body
        )
        await writer.drain()
        response = await reader.read()
        writer.close()
        await writer.wait_closed()
        assert b"Order placed" in response
        assert site.orders == [{"name": "Alex"}]
    finally:
        await site.close()


@pytest_asyncio.fixture
async def browser():
    pytest.importorskip(
        "playwright.async_api",
        reason="Install Playwright and Chromium to run browser integration tests",
    )
    practice = BrowserPractice()
    await practice.start()
    client = BrowserClient(practice.config)
    try:
        await client.request("tabs", action="list")
        await client.request("navigate", url=practice.url)
        yield client, practice
    finally:
        await client.close()
        await practice.close()


async def script(client, code):
    prepared = await client.request("prepare", command={"kind": "script", "code": code})
    return await client.request("execute", command=prepared)


@pytest.mark.browser
async def test_function_only_script_is_rejected_before_review(browser):
    client, _ = browser
    with pytest.raises(BrowserError, match="only defines functions"):
        await client.request(
            "prepare",
            command={
                "kind": "script",
                "code": "async def script(page):\n    await page.fill('#name', 'hoodies')",
            },
        )
    assert await script(client, "return await page.title()")


@pytest.mark.browser
async def test_product_links_can_be_disambiguated_by_observed_destination(browser):
    import json

    client, _ = browser
    await script(
        client,
        """await page.set_content('''
        <article data-asin="xm4"><a href="#xm4">Sony headphones</a>WH-1000XM4</article>
        <article data-asin="xm5"><a href="#xm5">Sony headphones</a>WH-1000XM5 Black</article>
        ''')
return {}""",
    )
    target = {"kind": "role", "value": "link", "name": "Sony headphones"}
    observed = await client.request("observe", mode="query", target=target)
    matches = json.loads(observed["content"])
    assert matches[1]["href"] == "#xm5"
    assert "WH-1000XM5 Black" in matches[1]["context"]
    assert matches[1]["index"] == 1
    with pytest.raises(BrowserError, match="matched 2"):
        await client.request("act", command={"action": "click", "target": target})
    selected = {**target, "href": matches[1]["href"]}
    await client.request("act", command={"action": "click", "target": selected})
    state = await client.request("tabs", action="list")
    assert "#xm5" in str(state)


@pytest.mark.browser
async def test_query_exposes_all_controls_and_explicit_match_index(browser):
    import json

    client, _ = browser
    await script(
        client,
        """await page.set_content('<a href="#one">Item</a><a href="#two">Item</a>')
return {}""",
    )
    observed = await client.request("observe", mode="query")
    assert len(json.loads(observed["content"])) == 2
    await client.request(
        "act",
        command={
            "action": "click",
            "target": {"kind": "role", "value": "link", "name": "Item", "index": 1},
        },
    )
    state = await client.request("tabs", action="list")
    assert "#two" in str(state)


@pytest.mark.browser
async def test_prepare_does_not_submit_and_execute_is_single_use(browser):
    client, site = browser
    await client.request(
        "act",
        command={
            "kind": "action",
            "action": "fill",
            "target": {"kind": "label", "value": "Name"},
            "value": "Alex",
        },
    )
    pending = await client.request(
        "prepare",
        command={
            "kind": "action",
            "action": "click",
            "target": {"kind": "role", "value": "button", "name": "Place order"},
        },
    )
    assert site.orders == []
    await client.request("execute", command=pending)
    await client.request("wait", target={"kind": "text", "value": "Order placed"})
    assert site.orders == [{"name": "Alex"}]
    with pytest.raises(BrowserError, match="already consumed"):
        await client.request("execute", command=pending)
    assert len(site.orders) == 1


@pytest.mark.browser
async def test_manual_edit_invalidates_review(browser):
    client, site = browser
    # Schedule a manual-style DOM edit independent of subsequent tool calls.
    await script(
        client,
        "await page.evaluate(\"setTimeout(() => document.querySelector('#name').value = 'Changed', 1200)\")",
    )
    pending = await client.request(
        "prepare",
        command={
            "kind": "action",
            "action": "click",
            "target": {"kind": "role", "value": "button", "name": "Place order"},
        },
    )
    await asyncio.sleep(1.5)
    with pytest.raises(BrowserError, match="page changed"):
        await client.request("execute", command=pending)
    assert site.orders == []


@pytest.mark.browser
async def test_frames_popup_images_files_and_dialogs(browser):
    client, site = browser
    frames = (await client.request("observe", mode="frames"))["frames"]
    frame = next(frame for frame in frames if frame["url"].endswith("/frame"))
    await client.request(
        "act",
        command={
            "action": "fill",
            "target": {
                "kind": "label",
                "value": "Frame name",
                "frame_id": frame["frame_id"],
            },
            "value": "Frame works",
        },
    )
    (site.config.upload_dir / "sample.txt").write_text("sample")
    await client.request(
        "act",
        command={
            "action": "upload",
            "target": {"kind": "label", "value": "Attachment"},
            "files": ["sample.txt"],
        },
    )
    screenshot = await client.request("observe", mode="screenshot")
    assert screenshot["image"].startswith("data:image/png;base64,")
    await client.request(
        "act",
        command={
            "action": "click",
            "target": {"kind": "text", "value": "Download sample"},
        },
    )
    for _ in range(20):
        artifacts = (await client.request("diagnostics"))["artifacts"]
        if any(a["kind"] == "download" for a in artifacts):
            break
        await asyncio.sleep(0.1)
    assert any(a["kind"] == "download" for a in artifacts)
    original = (await client.request("tabs"))["active_tab"]
    await client.request(
        "act",
        command={
            "action": "open_popup",
            "target": {"kind": "role", "value": "button", "name": "Open popup"},
        },
    )
    tabs = (await client.request("tabs"))["tabs"]
    assert len(tabs) == 2
    await client.request("tabs", action="switch", tab_id=original)
    await client.request(
        "act",
        command={
            "action": "click",
            "target": {"kind": "role", "value": "button", "name": "Show dialog"},
        },
    )
    assert (await client.request("observe"))["page"]["dialog"][
        "message"
    ] == "Practice dialog"
    await client.request("act", command={"action": "dialog", "value": "dismiss"})


@pytest.mark.browser
async def test_full_api_registry_network_and_persistent_logins(browser):
    client, _site = browser
    result = await script(
        client,
        """registry['marker'] = 'kept'
await context.add_cookies([{'name':'login-test','value':'remembered','url':page.url,'expires':2000000000}])
await page.route('**/api-test', lambda route: route.fulfill(json={'value':42}))
return await page.evaluate("fetch('/api-test').then(r => r.json())")""",
    )
    assert "42" in result["result"]
    result = await script(client, "return registry['marker']")
    assert "kept" in result["result"]
    await client.close()
    await client.request("tabs")
    result = await script(client, "return await context.cookies()")
    assert "remembered" in result["result"]


@pytest.mark.browser
async def test_bad_locator_and_closed_tab_are_actionable(browser):
    client, _ = browser
    with pytest.raises(BrowserError, match="matched"):
        await client.request(
            "act",
            command={"action": "click", "target": {"kind": "role", "value": "button"}},
        )
    await client.request("tabs", action="close")
    with pytest.raises(BrowserError, match="closed or missing"):
        await client.request("observe")
    assert (await client.request("tabs", action="open"))["tabs"]


@pytest.mark.browser
async def test_script_timeout_stops_worker_and_releases_profile(browser):
    client, site = browser
    client.config = replace(site.config, script_timeout=0.2)
    await client.close()
    await client.request("tabs")
    with pytest.raises(BrowserError):
        await script(client, "await asyncio.sleep(10)")
    await client.close()
    replacement = BrowserClient(site.config)
    try:
        assert (await replacement.request("tabs"))["tabs"]
    finally:
        await replacement.close()
