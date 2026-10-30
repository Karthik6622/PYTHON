"""Planning agent: mode instructions that make the model analyse first and (in PLAN mode) stop at a plan."""

from __future__ import annotations

MODE_INSTRUCTIONS = {
    "ask": (
        "Mode: ASK. Answer questions and explain code. You cannot and must not modify anything. "
        "Use the read and search tools when the provided context is not enough, and cite file paths with line numbers. "
        "If something is not in the files you inspected, say so instead of guessing."
    ),
    "plan": (
        "Mode: PLAN. Analyse the request and produce an implementation plan. You cannot and must not modify anything. "
        "Inspect the relevant code with the tools first. Reply with these sections: "
        "Summary; Relevant files (path and why it matters); Proposed changes (numbered, per file, with the key detail of each edit); "
        "Risks and open questions; How to verify (tests and commands). Do not write full implementations."
    ),
    "agent": (
        "Mode: AGENT. You may modify files and run approved commands with the tools. Tool results are the only truth about the repository. "
        "Start with a short plan of 3-6 bullet points, then work through it. Prefer edit_file for small changes and write_file for new files or full rewrites. "
        "Keep changes minimal and follow the existing code style. After you edit, the application validates the changes automatically; fix any problems it reports. "
        "Do not commit or push unless the user explicitly asked for it (the user must approve those actions). "
        "Finish with a concise report: what changed, which files were modified, the validation result, and anything left to do."
    ),
}


class PlanningAgent:
    def instructions(self, mode: str) -> str:
        return MODE_INSTRUCTIONS.get(mode, MODE_INSTRUCTIONS["ask"])

    def max_steps(self, mode: str, configured: int) -> int:
        return {"ask": min(8, configured), "plan": min(10, configured)}.get(mode, configured)
