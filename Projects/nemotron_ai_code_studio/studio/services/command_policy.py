"""Classifies shell commands before the AI agent may run them: allowed, needs the user's approval, or refused outright.

This is a safety net for the agent, not a sandbox: commands run with the user's own permissions inside the repository folder.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SEGMENT_SPLIT = re.compile(r"&&|\|\||[;|&\n]")

_DENY: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\brm\s+(?:-[a-z]*\s+)*-[a-z]*(?:r[a-z]*f|f[a-z]*r)[a-z]*\s+(?:--\s+)?(?:/|~|\$home|\*|\.\.|[a-z]:[\\/]?)(?:\s|$)", re.I), "recursive delete of a root, home or parent folder"),
    (re.compile(r"\b(?:rd|rmdir)\s+/s\b.*\s[a-z]:[\\/]?(?:\s|$)", re.I), "recursive delete of a drive root"),
    (re.compile(r"\bdel\s+(?:/[a-z]\s+)+[a-z]:[\\/]", re.I), "deleting files from a drive root"),
    (re.compile(r"remove-item\b.*-recurse\b.*\s[a-z]:[\\/]?(?:\s|$)", re.I), "recursive delete of a drive root"),
    (re.compile(r"\bmkfs(?:\.\w+)?\b|\bformat\s+[a-z]:|\bdiskpart\b", re.I), "formatting a disk"),
    (re.compile(r"\bdd\b[^|;&]*\bof=/dev/", re.I), "writing directly to a device"),
    (re.compile(r":\(\)\s*\{"), "fork bomb"),
    (re.compile(r"\b(?:shutdown|reboot|halt|poweroff)\b", re.I), "shutting down the machine"),
    (re.compile(r"\b(?:curl|wget)\b[^|]*\|\s*(?:sudo\s+)?(?:sh|bash|zsh|python\d?|pwsh|powershell)\b", re.I), "piping a download into a shell"),
    (re.compile(r"\b(?:iex|invoke-expression)\b", re.I), "executing downloaded or generated code"),
    (re.compile(r"powershell(?:\.exe)?\b[^|;&]*\s-(?:enc|encodedcommand)\b", re.I), "encoded PowerShell"),
    (re.compile(r"\bchmod\s+-r\s+7\d\d\s+/(?:\s|$)", re.I), "changing permissions on the filesystem root"),
    (re.compile(r"\b(?:sudo|su)\s", re.I), "elevated privileges"),
    (re.compile(r"\breg\s+(?:delete|add)\b|\bnet\s+user\b|\bschtasks\b|\bcrontab\b", re.I), "changing system configuration"),
    (re.compile(r"\bgit\s+push\b[^|;&]*(?:--force\b|\s-f\b|--force-with-lease)", re.I), "force-pushing (use the Git panel yourself)"),
]

_APPROVE: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(?:pip3?|python3?\s+-m\s+pip|py\s+-m\s+pip)\s+(?:install|uninstall)\b|\buv\s+(?:add|pip\s+install|sync)\b|\bpoetry\s+(?:add|install|remove)\b|\bpipx\s+install\b", re.I), "installs or removes Python packages"),
    (re.compile(r"\b(?:npm|pnpm|yarn|bun)\s+(?:install|i|add|ci|update|upgrade|remove|uninstall|link|publish)\b", re.I), "installs or changes JavaScript packages"),
    (re.compile(r"\bnpx\b|\bpnpm\s+dlx\b|\byarn\s+dlx\b|\bbunx\b", re.I), "downloads and runs a package"),
    (re.compile(r"\bplaywright\s+install(?:-deps)?\b|\bpython3?\s+-m\s+playwright\s+install(?:-deps)?\b|\bpy\s+-m\s+playwright\s+install(?:-deps)?\b", re.I), "downloads browser binaries"),
    (re.compile(r"\b(?:apt|apt-get|dnf|yum|brew|choco|winget|scoop|snap)\s", re.I), "installs system software"),
    (re.compile(r"\b(?:cargo|go|gem|dotnet)\s+(?:install|add|get)\b", re.I), "installs packages"),
    (re.compile(r"(?:^|\s)(?:rm|rmdir|rd|del|erase|unlink|shred|truncate)(?:\s|$)|\bremove-item\b", re.I), "deletes files"),
    (re.compile(r"\bgit\s+(?:push|commit|reset|clean|rebase|merge|cherry-pick|revert|stash\s+(?:drop|clear)|branch\s+-d|tag\s+-d|checkout\s+--|restore|pull|rm|am|apply)\b", re.I), "changes Git history or the working tree"),
    (re.compile(r"\b(?:curl|wget|invoke-webrequest|iwr|invoke-restmethod|irm|ssh|scp|sftp|ftp|nc|ncat|telnet)\b", re.I), "uses the network"),
    (re.compile(r"\b(?:chmod|chown|chgrp|icacls|takeown)\b", re.I), "changes permissions"),
    (re.compile(r"\b(?:kill|killall|pkill|taskkill|stop-process)\b", re.I), "stops processes"),
    (re.compile(r"\b(?:docker|podman|kubectl|terraform)\s+(?:rm|rmi|run|exec|prune|apply|destroy|delete|push|system)\b", re.I), "changes containers or infrastructure"),
]

READ_ONLY_HEADS = {"ls", "dir", "cat", "type", "echo", "pwd", "cd", "head", "tail", "wc", "grep", "findstr", "find", "where", "which", "tree"}

# Setting up the project (pip install, npm install, playwright install) needs no confirmation when the user types it themselves.
USER_TRUSTED = {
    "installs or removes Python packages", "installs or changes JavaScript packages", "downloads and runs a package",
    "downloads browser binaries", "installs packages",
}


@dataclass(frozen=True)
class Verdict:
    level: str  # "allow" | "approve" | "deny"
    reason: str = ""


def classify_command(command: str, user_initiated: bool = False) -> Verdict:
    """user_initiated=True is for commands the person typed in the terminal: package installs run without a prompt."""
    text = (command or "").strip()
    if not text:
        return Verdict("deny", "The command is empty.")
    if len(text) > 4000:
        return Verdict("deny", "The command is too long.")
    for pattern, reason in _DENY:
        if pattern.search(text):
            return Verdict("deny", f"Blocked: {reason}.")
    reasons: list[str] = []
    for segment in (part.strip() for part in _SEGMENT_SPLIT.split(text)):
        if not segment:
            continue
        for pattern, reason in _APPROVE:
            if pattern.search(segment) and reason not in reasons and not (user_initiated and reason in USER_TRUSTED):
                reasons.append(reason)
    if reasons:
        return Verdict("approve", "This command " + "; ".join(reasons) + ".")
    return Verdict("allow")
