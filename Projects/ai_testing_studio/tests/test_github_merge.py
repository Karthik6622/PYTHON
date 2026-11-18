"""Pure merge logic: manifest hashes, shared-file merges and the publish plan (no network)."""

from __future__ import annotations

import pytest

from ats.github.merge import (
    MANIFEST_PATH,
    ChannelFiles,
    Manifest,
    blob_sha,
    is_blocked,
    merge_env_example,
    merge_gitignore,
    merge_pytest_ini,
    merge_readme,
    merge_requirements,
    plan_publish,
)

WEB_INI = """[pytest]
testpaths = tests
addopts = -p no:cacheprovider --junitxml=reports/junit.xml --screenshot=only-on-failure
junit_family = xunit2
markers =
    tc(id): the test case identifier this test implements
"""
API_INI = """[pytest]
testpaths = tests
addopts = -p no:cacheprovider --junitxml=reports/junit.xml
junit_family = xunit2
markers =
    tc(id): the test case identifier this test implements
    api: tests that call the API
"""


def web(files: dict[str, str]) -> ChannelFiles:
    return ChannelFiles("web", "playwright_python", files)


def api(files: dict[str, str]) -> ChannelFiles:
    return ChannelFiles("api", "api_python", files)


def test_blob_sha_is_the_git_object_id():
    assert blob_sha("hello\n") == "ce013625030ba8dba906f756967f9e9ca394464a"
    assert blob_sha("") == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"


def test_requirements_add_missing_packages_without_touching_existing_lines():
    existing = "# my pins\npytest==7.4.0\nPlaywright_Python>=1\n\nhttpx\n"
    merged = merge_requirements(existing, "pytest>=8.0\nhttpx>=0.27\njsonschema>=4.0\nAppium-Python-Client>=4\n")
    assert merged == existing + "jsonschema>=4.0\nAppium-Python-Client>=4\n"
    assert merge_requirements(merged, "jsonschema>=4.0\nappium_python_client>=4\n") == merged  # normalised names: no duplicates
    assert merge_requirements("pytest\r\n", "httpx\n") == "pytest\r\nhttpx\r\n"  # the file's own line endings
    assert merge_requirements("", "pytest>=8\n") == "pytest>=8\n"


def test_pytest_ini_union_keeps_existing_keys_and_values():
    merged = merge_pytest_ini(API_INI, WEB_INI)
    assert "--screenshot=only-on-failure" in merged and merged.count("--junitxml") == 1 and merged.count("-p no:cacheprovider") == 1
    assert merged.count("tc(id)") == 1 and "api: tests that call the API" in merged and merged.count("testpaths") == 1
    assert merge_pytest_ini(merged, WEB_INI) == merged and merge_pytest_ini(merged, API_INI) == merged  # idempotent
    custom = "[pytest]\ntestpaths = tests/web tests/custom\naddopts = --junitxml=out/custom.xml -q\nmarkers =\n    slow: slow tests\nminversion = 8.0\n"
    result = merge_pytest_ini(custom, WEB_INI)
    assert "--junitxml=out/custom.xml" in result and "reports/junit.xml" not in result  # the user's value wins
    assert "minversion = 8.0" in result and "slow: slow tests" in result and "tc(id)" in result and "junit_family = xunit2" in result
    assert "testpaths = tests" in result.splitlines()  # the broader path replaces its sub-folders: nothing is collected twice
    assert merge_pytest_ini("[tool]\nx = 1\n", WEB_INI).startswith("[tool]\nx = 1\n") and "[pytest]" in merge_pytest_ini("[tool]\nx = 1\n", WEB_INI)


def test_gitignore_appends_missing_rules_and_never_removes():
    existing = "node_modules/\n/reports\nmy-secret-notes.txt\n"
    merged = merge_gitignore(existing, ["reports/", "*.apk", ".env", "node_modules/"])
    assert merged.startswith(existing) and "*.apk" in merged and ".env" in merged and merged.count("reports") == 1 and merged.count("node_modules") == 1
    assert merge_gitignore(merged, ["*.apk", ".env"]) == merged


