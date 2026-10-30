"""A run must never end silently: every abnormal ending leaves a visible explanation and a Continue hint."""

import asyncio

from studio.agents.coding_agent import CodingAgent
from studio.approvals import ApprovalBroker
from studio.chat import ChatMessage, apply_event
from studio.services.nvidia_service import ChatResult


class EmptyModel:
    """A model that answers with nothing at all, every time."""

    async def agent_chat(self, messages, schemas, model=None):
        yield {"type": "done", "result": ChatResult(content="", finish_reason="stop")}


class SlowModel:
    async def agent_chat(self, messages, schemas, model=None):
        await asyncio.sleep(30)
        yield {"type": "done", "result": ChatResult(content="late")}


def _replay(events):
    message = ChatMessage(role="assistant", streaming=True)
    approvals = {}
    for event in events:
        apply_event(message, event, approvals)
    return message


def test_empty_model_reply_is_explained(active):
    events = []
    asyncio.run(CodingAgent(EmptyModel(), ApprovalBroker()).run(active, "restyle it", "ask", [], events.append))
    message = _replay(events)
    assert not message.streaming
    assert "empty reply" in message.text
    assert message.incomplete


def test_stopping_leaves_a_notice(active):
    events = []

    async def scenario():
        task = asyncio.ensure_future(CodingAgent(SlowModel(), ApprovalBroker()).run(active, "restyle it", "ask", [], events.append))
        await asyncio.sleep(0.5)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(scenario())
    message = _replay(events)
    assert not message.streaming
    assert message.status == "Stopped"
    assert message.text.startswith("Stopped.")
    assert message.incomplete


def test_error_marks_the_reply_incomplete():
    message = _replay([{"type": "error", "message": "boom"}])
    assert message.error == "boom"
    assert message.incomplete
