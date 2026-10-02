from unittest.mock import AsyncMock

import pytest

from browser.config import BrowserConfig
from browser.worker import BrowserRuntime


async def test_page_load_timeout_is_unconfirmed_not_failed():
    playwright = pytest.importorskip("playwright.async_api")
    page = AsyncMock()
    page.goto.side_effect = playwright.TimeoutError("Timed out waiting for DOM content")
    page.url = "https://www.youtube.com/"
    runtime = BrowserRuntime(BrowserConfig())
    runtime.pages["tab_test"] = page
    result = await runtime.navigate(page, "goto", page.url)
    assert result["status"] == "navigation_unconfirmed"
    assert result["url"] == page.url
    assert result["requested_url"] == page.url
    page.goto.assert_awaited_once()


async def test_actual_navigation_error_is_not_reported_as_loaded():
    playwright = pytest.importorskip("playwright.async_api")
    page = AsyncMock()
    page.goto.side_effect = playwright.Error("net::ERR_NAME_NOT_RESOLVED")
    runtime = BrowserRuntime(BrowserConfig())
    with pytest.raises(playwright.Error):
        await runtime.navigate(page, "goto", "https://does-not-exist.invalid/")
