"""Repository agent: builds a deterministic understanding of the repository (no model call needed)."""

from __future__ import annotations

from typing import Any

from ..services.repository_service import ActiveRepository


class RepositoryAgent:
    def overview(self, repo: ActiveRepository) -> dict[str, Any]:
        summary = repo.index.summary()
        biggest = sorted(repo.index.files.values(), key=lambda entry: entry.lines, reverse=True)[:8]
        hubs = sorted(repo.index.imported_by.items(), key=lambda item: len(item[1]), reverse=True)[:8]
        return {
            **summary,
            "name": repo.name,
            "largest_files": [{"path": entry.path, "lines": entry.lines} for entry in biggest],
            "most_imported": [{"path": path, "imported_by": len(users)} for path, users in hubs if users],
            "map": repo.index.repo_map(repo.name),
        }

    def explain_prompt(self, repo: ActiveRepository) -> str:
        """A request the user can send in ASK mode to get the model's own summary of the repository."""
        return (
            "Give me an overview of this repository: its purpose, the main components and how they fit together, "
            "how to run it, and where I should start reading. Base it only on files you have actually inspected."
        )