def test_env_example_appends_missing_keys_only():
    existing = "BASE_URL=https://mine.example\nAPI_TOKEN=\n"
    merged = merge_env_example(existing, "# Address\nBASE_URL=\nAPPIUM_URL=http://127.0.0.1:4723\n# Credentials\nAPI_TOKEN=\nTEST_APP_USERNAME=\n")
    assert merged.startswith(existing) and "BASE_URL=https://mine.example" in merged and merged.count("BASE_URL") == 1
    assert "APPIUM_URL=http://127.0.0.1:4723" in merged and "TEST_APP_USERNAME=" in merged and merged.count("API_TOKEN") == 1
    assert merge_env_example(merged, "BASE_URL=\nAPPIUM_URL=x\n") == merged


def test_readme_sections_are_managed_per_channel():
    first = merge_readme(None, "web", "# Shop - automated tests\n\n## Setup\n\n```\n# not a heading\n```\n", "Shop")
    assert first.startswith("# Shop\n") and "<!-- ats:web:begin -->" in first and "## Shop - automated tests" in first and "### Setup" in first and "# not a heading" in first
    both = merge_readme(first, "api", "# Shop - API tests\n", "Shop")
    assert "<!-- ats:api:end -->" in both and both.startswith(first.rstrip())
    edited = both.replace("# Shop\n", "# Shop\n\nMy own intro.\n", 1) + "\nMy own footer.\n"
    regenerated = merge_readme(edited, "web", "# Shop - automated tests\n\nNEW BODY\n", "Shop")
    assert "NEW BODY" in regenerated and "My own intro." in regenerated and "My own footer." in regenerated and "<!-- ats:api:begin -->" in regenerated
    user_readme = "# Existing project\n\nHand written.\n"
    assert merge_readme(user_readme, "api", "# API\n").startswith(user_readme.rstrip())


@pytest.mark.parametrize(
    "path",
    [".env", ".env.local", "storage_state.json", "storage_state_admin.json", "app/debug.apk", "app/Release.AAB", "reports/junit.xml", "logs/run.txt", "appium.log", "token.json", "id_rsa", "keys/server.pem"],
)
def test_secrets_binaries_and_run_output_are_blocked(path):
    assert is_blocked(path)


def test_normal_files_and_secret_looking_content_are_handled():
    assert not is_blocked(".env.example") and not is_blocked("tests/web/test_x.py") and not is_blocked("utils/token_helper.py") and not is_blocked(MANIFEST_PATH)
    assert is_blocked("config/x.py", "TOKEN = 'ghp_" + "a" * 36 + "'") and is_blocked("c.txt", "-----BEGIN RSA PRIVATE KEY-----")


def test_plan_for_an_empty_branch_adds_everything_and_the_manifest():
    files = {"tests/web/test_a.py": "# a\n", "tests/web/__init__.py": "", "tests/__init__.py": "", "requirements.txt": "pytest\n", "pytest.ini": WEB_INI, ".env": "SECRET=1"}
    plan = plan_publish({}, [web(files)], Manifest(), {})
    assert {"tests/web/test_a.py", "tests/web/__init__.py", "tests/__init__.py", "requirements.txt", "pytest.ini", ".gitignore"} <= set(plan.add)
    assert plan.blocked == [".env"] and not plan.update and not plan.conflicts
    assert "*.apk" not in plan.add[".gitignore"] and ".env" in plan.add[".gitignore"]  # secret rules always; mobile rules only for mobile
    manifest = Manifest.parse(plan.manifest_text)
    assert manifest.files_of("web")["tests/web/test_a.py"] == blob_sha("# a\n") and "requirements.txt" not in manifest.files_of("web")
    assert plan.commit_files()[MANIFEST_PATH] == plan.manifest_text


def test_mobile_adds_the_standard_ignore_rules():
    plan = plan_publish({}, [ChannelFiles("mobile", "appium_python", {"tests/mobile/test_a.py": "x\n"})], Manifest(), {})
    assert all(rule in plan.add[".gitignore"] for rule in ("*.apk", "appium*.log", "screenshots/", "reports/"))


def test_user_files_are_never_overwritten_or_deleted():
    tree = {"tests/web/test_a.py": blob_sha("# MINE\n"), "tests/web/test_custom.py": blob_sha("# custom\n"), "notes.txt": blob_sha("n")}
    plan = plan_publish(tree, [web({"tests/web/test_a.py": "# generated\n", "tests/web/test_b.py": "# b\n"})], Manifest(), {})
    assert "tests/web/test_b.py" in plan.add and "tests/web/test_a.py" not in plan.changes
    assert [(c.path, c.reason) for c in plan.conflicts] == [("tests/web/test_a.py", "user_file")]
    assert "tests/web/test_custom.py" not in plan.commit_files() and "notes.txt" not in plan.commit_files()  # untouched: not even mentioned
    assert "tests/web/test_a.py" not in Manifest.parse(plan.manifest_text).files_of("web")  # the user's file does not become ours


