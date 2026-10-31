"""The nine logical agents (the execution orchestrator is deliberately not an agent)."""

from ats.ai.agents.analysis_agents import FailureAnalysisAgent, SelfHealingAgent
from ats.ai.agents.discovery_agents import LocatorIntelligenceAgent, WebDiscoveryAgent
from ats.ai.agents.generation_agents import ScenarioAgent, ScriptGenerationAgent, TestCaseAgent
from ats.ai.agents.reporting_agents import GitHubAgent, ReportAgent

__all__ = [
    "FailureAnalysisAgent",
    "GitHubAgent",
    "LocatorIntelligenceAgent",
    "ReportAgent",
    "ScenarioAgent",
    "ScriptGenerationAgent",
    "SelfHealingAgent",
    "TestCaseAgent",
    "WebDiscoveryAgent",
]
