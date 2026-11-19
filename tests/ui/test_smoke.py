import pytest
from playwright.sync_api import expect


@pytest.mark.parametrize("path,title", [("dashboard", "ChitMirror Dashboard")])
def test_page_connects_to_backend(page, base_url, path, title):
    page.goto(f"{base_url}/{path}/")
    expect(page.get_by_role("heading", name=title, exact=True)).to_be_visible()
    expect(page.get_by_role("status")).to_have_text("Backend connected")


@pytest.mark.parametrize("path", ["dashboard"])
def test_backend_failure_is_visible(page, base_url, path):
    page.route("**/health", lambda route: route.abort())
    page.goto(f"{base_url}/{path}/")
    expect(page.get_by_role("status")).to_contain_text("Backend unavailable")
