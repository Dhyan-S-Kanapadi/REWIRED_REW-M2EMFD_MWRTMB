import copy
import json
import re
from pathlib import Path

from playwright.sync_api import expect


ROOT = Path(__file__).resolve().parents[2]
STATE_FIXTURE = ROOT / "data" / "fixtures" / "state_foreman.json"
FOREMAN_ROUTE = re.compile(r".*/state\?role=foreman$")
DASHBOARD_CONFIG_ROUTE = re.compile(r".*/dashboard/config\.js$")


def fixture_state():
    return json.loads(STATE_FIXTURE.read_text(encoding="utf-8"))


def fulfill_state(route, payload):
    route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))


def watch_errors(page):
    console_errors = []
    failed_requests = []
    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
    page.on("requestfailed", lambda request: failed_requests.append(request.url))
    return console_errors, failed_requests


def open_dashboard(page, base_url):
    page.route(DASHBOARD_CONFIG_ROUTE, lambda route: route.fulfill(
        status=200,
        content_type="application/javascript",
        body='window.CHITMIRROR_API_BASE = "";window.CHITMIRROR_GROUP_NAME = "Demo chit group";window.CHITMIRROR_POLL_MS = 10000;window.CHITMIRROR_DEFAULT_MEMBER = "member-07";'
    ))
    page.goto(f"{base_url}/dashboard/")
    expect(page.get_by_test_id("review-list")).to_have_attribute("aria-busy", "false")


def install_reminder_stub(page, *, status=200, payload=None, reject=False):
    page.evaluate("""({status, payload, reject}) => {
      window.__reminderRequests = [];
      window.__reminderStatus = status;
      window.__reminderPayload = payload;
      window.__rejectReminder = reject;
      window.__resolveReminder = null;
      const originalFetch = window.fetch.bind(window);
      window.fetch = (url, options) => {
        if (String(url).includes('/reminders/send')) {
          window.__reminderRequests.push(JSON.parse(options.body));
          if (window.__rejectReminder) return Promise.reject(new Error('network unavailable'));
          return new Promise(resolve => {
            window.__resolveReminder = () => resolve(new Response(JSON.stringify(window.__reminderPayload), {
              status: window.__reminderStatus,
              headers: {'Content-Type': 'application/json'}
            }));
          });
        }
        return originalFetch(url, options);
      };
    }""", {"status": status, "payload": payload if payload is not None else {"sent": 0}, "reject": reject})


def resolve_reminder(page):
    page.evaluate("() => window.__resolveReminder && window.__resolveReminder()")


def test_scenario_a_panels_render_contract_data(page, base_url):
    console_errors, failed_requests = watch_errors(page)
    page.route(FOREMAN_ROUTE, lambda route: fulfill_state(route, fixture_state()))
    open_dashboard(page, base_url)

    flag = page.get_by_test_id("flag-row").filter(has_text="Screenshot claim has no matching independent bank evidence.").first
    expect(flag).to_be_visible()
    assert "Member 20" in flag.inner_text()
    assert "Ref review-month-03-member-20" in flag.inner_text()
    assert "₹4,450.00" in flag.inner_text()
    assert "Needs review" in flag.inner_text()

    expect(page.get_by_test_id("overdue-row")).to_have_count(2)
    overdue = page.get_by_test_id("overdue-list")
    assert "Member 18" in overdue.inner_text()
    assert "Month 4" in overdue.inner_text()
    assert "₹4,350.00" in overdue.inner_text()
    assert "Overdue" in overdue.inner_text()
    assert "Member 20" not in overdue.inner_text()

    expect(page.get_by_test_id("audit-row")).to_have_count(11)
    assert page.get_by_test_id("audit-row").first.get_attribute("data-audit-id") == "audit-auction-04"
    audit = page.get_by_test_id("audit-list")
    assert "auction_winner_recorded" in audit.inner_text()
    assert "foreman" in audit.inner_text()
    assert "2026" in audit.inner_text()
    assert audit.locator("button, input, select, textarea, [contenteditable='true']").count() == 0

    page.get_by_role("button", name="Member").click()
    expect(page.get_by_test_id("send-reminders")).to_be_hidden()
    assert console_errors == []
    assert failed_requests == []


