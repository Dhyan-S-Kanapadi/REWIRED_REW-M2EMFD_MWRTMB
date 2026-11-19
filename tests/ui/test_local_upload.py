import json
from pathlib import Path

from playwright.sync_api import expect


ROOT = Path(__file__).resolve().parents[2]


def test_attach_preview_and_send_screenshot(page, base_url):
    state = json.loads((ROOT / "data/fixtures/state_foreman.json").read_text(encoding="utf-8"))
    page.route("**/state?*", lambda route: route.fulfill(status=200, json=state))
    sent = []

    def respond(route):
        sent.append(route.request.post_data_buffer)
        route.fulfill(status=200, json={"bubbles": [{"type": "result_card", "status": "needs_review", "amount_paise": 445007, "utr": None, "reason": "Bank evidence required"}]})

    page.route("**/message", respond)
    page.goto(base_url + "/chat/")
    expect(page.get_by_label("Sending as").locator("option[value='member-07']")).to_have_count(1)
    page.get_by_label("Sending as").select_option("member-07")
    screenshot = ROOT / "tests/fixtures/payment_screenshots/genuine/gpay/t07-genuine-gpay-001.png"
    page.locator("#screenshot-input").set_input_files(str(screenshot))
    expect(page.locator("#screenshot-preview")).to_be_visible()
    page.get_by_role("button", name="Send message").click()
    expect(page.locator(".result-bubble")).to_contain_text("needs_review")
    assert len(sent) == 1 and b'name="image"' in sent[0] and b't07-genuine-gpay-001.png' in sent[0]
    expect(page.locator("#screenshot-preview")).to_be_hidden()
