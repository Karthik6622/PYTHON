import requests
import base64
import json
from typing import Any, Dict, List, Optional


class GitHubFolderFetcher:
    """
    Fetches all files from a GitHub repository folder (recursively)
    and returns their contents as a structured JSON object.
    """

    def __init__(self, token: str, owner: str, repo: str, branch: str = "main"):
        self.token   = token
        self.owner   = owner
        self.repo    = repo
        self.branch  = branch
        self.api_url = f"https://api.github.com/repos/{owner}/{repo}/contents"
        self.headers = {
            "Authorization": f"token {token}",
            "Accept":        "application/vnd.github.v3+json",
        }

    # ─────────────────────────────────────────────────────────────────
    # INTERNAL HELPERS
    # ─────────────────────────────────────────────────────────────────

    def _get(self, path: str) -> Any:
        """GET a GitHub contents API path and return parsed JSON."""
        url    = f"{self.api_url}/{path}".rstrip("/")
        params = {"ref": self.branch}
        resp   = requests.get(url, headers=self.headers, params=params, timeout=30)

        if resp.status_code == 404:
            raise FileNotFoundError(
                f"Path '{path}' not found in {self.owner}/{self.repo}@{self.branch}"
            )
        resp.raise_for_status()
        return resp.json()

    def _decode_file(self, item: Dict) -> Optional[str]:
        """Base64-decode a file's content returned by the GitHub API."""
        raw = item.get("content", "")
        if not raw:
            return None
        try:
            return base64.b64decode(raw.replace("\n", "")).decode("utf-8")
        except Exception:
            # Binary file — return base64 as-is
            return raw.strip()

    def _fetch_recursive(self, folder_path: str) -> List[Dict]:
        """
        Recursively walk a folder and return a flat list of file records.
        Each record: { name, path, size_bytes, sha, download_url, content }
        """
        items   = self._get(folder_path)
        results = []

        if not isinstance(items, list):
            items = [items]

        for item in items:
            item_type = item.get("type")
            item_path = item.get("path", "")
            item_name = item.get("name", "")

            if item_type == "file":
                print(f"  [FILE] Fetching: {item_path}")
                file_data    = self._get(item_path)
                file_content = self._decode_file(file_data)

                results.append({
                    "name":         item_name,
                    "path":         item_path,
                    "size_bytes":   item.get("size", 0),
                    "sha":          item.get("sha", ""),
                    "download_url": item.get("download_url", ""),
                    "content":      file_content,
                })

            elif item_type == "dir":
                print(f"  [DIR]  Entering: {item_path}/")
                results.extend(self._fetch_recursive(item_path))

        return results

    # ─────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ─────────────────────────────────────────────────────────────────

    def fetch_folder(self, folder_path: str = "") -> Dict:
        """
        Fetch all files under `folder_path` in the repository.

        Args:
            folder_path: Relative path inside the repo (e.g. "PYTHON").
                         Pass "" to fetch from the repo root.

        Returns a dict with repository info and a list of file records.
        """
        folder_path = folder_path.strip("/")
        print(f"\n[GO] Fetching files from '{self.owner}/{self.repo}' "
              f"folder='{folder_path or '(root)'}' branch='{self.branch}'")
        print("-" * 60)

        files = self._fetch_recursive(folder_path)

        result = {
            "repository":  f"{self.owner}/{self.repo}",
            "branch":      self.branch,
            "folder":      folder_path or "(root)",
            "total_files": len(files),
            "files":       files,
        }

        print("-" * 60)
        print(f"[OK] Done. {len(files)} file(s) fetched.\n")
        return result

    def fetch_folder_as_json(self, folder_path: str = "", indent: int = 2) -> str:
        """Same as fetch_folder() but returns a formatted JSON string."""
        return json.dumps(self.fetch_folder(folder_path), indent=indent, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":

    # ── Credentials ──────────────────────────────────────────────────
    TOKEN  = "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"
    OWNER  = "Karthik6622"
    BRANCH = "main"

    # ── User inputs ───────────────────────────────────────────────────
    print("=" * 60)
    print("       GitHub Folder Fetcher")
    print("=" * 60)

    REPO = input("Enter repository name (e.g. PYTHON): ").strip()
    if not REPO:
        raise ValueError("Repository name cannot be empty.")

    FOLDER_PATH = input("Enter folder path inside the repo (e.g. PYTHON): ").strip()
    if not FOLDER_PATH:
        raise ValueError("Folder path cannot be empty. Please enter a valid folder path.")

    # ── Fetch ─────────────────────────────────────────────────────────
    fetcher = GitHubFolderFetcher(
        token  = TOKEN,
        owner  = OWNER,
        repo   = REPO,
        branch = BRANCH,
    )

    output_json = fetcher.fetch_folder_as_json(folder_path=FOLDER_PATH)
    print(output_json)

    # ── Save to file ──────────────────────────────────────────────────
    safe_folder = FOLDER_PATH.replace("/", "_")
    output_file = f"{REPO}_{safe_folder}_contents.json"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(output_json)
    print(f"\n[SAVED] Output written to: {output_file}")