def test_scenario_b_reminder_success_sends_once_and_refreshes(page, base_url):
    initial = fixture_state()
    updated = copy.deepcopy(initial)
    updated["overdue"] = []
    updated["counters"]["overdue"] = 0
    state_calls = []

    def state_stub(route):
        state_calls.append(route.request.url)
        fulfill_state(route, initial if len(state_calls) == 1 else updated)

    page.route(FOREMAN_ROUTE, state_stub)
    open_dashboard(page, base_url)
    expect(page.get_by_test_id("kpi-overdue")).to_have_text("2")

    install_reminder_stub(page, payload={"sent": 2})
    button = page.get_by_test_id("send-reminders")
    status = page.locator("#reminder-status")
    button.click()

    expect(button).to_be_disabled()
    expect(button).to_have_text("Sending…")
    expect(status).to_contain_text("Sending private reminders…")
    page.evaluate("() => window.chitmirrorDashboard.sendRemindersNow()")
    assert page.evaluate("() => window.__reminderRequests") == [{"actor": "foreman"}]

    resolve_reminder(page)
    expect(status).to_contain_text("Backend recorded 2 private reminders")
    expect(status).to_contain_text("No WhatsApp or external message was sent")
    expect(button).to_be_enabled()
    expect(button).to_have_text("Send reminders now")
    expect(page.get_by_test_id("kpi-overdue")).to_have_text("0")
    expect(page.get_by_test_id("overdue-list")).to_contain_text("No overdue payments recorded.")
    assert len(state_calls) >= 2
    assert page.evaluate("() => window.__reminderRequests") == [{"actor": "foreman"}]


def test_scenario_c_reminder_error_is_meaningful_and_retryable(page, base_url):
    console_errors, failed_requests = watch_errors(page)
    page.route(FOREMAN_ROUTE, lambda route: fulfill_state(route, fixture_state()))
    open_dashboard(page, base_url)

    install_reminder_stub(page, status=422, payload={"error": {"code": "invalid_request", "message": "Foreman required."}})
    button = page.get_by_test_id("send-reminders")
    status = page.locator("#reminder-status")
    button.click()
    expect(button).to_be_disabled()
    resolve_reminder(page)

    expect(status).to_contain_text("Could not send reminders: Foreman required.")
    expect(status).not_to_contain_text("Backend recorded")
    expect(button).to_be_enabled()
    expect(button).to_have_text("Send reminders now")

    page.evaluate("() => { window.__reminderStatus = 200; window.__reminderPayload = {sent: 1}; }")
    button.click()
    expect(button).to_be_disabled()
    resolve_reminder(page)
    expect(status).to_contain_text("Backend recorded 1 private reminder")
    expect(button).to_be_enabled()
    assert page.evaluate("() => window.__reminderRequests") == [{"actor": "foreman"}, {"actor": "foreman"}]
    assert console_errors == []
    assert failed_requests == []


def test_reminder_network_failure_shows_error(page, base_url):
    page.route(FOREMAN_ROUTE, lambda route: fulfill_state(route, fixture_state()))
    open_dashboard(page, base_url)
    install_reminder_stub(page, reject=True)

    page.get_by_test_id("send-reminders").click()
    expect(page.locator("#reminder-status")).to_contain_text("Could not send reminders: network unavailable")
    expect(page.get_by_test_id("send-reminders")).to_be_enabled()


def test_empty_panel_states(page, base_url):
    state = fixture_state()
    state["flags"] = []
    state["overdue"] = []
    state["audit_log"] = []
    state["counters"]["needs_review"] = 0
    state["counters"]["overdue"] = 0
    page.route(FOREMAN_ROUTE, lambda route: fulfill_state(route, state))
    open_dashboard(page, base_url)

    expect(page.get_by_test_id("kpi-review")).to_have_text("0")
    expect(page.get_by_test_id("kpi-overdue")).to_have_text("0")
    expect(page.get_by_test_id("review-list")).to_contain_text("No items need review.")
    expect(page.get_by_test_id("overdue-list")).to_contain_text("No overdue payments recorded.")
    expect(page.get_by_test_id("audit-list")).to_contain_text("No audit events recorded.")
