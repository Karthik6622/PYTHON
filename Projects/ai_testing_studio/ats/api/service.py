"""API sources of a project: import definitions, keep the normalised endpoints, resolve the base URL."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

from ats.api.fetch import fetch_text
from ats.api.models import ApiEndpoint
from ats.api.parsers import ParsedApi, load_document, manual_endpoint, parse_definition, parse_observed
from ats.config import get_settings
from ats.errors import GenerationError
from ats.progress import report
from ats.repository import Project, Repository
from ats.security import UnsafeURLError, validate_target_url


class ApiService:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    # ------------------------------------------------------------------ reading
    def endpoints(self, project_id: str) -> list[ApiEndpoint]:
        return self.repo.list_api_endpoints(project_id)

    def grouped(self, project_id: str) -> dict[str, list[ApiEndpoint]]:
        groups: dict[str, list[ApiEndpoint]] = {}
        for endpoint in self.endpoints(project_id):
            groups.setdefault(endpoint.tag, []).append(endpoint)
        return dict(sorted(groups.items()))

    # ------------------------------------------------------------------ base URL
    def set_base_url(self, project: Project, raw: str) -> str:
        """Store the address API tests send requests to ('' clears it: the application's own address is used)."""
        value = raw.strip().rstrip("/")
        if value:
            try:
                value = validate_target_url(value, get_settings().allow_private_network).rstrip("/")
            except UnsafeURLError as exc:
                raise GenerationError(str(exc)) from exc
        self.repo.update_project(project.id, api_base_url=value)
        self.repo.audit(project.id, "user", "api.base_url", "api", {"url": value})
        return value

    def _adopt_base_url(self, project: Project, parsed: ParsedApi, source_url: str, warnings: list[str]) -> str:
        """Use the base URL a definition declares when the project has none yet."""
        declared = parsed.base_url.strip()
        if not declared or project.api_base_url:
            return ""
        if declared.startswith("/") and source_url:
            declared = urljoin(source_url, declared)
        try:
            return self.set_base_url(project, declared)
        except GenerationError as exc:
            warnings.append(f"The server address in the definition was not used: {exc.user_message}")
            return ""

    # ------------------------------------------------------------------ importing
    def _store(self, project: Project, parsed: ParsedApi, source: str, replace: bool, source_url: str = "") -> dict[str, Any]:
        if not parsed.endpoints:
            raise GenerationError("; ".join(parsed.warnings) or "No endpoints were found in the definition.")
        before = {e.key for e in self.endpoints(project.id)}
        self.repo.save_api_endpoints(project.id, parsed.endpoints, replace_source=source if replace else None)
        warnings = list(parsed.warnings)
        base = self._adopt_base_url(project, parsed, source_url, warnings)
        fresh = {e.key for e in parsed.endpoints}
        self.repo.audit(project.id, "user", "api.imported", "api", {"source": source, "endpoints": len(fresh), "title": parsed.title[:80]})
        return {
            "count": len(fresh), "added": len(fresh - before), "updated": len(fresh & before), "base_url": base or project.api_base_url or parsed.base_url,
            "title": parsed.title, "kind": parsed.kind, "warnings": warnings,
        }

    def import_document(self, project: Project, text: str, source_url: str = "", replace: bool = True) -> dict[str, Any]:
        """Import OpenAPI 3.x / Swagger 2.0 (JSON or YAML) or a Postman v2 collection from text."""
        parsed = parse_definition(load_document(text))
        source = "postman" if parsed.kind == "postman" else "openapi"
        return self._store(project, parsed, source, replace, source_url)

    def import_url(self, project: Project, url: str, replace: bool = True, progress: Any = None) -> dict[str, Any]:
        report(progress, "Downloading the API definition", 0.1, 0.5)
        text, final_url = fetch_text(url, verify=not project.limits.ignore_https_errors)
        report(progress, "Reading the endpoints", 0.6)
        result = self.import_document(project, text, final_url, replace)
        report(progress, f"Imported {result['count']} endpoints", 0.95)
        return result

    def import_observed(self, project: Project, include_external: bool = False) -> dict[str, Any]:
        discovery = self.repo.latest_successful_discovery(project.id)
        if discovery is None:
            raise GenerationError("Run website discovery first; observed calls come from it.")
        parsed = parse_observed(discovery.pages, project.url, include_external)
        return self._store(project, parsed, "observed", True)

    def observed_preview(self, project: Project) -> int:
        discovery = self.repo.latest_successful_discovery(project.id)
        return len(parse_observed(discovery.pages, project.url).endpoints) if discovery else 0

    def add_manual(self, project: Project, **fields: Any) -> ApiEndpoint:
        endpoint = manual_endpoint(
            fields.get("method", "GET"), fields.get("path", ""), fields.get("summary", ""), fields.get("tags", ""), fields.get("query", ""),
            fields.get("body", ""), fields.get("success_status", ""), fields.get("auth_scheme", ""),
        )
        self.repo.save_api_endpoints(project.id, [endpoint])
        self.repo.audit(project.id, "user", "api.endpoint_added", "api", {"endpoint": endpoint.key})
        return endpoint

    # ------------------------------------------------------------------ deleting
    def delete(self, project_id: str, keys: list[str] | None = None) -> int:
        """Delete the given endpoints (all when ``keys`` is None). Returns how many were removed."""
        count = len(self.endpoints(project_id)) if keys is None else len(keys)
        self.repo.delete_api_endpoints(project_id, keys)
        self.repo.audit(project_id, "user", "api.deleted", "api", {"count": count})
        return count