def test_regeneration_replaces_unmodified_files_and_keeps_edited_ones():
    old_a, old_b = "# a v1\n", "# b v1\n"
    manifest = Manifest({"web": {"framework": "playwright_python", "files": {"tests/web/test_a.py": blob_sha(old_a), "tests/web/test_b.py": blob_sha(old_b), "tests/web/test_gone.py": blob_sha("g")}}})
    tree = {"tests/web/test_a.py": blob_sha(old_a), "tests/web/test_b.py": blob_sha("# b EDITED BY USER\n"), "tests/web/test_gone.py": blob_sha("g"), MANIFEST_PATH: "m"}
    plan = plan_publish(tree, [web({"tests/web/test_a.py": "# a v2\n", "tests/web/test_b.py": "# b v2\n"})], manifest, {})
    assert plan.update == {"tests/web/test_a.py": "# a v2\n"}
    assert [(c.path, c.reason) for c in plan.conflicts] == [("tests/web/test_b.py", "user_edited")]
    assert plan.stale == ["tests/web/test_gone.py"]  # no longer generated: reported, never deleted
    recorded = Manifest.parse(plan.manifest_text).files_of("web")
    assert recorded["tests/web/test_a.py"] == blob_sha("# a v2\n") and recorded["tests/web/test_b.py"] == blob_sha(old_b)  # still flagged as edited next time


def test_publishing_the_same_content_again_changes_nothing():
    files = {"tests/web/test_a.py": "# a\n", "tests/__init__.py": "", "requirements.txt": "pytest\n", "pytest.ini": WEB_INI, "README.md": "# Shop\n", ".gitignore": "x/\n", ".env.example": "A=\n"}
    first = plan_publish({}, [web(files)], Manifest(), {})
    tree = {path: blob_sha(text) for path, text in first.commit_files().items()}
    again = plan_publish(tree, [web(files)], first.manifest, {p: first.add[p] for p in ("requirements.txt", "pytest.ini", "README.md", ".gitignore", ".env.example")})
    assert again.empty, again.summary()


def test_adding_api_to_a_web_branch_merges_shared_files_and_keeps_web():
    web_files = {"tests/web/test_a.py": "# a\n", "tests/__init__.py": "", "utils/__init__.py": "", "utils/app.py": "app\n", "requirements.txt": "pytest>=8.0\nplaywright==1.49.0\n", "pytest.ini": WEB_INI}
    first = plan_publish({}, [web(web_files)], Manifest(), {})
    tree = {path: blob_sha(text) for path, text in first.commit_files().items()}
    shared = {p: first.add[p] for p in ("requirements.txt", "pytest.ini", ".gitignore")}
    api_files = {"tests/api/test_b.py": "# b\n", "tests/__init__.py": "", "utils/__init__.py": "", "utils/api.py": "api\n", "requirements.txt": "pytest>=8.0\nhttpx>=0.27\n", "pytest.ini": API_INI}
    plan = plan_publish(tree, [api(api_files)], first.manifest, shared)
    assert set(plan.add) == {"tests/api/test_b.py", "utils/api.py"} and set(plan.update) == {"requirements.txt", "pytest.ini"}  # tests/__init__.py exist: not rewritten
    assert plan.update["requirements.txt"] == shared["requirements.txt"] + "httpx>=0.27\n"
    assert "--screenshot=only-on-failure" in plan.update["pytest.ini"] and "api: tests that call the API" in plan.update["pytest.ini"]
    assert not plan.conflicts and "utils/app.py" not in plan.commit_files() and "tests/web/test_a.py" not in plan.commit_files()
    assert set(Manifest.parse(plan.manifest_text).channels) == {"web", "api"}


def test_a_file_owned_by_another_channel_is_not_overwritten():
    manifest = Manifest({"web": {"framework": "playwright_python", "files": {"utils/shared.py": blob_sha("web version\n")}}})
    plan = plan_publish({"utils/shared.py": blob_sha("web version\n"), MANIFEST_PATH: "m"}, [api({"utils/shared.py": "api version\n"})], manifest, {})
    assert [(c.path, c.reason) for c in plan.conflicts] == [("utils/shared.py", "other_channel")] and not plan.update
