"""Locating one test, and one assertion statement inside it, in a generated test file (pytest or Playwright TypeScript / JavaScript)."""

from __future__ import annotations

import json
import re

TS_METHOD = {"to_contain_text": "toContainText", "to_have_value": "toHaveValue"}
TEST_EXTENSIONS = (".py", ".ts", ".js")


def is_test_path(path: str) -> bool:
    return path.startswith("tests/") and path.endswith(TEST_EXTENSIONS)


def test_block(content: str, test_case_id: str) -> tuple[int, int] | None:
    """``(start, end)`` of the test of ``test_case_id``: from its pytest marker, or from its ``test("TC_ID - title", ...)`` line."""
    marker = re.compile(r"@pytest\.mark\.tc\(['\"]" + re.escape(test_case_id) + r"['\"]\)", re.I)
    found = marker.search(content)
    if found:
        end = content.find("\n@pytest.mark.tc(", found.end())
        return found.start(), end if end > 0 else len(content)
    spec = re.compile(r"""^[ \t]*test\(\s*(["'`])""" + re.escape(test_case_id) + r"""\b""", re.I | re.M)
    found = spec.search(content)
    if not found:
        return None
    following = re.search(r"\n[ \t]*(?://\s*TC_|test\()", content[found.end() :])
    return found.start(), found.end() + following.start() if following else len(content)


def statement_span(files: dict[str, str], test_case_id: str, element_key: str, method: str, expected: str) -> tuple[str, str, str] | None:
    """``(path, segment, call)`` for the assertion ``.<method>(<expected>)`` of ``element_key`` in the test of ``test_case_id``.

    ``method`` is the pytest name (``to_contain_text``); Playwright TypeScript / JavaScript tests use the camel-case equivalent.
    ``segment`` runs from the start of the test to the end of that statement, so it appears exactly once in the file; ``call`` is
    the literal call text inside it. ``None`` when it is not found or not unique."""
    for path, content in sorted(files.items()):
        if not is_test_path(path):
            continue
        block = test_block(content, test_case_id)
        if block is None:
            continue
        body = content[block[0] : block[1]]
        if path.endswith(".py"):
            literals = {repr(expected), '"' + expected.replace("\\", "\\\\").replace('"', '\\"') + '"', "'" + expected.replace("\\", "\\\\").replace("'", "\\'") + "'"}
            name = method
            head = r"element=['\"]" + re.escape(element_key) + r"['\"]\):\n[^\n]*?"
        else:
            literals = {json.dumps(expected, ensure_ascii=False), "'" + expected.replace("\\", "\\\\").replace("'", "\\'") + "'"}
            name = TS_METHOD.get(method, method)
            head = r"element:\s*['\"]" + re.escape(element_key) + r"['\"]\s*\},\s*async \(\) => \{\n[^\n]*?"
        for literal in literals:
            call = f"{name}({literal})"
            hits = list(re.finditer(head + re.escape(call), body))
            if len(hits) == 1:
                segment = body[: hits[0].end()]
                if content.count(segment) == 1:
                    return path, segment, call
        return None
    return None
