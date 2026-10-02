import pytest

from browser.approval import ApprovalError, ApprovalState


def prepared():
    state = ApprovalState()
    state.observe_user_message("request")
    pending = state.prepare(
        {"ticket": "worker-ticket", "kind": "script"}, "Set the title"
    )
    return state, pending


def test_requires_completed_review_and_later_real_user_message():
    state, pending = prepared()
    with pytest.raises(ApprovalError, match="not finished"):
        state.consume(pending.id)
    assert state.delivered(pending.id, interrupted=False, failed=False)
    with pytest.raises(ApprovalError, match="later user"):
        state.consume(pending.id)
    state.observe_user_message("approval")
    assert state.consume(pending.id) == {"ticket": "worker-ticket", "kind": "script"}
    with pytest.raises(ApprovalError, match="No matching"):
        state.consume(pending.id)


@pytest.mark.parametrize("interrupted,failed", [(True, False), (False, True)])
def test_interrupted_or_failed_review_cannot_authorize(interrupted, failed):
    state, pending = prepared()
    assert not state.delivered(pending.id, interrupted=interrupted, failed=failed)
    state.observe_user_message("approval")
    with pytest.raises(ApprovalError):
        state.consume(pending.id)


def test_correction_during_review_invalidates_delivery():
    state, pending = prepared()
    state.observe_user_message("correction")
    assert not state.delivered(pending.id, interrupted=False, failed=False)
    assert state.pending is None


def test_old_or_replayed_messages_do_not_manufacture_approval():
    state, pending = prepared()
    state.delivered(pending.id, interrupted=False, failed=False)
    state.observe_user_message("request")
    with pytest.raises(ApprovalError):
        state.consume(pending.id)


def test_cancel_or_replacement_invalidates_old_action():
    state, pending = prepared()
    state.cancel()
    replacement = state.prepare({"ticket": "different"}, "A different action")
    state.delivered(replacement.id, interrupted=False, failed=False)
    state.observe_user_message("approval")
    with pytest.raises(ApprovalError):
        state.consume(pending.id)
    assert state.consume(replacement.id) == {"ticket": "different"}


def test_payload_is_copied_when_prepared():
    state = ApprovalState()
    command = {"ticket": "original"}
    pending = state.prepare(command, "Read")
    command["ticket"] = "tampered"
    state.delivered(pending.id, interrupted=False, failed=False)
    state.observe_user_message("approval")
    assert state.consume(pending.id)["ticket"] == "original"
