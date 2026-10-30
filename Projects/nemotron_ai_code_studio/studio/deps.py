"""Process-wide singletons shared by the route modules."""

from __future__ import annotations

from .agents.coding_agent import CodingAgent, ConversationStore
from .agents.repository_agent import RepositoryAgent
from .approvals import ApprovalBroker
from .services.nvidia_service import NvidiaService
from .services.repository_service import RepositoryError, repositories

broker = ApprovalBroker()
nvidia = NvidiaService()
coding_agent = CodingAgent(nvidia, broker)
repository_agent = RepositoryAgent()
conversations = ConversationStore()


__all__ = ["broker", "nvidia", "coding_agent", "repository_agent", "conversations", "repositories", "RepositoryError"]
