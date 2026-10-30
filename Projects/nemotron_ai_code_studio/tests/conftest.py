import os
import sys
import tempfile
from pathlib import Path

_BASE = Path(tempfile.mkdtemp(prefix="nemotron-tests-"))
os.environ["WORKSPACE_PATH"] = str(_BASE / "workspaces")
os.environ["AUTO_VALIDATE"] = "0"
os.environ.pop("NVIDIA_API_KEY", None)
os.environ.pop("GITHUB_TOKEN", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from git import Repo  # noqa: E402

from studio.config import settings  # noqa: E402
from studio.services import repository_service  # noqa: E402

FILES = {
    "app/__init__.py": "",
    "app/main.py": "from app.auth import login_user\n\n\ndef run():\n    return login_user('a', 'b')\n\n\nif __name__ == '__main__':\n    run()\n",
    "app/auth.py": "class AuthService:\n    def check(self, user, password):\n        return bool(user) and bool(password)\n\n\ndef login_user(user, password):\n    \"\"\"Log a user in.\"\"\"\n    return AuthService().check(user, password)\n",
    "app/utils.py": "def slugify(text):\n    return text.lower().replace(' ', '-')\n",
    "tests/test_auth.py": "from app.auth import login_user\n\n\ndef test_login():\n    assert login_user('a', 'b')\n",
    "README.md": "# Demo\nA small demo project about authentication.\n",
    ".gitignore": ".env\n__pycache__/\n",
    ".env": "NVIDIA_API_KEY=nvapi-super-secret-value-123456\n",
}


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch, tmp_path):
    monkeypatch.setattr(repository_service, "STATE_FILE", tmp_path / "state.json")
    yield
    repository_service.repositories._active = None


@pytest.fixture()
def repo_dir():
    root = settings.workspace_path
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"demo_{os.urandom(3).hex()}"
    path.mkdir()
    for name, content in FILES.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    repo = Repo.init(path)
    repo.git.add("-A")
    repo.git.execute(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init"])
    return path


@pytest.fixture()
def active(repo_dir):
    return repository_service.repositories._activate(repo_dir, repo_dir.name)
