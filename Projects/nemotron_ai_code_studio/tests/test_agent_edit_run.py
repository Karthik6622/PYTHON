"""An agent run that edits a file must reach its final answer (no internal error) and report the change."""

import asyncio

from studio.agents.coding_agent import CodingAgent
from studio.approvals import ApprovalBroker
from studio.services.nvidia_service import ChatResult, ToolCall


class EditingModel:
    """First turn edits a file, second turn gives the final answer."""

    def __init__(self) -> None:
        self.turns = 0

    async def agent_chat(self, messages, schemas, model=None):
        self.turns += 1
        if self.turns == 1:
            call = ToolCall("c1", "write_file", {"path": "app/utils.py", "content": "def slugify(text):\n    return text.strip().lower().replace(' ', '-')\n"})
            yield {"type": "done", "result": ChatResult(tool_calls=[call], finish_reason="tool_calls")}
        else:
            yield {"type": "content", "text": "Done: slugify now strips whitespace."}
            yield {"type": "done", "result": ChatResult(content="Done: slugify now strips whitespace.", finish_reason="stop")}


def test_agent_edit_run_finishes_without_internal_error(active):
    events = []
    result = asyncio.run(CodingAgent(EditingModel(), ApprovalBroker()).run(active, "make slugify in app/utils.py strip whitespace", "agent", [], events.append))
    errors = [e for e in events if e["type"] == "error"]
    assert not errors, errors
    assert any(e["type"] == "context" and e["files"] for e in events)  # the request's files were loaded into the prompt
    assert result.ok and result.modified == ["app/utils.py"]
    assert any(e["type"] == "changes" for e in events)
    assert events[-1]["type"] == "done"
