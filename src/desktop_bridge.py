"""Authenticated, optional desktop UI adapter. No desktop HTTP listener."""

from __future__ import annotations

import asyncio
import contextlib
import json
import time

from livekit import rtc

TOPIC = "jarvis.desktop.events"


class DesktopBridge:
    def __init__(self, room, session, browser, session_id: str, identity: str):
        self.room, self.session, self.browser = room, session, browser
        self.session_id, self.identity = session_id, identity
        self.sequence = 0
        self.state = "initializing"
        self.action = None
        self.transcripts: dict[str, dict] = {}
        self.queue: asyncio.Queue = asyncio.Queue()
        self.publisher: asyncio.Task | None = None
        self.participant = None
        browser.event_sink = self.emit
        browser.approvals.on_change = self.approval_changed
        self.listeners = {
            "agent_state_changed": self.state_changed,
            "conversation_item_added": self.conversation_added,
            "user_input_transcribed": self.transcribed,
            "error": self.error,
            "close": self.closed,
        }
        for name, callback in self.listeners.items():
            session.on(name, callback)
        self.rpc_methods = {
            "jarvis.getSnapshot": self.snapshot_rpc,
            "jarvis.resolveApproval": self.approval_rpc,
            "jarvis.stopTask": self.stop_rpc,
        }

    def approval(self):
        pending = self.browser.approvals.pending
        if not pending:
            return None
        return {
            "actionId": pending.id,
            "description": pending.description,
            "delivered": pending.delivered,
            **self.browser.review_details,
        }

    def emit(self, event: str, payload: dict):
        if event.startswith("action."):
            self.action = payload
        self.sequence += 1
        self.queue.put_nowait(
            {
                "version": 1,
                "sessionId": self.session_id,
                "sequence": self.sequence,
                "type": event,
                "timestamp": time.time(),
                "payload": payload,
            }
        )

    def approval_changed(self):
        approval = self.approval()
        self.emit(
            "approval.pending" if approval else "approval.cleared", approval or {}
        )

    def state_changed(self, event):
        if self.state == "recovering":
            return  # A state transition alone is not evidence of provider recovery.
        self.state = event.new_state
        self.emit("session.state", {"state": self.state})

    def recovered(self):
        if self.state == "recovering":
            self.state = self.session.agent_state
            self.emit("session.state", {"state": self.state})

    def conversation_added(self, event):
        from livekit.agents import llm

        item = event.item
        if not isinstance(item, llm.ChatMessage) or item.role not in {
            "user",
            "assistant",
        }:
            return
        if item.id in self.browser.observation_ids or not item.text_content:
            return
        if item.role == "assistant":
            self.recovered()
        transcript = {
            "id": item.id,
            "role": item.role,
            "text": item.text_content,
            "final": True,
        }
        self.transcripts[item.id] = transcript
        while len(self.transcripts) > 300:
            self.transcripts.pop(next(iter(self.transcripts)))
        self.emit("transcript.updated", transcript)

    def transcribed(self, event):
        if event.transcript.strip():
            self.recovered()
        # Interim text is displayed separately; committed messages own stable IDs.
        self.emit(
            "transcript.updated",
            {"id": "interim", "role": "user", "text": event.transcript, "final": False},
        )

    def error(self, event):
        recoverable = getattr(event.error, "recoverable", False)
        self.state = "recovering" if recoverable else "disconnected"
        self.emit(
            "session.error",
            {
                "recoverable": recoverable,
                "message": "The voice provider connection failed. Reconnecting."
                if recoverable
                else "The voice session failed. Use Reconnect to start a new session.",
            },
        )

    def closed(self, _event):
        self.state = "disconnected"
        self.emit("session.state", {"state": self.state})

    def authorize(self, invocation):
        if invocation.caller_identity != self.identity:
            raise rtc.RpcError(1500, "Caller is not the desktop session owner.")

    async def snapshot_rpc(self, invocation):
        self.authorize(invocation)
        self.emit(
            "session.snapshot",
            {
                "state": self.state,
                "action": self.action,
                "approval": self.approval(),
                "transcripts": list(self.transcripts.values()),
            },
        )
        return json.dumps({"status": "snapshot_queued"})

    async def approval_rpc(self, invocation):
        self.authorize(invocation)
        try:
            payload = json.loads(invocation.payload)
            action_id, decision = payload["actionId"], payload["decision"]
            if not isinstance(action_id, str) or decision not in {"approve", "cancel"}:
                raise ValueError("Invalid approval request.")
            result = await self.browser.resolve_ui(action_id, decision)
            return json.dumps(result)
        except (ValueError, KeyError, TypeError) as exc:
            raise rtc.RpcError(1500, str(exc)[:200]) from None

    async def stop_rpc(self, invocation):
        self.authorize(invocation)
        return json.dumps(await self.browser.stop_task())

    async def start(self):
        self.participant = self.room.local_participant
        for method, handler in self.rpc_methods.items():
            self.participant.register_rpc_method(method, handler)
        self.publisher = asyncio.create_task(self.publish())
        self.state = self.session.agent_state
        self.emit(
            "session.ready",
            {
                "state": self.state,
                "agentIdentity": self.participant.identity,
            },
        )

    async def publish(self):
        while True:
            envelope = await self.queue.get()
            # A subsequent authenticated snapshot repairs missed events.
            with contextlib.suppress(Exception):
                await self.participant.send_text(
                    json.dumps(envelope),
                    topic=TOPIC,
                    destination_identities=[self.identity],
                )

    async def close(self):
        self.browser.event_sink = None
        self.browser.approvals.on_change = None
        for name, callback in self.listeners.items():
            self.session.off(name, callback)
        if self.participant:
            for method in self.rpc_methods:
                self.participant.unregister_rpc_method(method)
        if self.publisher:
            self.publisher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.publisher
