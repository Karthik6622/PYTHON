"""Locating one assertion statement inside a generated test file."""

from __future__ import annotations

import re


def statement_span(files: dict[str, str], test_case_id: str, element_key: str, method: str, expected: str) -> tuple[str, str, str] | None:
    """``(path, segment, call)`` for the assertion ``.<method>(<expected>)`` of ``element_key`` in the test of ``test_case_id``.

    ``segment`` runs from the test's ``@pytest.mark.tc`` marker to the end of that statement, so it appears exactly once in the file;
    ``call`` is the literal ``to_contain_text('...')`` text inside it. ``None`` when it is not found or not unique."""
    marker = re.compile(r"@pytest\.mark\.tc\(['\"]" + re.escape(test_case_id) + r"['\"]\)", re.I)
    for path, content in sorted(files.items()):
        if not (path.startswith("tests/") and path.endswith(".py")):
            continue
        found = marker.search(content)
        if not found:
            continue
        end = content.find("\n@pytest.mark.tc(", found.end())
        body = content[found.start() : end if end > 0 else len(content)]
        literals = {repr(expected), '"' + expected.replace("\\", "\\\\").replace('"', '\\"') + '"', "'" + expected.replace("\\", "\\\\").replace("'", "\\'") + "'"}
        for literal in literals:
            call = f"{method}({literal})"
            pattern = re.compile(r"element=['\"]" + re.escape(element_key) + r"['\"]\):\n[^\n]*?" + re.escape(call))
            hits = list(pattern.finditer(body))
            if len(hits) == 1:
                segment = body[: hits[0].end()]
                if content.count(segment) == 1:
                    return path, segment, call
        return None
    return None
