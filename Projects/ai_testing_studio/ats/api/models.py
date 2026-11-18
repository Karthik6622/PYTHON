"""Normalised description of an API endpoint, whatever the source (OpenAPI, Swagger, Postman, manual, observed traffic)."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ConfigDict, Field, field_validator

from ats.models import HTTP_METHODS, _Model

SOURCES = {"openapi": "OpenAPI / Swagger", "postman": "Postman collection", "manual": "Entered manually", "observed": "Observed in the UI"}
_ALIASED = ConfigDict(extra="ignore", str_strip_whitespace=True, populate_by_name=True)


class ApiParam(_Model):
    model_config = _ALIASED

    name: str
    location: str = "query"  # path | query | header | cookie
    required: bool = False
    type: str = "string"
    description: str = ""
    example: Any = None
    schema_: dict[str, Any] = Field(default_factory=dict, alias="schema")


class ApiBody(_Model):
    model_config = _ALIASED

    content_type: str = "application/json"
    required: bool = False
    schema_: dict[str, Any] = Field(default_factory=dict, alias="schema")
    example: Any = None


class ApiResponseSpec(_Model):
    model_config = _ALIASED

    status: str = "200"  # "200", "404", "default"
    description: str = ""
    content_type: str = ""
    schema_: dict[str, Any] = Field(default_factory=dict, alias="schema")
    example: Any = None
    headers: list[str] = Field(default_factory=list)


class ApiSecurity(_Model):
    scheme: str  # name of the security scheme in the definition
    type: str = ""  # apiKey | http | oauth2 | openIdConnect | basic
    location: str = ""  # header | query | cookie (apiKey)
    name: str = ""  # header or query parameter name (apiKey)
    http_scheme: str = ""  # bearer | basic
    scopes: list[str] = Field(default_factory=list)


class ApiEndpoint(_Model):
    key: str = ""  # "GET /users/{id}" - unique inside a project
    method: str = "GET"
    path: str = "/"
    summary: str = ""
    description: str = ""
    operation_id: str = ""
    tags: list[str] = Field(default_factory=list)
    parameters: list[ApiParam] = Field(default_factory=list)
    request_body: ApiBody | None = None
    responses: list[ApiResponseSpec] = Field(default_factory=list)
    security: list[ApiSecurity] = Field(default_factory=list)
    deprecated: bool = False
    source: str = "manual"

    @field_validator("method", mode="before")
    @classmethod
    def _method(cls, value: Any) -> str:
        text = str(value or "GET").strip().upper()
        return text if text in HTTP_METHODS else "GET"

    @field_validator("path", mode="before")
    @classmethod
    def _path(cls, value: Any) -> str:
        text = str(value or "/").strip() or "/"
        return text if text.startswith("/") else "/" + text

    @field_validator("tags", mode="before")
    @classmethod
    def _tags(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return [t.strip() for t in value.split(",") if t.strip()]
        return [str(t) for t in value or []]

    def model_post_init(self, __context: Any) -> None:
        self.key = f"{self.method} {self.path}"

    @property
    def tag(self) -> str:
        return self.tags[0] if self.tags else "untagged"


def endpoint_digest(endpoints: list[ApiEndpoint], max_items: int = 60, body_chars: int = 600) -> list[dict[str, Any]]:
    """Compact, model-friendly view of the endpoints (schemas trimmed, examples kept short)."""
    out: list[dict[str, Any]] = []
    for endpoint in endpoints[:max_items]:
        item: dict[str, Any] = {"endpoint": endpoint.key, "summary": endpoint.summary or endpoint.operation_id, "tags": endpoint.tags}
        if endpoint.deprecated:
            item["deprecated"] = True
        params = [
            {k: v for k, v in {"name": p.name, "in": p.location, "required": p.required or None, "type": p.type, "example": p.example}.items() if v not in (None, "")}
            for p in endpoint.parameters
        ]
        if params:
            item["parameters"] = params
        if endpoint.request_body:
            body = endpoint.request_body
            item["request_body"] = {"content_type": body.content_type, "required": body.required, "schema": _short(body.schema_, body_chars), "example": _short(body.example, body_chars)}
        item["responses"] = [
            {k: v for k, v in {"status": r.status, "description": r.description[:80], "content_type": r.content_type, "schema": _short(r.schema_, body_chars)}.items() if v}
            for r in endpoint.responses
        ]
        if endpoint.security:
            item["security"] = [{k: v for k, v in {"scheme": s.scheme, "type": s.type, "in": s.location, "name": s.name, "http_scheme": s.http_scheme}.items() if v} for s in endpoint.security]
        out.append(item)
    return out


def _short(value: Any, limit: int) -> Any:
    if not value:
        return None
    text = json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
    return value if len(text) <= limit else text[:limit] + "...[trimmed]"


def path_placeholders(path: str) -> list[str]:
    return re.findall(r"\{([^{}/]+)\}", path)
