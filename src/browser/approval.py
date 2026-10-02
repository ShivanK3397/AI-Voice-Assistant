from __future__ import annotations

import copy
from dataclasses import dataclass
from uuid import uuid4


class ApprovalError(ValueError):
    pass


@dataclass
class PendingAction:
    id: str
    command: dict
    description: str
    prepared_message: str | None
    reviewed_message: str | None = None
    delivered: bool = False


class ApprovalState:
    """Ordering is derived from committed SDK user messages, never tool arguments.

    The model interprets approval/correction. Code enforces delivery, ordering,
    exact payload ownership, invalidation, and single use.
    """

    def __init__(self) -> None:
        self.latest_message: str | None = None
        self.seen_messages: set[str] = set()
        self.pending: PendingAction | None = None

    def observe_user_message(self, message_id: str) -> None:
        if message_id not in self.seen_messages:
            self.seen_messages.add(message_id)
            self.latest_message = message_id

    def prepare(self, command: dict, description: str) -> PendingAction:
        self.pending = PendingAction(
            uuid4().hex, copy.deepcopy(command), description, self.latest_message
        )
        return self.pending

    def delivered(self, action_id: str, *, interrupted: bool, failed: bool) -> bool:
        pending = self.pending
        if not pending or pending.id != action_id:
            return False
        if interrupted or failed or self.latest_message != pending.prepared_message:
            self.cancel()
            return False
        pending.delivered = True
        pending.reviewed_message = self.latest_message
        return True

    def consume(self, action_id: str) -> dict:
        pending = self.pending
        if not pending or pending.id != action_id:
            raise ApprovalError(
                "No matching pending action. Prepare and review it again."
            )
        if not pending.delivered:
            raise ApprovalError("The review has not finished being delivered.")
        if (
            self.latest_message is None
            or self.latest_message == pending.reviewed_message
        ):
            raise ApprovalError("Wait for a later user message approving this action.")
        self.pending = None  # Consume before I/O: an uncertain write is never replayed.
        return copy.deepcopy(pending.command)

    def cancel(self) -> None:
        self.pending = None
