import json
from types import SimpleNamespace

import pytest
from livekit import rtc

from browser.approval import ApprovalError, ApprovalState
from desktop_bridge import DesktopBridge


class LocalParticipant:
    identity = "agent"

    def __init__(self):
        self.methods = {}
        self.sent = []

    def register_rpc_method(self, name, callback):
        self.methods[name] = callback

    def unregister_rpc_method(self, name):
        self.methods.pop(name)

    async def send_text(self, text, **options):
        self.sent.append((json.loads(text), options))


class Session:
    agent_state = "listening"

    def __init__(self):
        self.listeners = {}

    def on(self, name, callback):
        self.listeners[name] = callback

    def off(self, name, _callback):
        self.listeners.pop(name)


class Browser:
    def __init__(self):
        self.approvals = ApprovalState()
        self.review_details = {
            "operation": {"code": "return await page.title()"},
            "page": {"url": "https://example.com"},
        }
        self.observation_ids = set()
        self.executed = []

    async def resolve_ui(self, action_id, decision):
        if decision == "approve":
            self.executed.append(self.approvals.consume_ui(action_id))
        else:
            self.approvals.cancel()
        return {"status": "execution_started"}

    async def stop_task(self):
        self.approvals.cancel()
        return {"status": "stopped"}


def fixture():
    participant, browser, session = LocalParticipant(), Browser(), Session()
    bridge = DesktopBridge(
        SimpleNamespace(local_participant=participant),
        session,
        browser,
        "session",
        "owner",
    )
    return bridge, participant, browser


async def test_desktop_rpc_requires_owner_and_does_not_allow_replay():
    bridge, _, browser = fixture()
    browser.approvals.observe_user_message("request")
    pending = browser.approvals.prepare({"ticket": "worker"}, "Read title")
    browser.approvals.delivered(pending.id, interrupted=False, failed=False)
    payload = json.dumps({"actionId": pending.id, "decision": "approve"})
    with pytest.raises(rtc.RpcError):
        await bridge.approval_rpc(
            SimpleNamespace(caller_identity="attacker", payload=payload)
        )
    assert not browser.executed
    await bridge.approval_rpc(SimpleNamespace(caller_identity="owner", payload=payload))
    assert browser.executed == [{"ticket": "worker"}]
    with pytest.raises(rtc.RpcError):
        await bridge.approval_rpc(
            SimpleNamespace(caller_identity="owner", payload=payload)
        )
    await bridge.close()


async def test_snapshot_is_streamed_with_session_identity_and_full_review_details():
    bridge, participant, browser = fixture()
    browser.approvals.prepare({"ticket": "worker"}, "Read title")
    await bridge.start()
    await bridge.snapshot_rpc(SimpleNamespace(caller_identity="owner"))
    import asyncio

    await asyncio.sleep(0.01)
    snapshot, options = participant.sent[-1]
    assert snapshot["type"] == "session.snapshot"
    assert snapshot["sessionId"] == "session"
    assert snapshot["payload"]["approval"]["delivered"] is False
    assert (
        snapshot["payload"]["approval"]["operation"]["code"]
        == "return await page.title()"
    )
    assert options["destination_identities"] == ["owner"]
    assert [item[0]["sequence"] for item in participant.sent] == sorted(
        item[0]["sequence"] for item in participant.sent
    )
    await bridge.close()
    assert not participant.methods


async def test_provider_recovery_requires_activity_not_state_transition():
    bridge, _, _ = fixture()
    bridge.error(SimpleNamespace(error=SimpleNamespace(recoverable=True)))
    bridge.state_changed(SimpleNamespace(new_state="listening"))
    assert bridge.state == "recovering"
    bridge.transcribed(SimpleNamespace(transcript=""))
    assert bridge.state == "recovering"
    bridge.transcribed(SimpleNamespace(transcript="Hello"))
    assert bridge.state == "listening"
    await bridge.close()


def test_ui_approval_requires_delivered_review_and_no_intervening_user_message():
    state = ApprovalState()
    state.observe_user_message("request")
    pending = state.prepare({"ticket": "original"}, "Review")
    with pytest.raises(ApprovalError):
        state.consume_ui(pending.id)
    state.delivered(pending.id, interrupted=False, failed=False)
    state.observe_user_message("correction")
    with pytest.raises(ApprovalError, match="new user message"):
        state.consume_ui(pending.id)
    assert state.pending.id == pending.id
