"""Test-case design with an AI model whose answers get cut off or come back malformed: the job still finishes."""

from __future__ import annotations

import json

import pytest

from ats.ai.agents import TestCaseAgent
from ats.ai.base import reshape, salvage_items
from ats.ai.agents.generation_agents import TestCaseList
from ats.errors import ModelTruncatedError
from ats.generation.testcases import TestCaseService
from ats.models import DiscoveryResult, PageSnapshot, Scenario


def case(scenario_id: str, n: int = 1) -> dict:
    return {"test_case_id": "", "scenario_id": scenario_id, "module": "Chat", "title": f"Check {scenario_id} #{n}", "steps": ["Open chat", "Send a message"], "expected_result": "Message shown"}


class CutOffClient:
    """Answers like a real model under an output limit: more than one scenario per request is cut off mid-JSON."""

    model_name = "fake-model"

    def __init__(self, broken: set[str] | None = None) -> None:
        self.broken, self.requests = broken or set(), []

    def complete(self, messages, **_kwargs):
        payload = json.loads(messages[1]["content"])
        ids = [s["scenario_id"] for s in payload["scenarios"]]
        self.requests.append(ids)
        if len(ids) > 1:  # too much at once: the answer stops in the middle of the second test case
            text = json.dumps({"test_cases": [case(ids[0])]})[:-2] + ', {"scenario_id": "' + ids[1] + '", "title": "Check'
            return text, {"prompt_tokens": 1, "completion_tokens": 1, "truncated": 1}
        if ids[0] in self.broken:
            return "Sorry, I cannot help with that.", {"prompt_tokens": 1, "completion_tokens": 1}
        return json.dumps([case(ids[0], 1), case(ids[0], 2)]), {"prompt_tokens": 1, "completion_tokens": 1}  # a bare list, not an object


def test_cut_off_and_reshaped_answers_are_salvaged():
    text = '{"test_cases": [{"a": 1}, {"b": 2}, {"c": '
    assert salvage_items(text) == [{"a": 1}, {"b": 2}]
    assert reshape([{"title": "x"}], TestCaseList) == {"test_cases": [{"title": "x"}]}
    assert reshape({"testCases": [{"title": "x"}]}, TestCaseList)["test_cases"] == [{"title": "x"}]


def test_a_cut_off_answer_keeps_its_complete_items_and_an_empty_one_is_not_retried():
    agent = TestCaseAgent(CutOffClient())
    kept = agent.generate({"scenarios": [{"scenario_id": "SC_A_001"}, {"scenario_id": "SC_A_002"}], "application": {}})
    assert [c.scenario_id for c in kept] == ["SC_A_001"]  # the complete test case survives, the cut-off one is dropped

    class Empty(CutOffClient):
        def complete(self, messages, **kwargs):
            self.requests.append(1)
            return '{"test_cases": [{"title": "Che', {"truncated": 1}

    client = Empty()
    with pytest.raises(ModelTruncatedError):
        TestCaseAgent(client).generate({"scenarios": [{"scenario_id": "SC_A_001"}], "application": {}})
    assert len(client.requests) == 1  # asking again for the same amount cannot work: no retries


def test_generation_finishes_for_every_scenario_it_can_and_reports_the_rest(repo):
    project = repo.create_project("owner", name="Big", url="http://127.0.0.1:9", base_url="http://127.0.0.1:9")
    discovery_id = repo.start_discovery(project.id)
    repo.finish_discovery(discovery_id, "completed", DiscoveryResult(start_url=project.url, pages=[PageSnapshot(url=project.url, page_key="home")]))
    scenarios = [Scenario(scenario_id=f"SC_CHT_{i:03d}", title=f"Scenario {i}", module="Chat", status="approved") for i in range(1, 8)]
    repo.save_scenarios(project.id, scenarios)
    client = CutOffClient(broken={"SC_CHT_007"})
    service = TestCaseService(repo, TestCaseAgent(client, repo))

    cases = service.generate(project)

    covered = {c.scenario_id for c in cases}
    assert covered == {f"SC_CHT_{i:03d}" for i in range(1, 7)}  # 6 of 7 scenarios designed, 2 test cases each
    assert len(cases) == 12 and len({c.test_case_id for c in cases}) == 12
    assert service.last_skipped[project.id] == ["SC_CHT_007"]  # the one the model could never design is reported, not fatal
    assert max(len(r) for r in client.requests) == 3  # at most 3 scenarios per request
    assert {c.test_case_id for c in repo.list_test_cases(project.id)} == {c.test_case_id for c in cases}
