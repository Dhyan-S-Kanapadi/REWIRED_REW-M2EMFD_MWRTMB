import base64
import json

from playwright.sync_api import expect

STATE_RESPONSE = {
    "members": [{"id": "member-7", "name": "Ravi"}],
    "months": [3],
    "ledger": [
        {
            "member_id": "member-7",
            "month": 3,
            "status": "verified",
            "amount_paise": 445007,
            "utr": "123456789012",
        }
    ],
    "counters": {
        "collected_paise": 445007,
        "paid": 1,
        "total_members": 20,
        "needs_review": 1,
        "overdue": 0,
    },
    "flags": [
        {
            "item_id": "review-1",
            "member_id": "member-8",
            "month": 3,
            "reason": "Readers disagree",
        }
    ],
    "overdue": [],
    "audit_log": [
        {
            "id": "audit-1",
            "actor": "foreman",
            "action": "settle",
            "reason": "Month 3",
            "timestamp": "2026-11-19T10:00:00Z",
        }
    ],
    "statement": [
        {
            "month": 3,
            "instalment_paise": 445007,
            "dividend_paise": 55000,
            "late_fee_paise": 0,
            "prize_paise": 0,
            "status": "verified",
        }
    ],
    "private_bubbles": [
        {"type": "reminder", "text": "Your payment is due."}
    ],
}

MESSAGE_RESPONSE = {
    "bubbles": [
        {"type": "text", "text": "Payment received for checking."},
        {
            "type": "result_card",
            "status": "verified",
            "amount_paise": 445007,
            "utr": "123456789012",
            "reason": "Matched bank credit.",
        },
        {
            "type": "result_card",
            "status": "duplicate",
            "amount_paise": 445007,
            "utr": "123456789012",
            "reason": "UTR already used.",
        },
        {
            "type": "result_card",
            "status": "wrong_amount",
            "amount_paise": 445000,
            "utr": "123456789013",
            "reason": "Expected 445007 paise.",
        },
        {
            "type": "result_card",
            "status": "needs_review",
            "amount_paise": 445007,
            "utr": None,
            "reason": "UTR not found in bank CSV.",
        },
        {
            "type": "review_request",
            "item_id": "review-1",
            "reason": "Readers disagree.",
        },
        {"type": "reminder", "text": "Your payment is due."},
    ]
}


def fulfill_json(route, payload):
    route.fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps(payload),
    )


def stub_state(route):
    fulfill_json(route, STATE_RESPONSE)


def stub_message(route):
    fulfill_json(route, MESSAGE_RESPONSE)


def test_chat_opens_and_sender_can_be_switched(page, base_url):
    state_requests = []

    def capture_state(route):
        state_requests.append(route.request.url)
        stub_state(route)

    page.route("**/state**", capture_state)
    page.goto(f"{base_url}/chat/")

    expect(page.get_by_role("heading", name="Chit group")).to_be_visible()
    expect(page.get_by_role("status").filter(has_text="Connected to the group API")).to_be_visible()
    sender = page.get_by_label("Sending as")
    expect(sender.locator("option")).to_have_count(2)
    sender.select_option("member-7")
    expect(sender).to_have_value("member-7")
    expect(page.get_by_role("status").filter(has_text="Connected to the group API")).to_be_visible()
    assert any("role=member&member_id=member-7" in url for url in state_requests)


def test_message_submission_renders_all_contract_reply_types(page, base_url):
    page.route("**/state**", stub_state)
    page.route("**/message", stub_message)
    page.goto(f"{base_url}/chat/")
    page.get_by_label("Write a message").fill("Payment sent")
    page.get_by_role("button", name="Send").click()

    expect(page.get_by_text("Payment sent", exact=True)).to_be_visible()
    expect(page.get_by_text("Payment received for checking.", exact=True)).to_be_visible()
    expect(page.get_by_text("Verified", exact=True)).to_be_visible()
    expect(page.get_by_text("Duplicate", exact=True)).to_be_visible()
    expect(page.get_by_text("Wrong amount", exact=True)).to_be_visible()
    expect(page.get_by_text("Needs review", exact=True)).to_be_visible()
    expect(page.get_by_text("Matched bank credit.", exact=True)).to_be_visible()
    expect(page.get_by_text("UTR already used.", exact=True)).to_be_visible()
    expect(page.get_by_text("Expected 445007 paise.", exact=True)).to_be_visible()
    expect(page.get_by_text("UTR not found in bank CSV.", exact=True)).to_be_visible()
    expect(page.get_by_text("Review requested", exact=True)).to_be_visible()
    expect(page.get_by_text("Payment reminder", exact=True)).to_be_visible()
    expect(page.locator(".message time")).to_have_count(8)


def test_screenshot_preview_and_removal(page, base_url):
    page.route("**/state**", stub_state)
    page.goto(f"{base_url}/chat/")
    page.locator("#image-input").set_input_files(
        {
            "name": "payment.png",
            "mimeType": "image/png",
            "buffer": base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/"
                "n5sAAAAASUVORK5CYII="
            ),
        }
    )
    expect(page.get_by_alt_text("Screenshot selected for sending")).to_be_visible()
    expect(page.get_by_role("button", name="Send")).to_be_enabled()
    page.get_by_role("button", name="Remove screenshot").click()
    expect(page.locator("#image-preview")).to_be_hidden()
    expect(page.get_by_role("button", name="Send")).to_be_disabled()


def test_loading_and_api_error_states(page, base_url):
    def delayed_state(route):
        page.wait_for_timeout(250)
        stub_state(route)

    page.route("**/state**", delayed_state)
    page.goto(f"{base_url}/chat/")
    expect(page.get_by_text("Loading group members…")).to_be_visible()
    expect(page.get_by_text("Connected to the group API")).to_be_visible()

    page.route(
        "**/state**",
        lambda route: route.fulfill(
            status=500,
            content_type="application/json",
            body=json.dumps(
                {
                    "error": {
                        "code": "server_error",
                        "message": "Service temporarily unavailable.",
                    }
                }
            ),
        ),
    )
    page.reload()
    expect(page.get_by_role("status").filter(has_text="API unavailable")).to_be_visible()
    expect(page.get_by_role("alert")).to_contain_text("Service temporarily unavailable.")
    expect(page.get_by_role("button", name="Try again")).to_be_visible()
