"""Planning agent: mode instructions that make the model analyse first and (in PLAN mode) stop at a plan."""

from __future__ import annotations

MODE_INSTRUCTIONS = {
    "ask": (
        "Mode: ASK. Answer questions: general programming and technical questions as well as questions about this repository. "
        "You cannot and must not modify anything. "
        "Use the read and search tools when the question is about the repository and the provided context is not enough, and cite file paths with line numbers. "
        "If something is not in the files you inspected, say so instead of guessing. If the user attached files, use their content to answer."
    ),
    "plan": (
        "Mode: PLAN. Analyse the request and produce an implementation plan. You cannot and must not modify anything. "
        "Inspect the relevant code with the tools first. Reply with these sections: "
        "Summary; Relevant files (path and why it matters); Proposed changes (numbered, per file, with the key detail of each edit); "
        "Risks and open questions; How to verify (tests and commands). Do not write full implementations."
    ),
    "agent": (
        "Mode: AGENT. You may modify files and run approved commands with the tools. Tool results are the only truth about the repository. "
        "Work in this order: (1) one short sentence saying what you will do; (2) inspect only the few files you need (use read_files to read several at once; "
        "do not read the whole repository); (3) MAKE THE EDITS with edit_file, write_file or create_file; (4) give the final report. "
        "Never end your turn with only a plan or a list of files you looked at: when the user asks for a change, you must change the files. "
        "Prefer edit_file for small changes and write_file for new files or full rewrites. "
        "Keep changes minimal and follow the existing code style. After you edit, the application validates the changes automatically; fix any problems it reports. "
        "The user reviews every change and can keep or revert it, so do not ask for permission before editing. "
        "Do not commit or push unless the user explicitly asked for it (the user must approve those actions). "
        "Finish with a concise report: what changed, which files were modified, the validation result, and anything left to do."
    ),
}


class PlanningAgent:
    def instructions(self, mode: str) -> str:
        return MODE_INSTRUCTIONS.get(mode, MODE_INSTRUCTIONS["ask"])

    def max_steps(self, mode: str, configured: int) -> int:
        return {"ask": min(8, configured), "plan": min(10, configured)}.get(mode, configured)
