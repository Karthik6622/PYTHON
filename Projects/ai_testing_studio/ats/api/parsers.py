"""Parsers that turn API definitions into normalised ``ApiEndpoint`` objects.

Supported: OpenAPI 3.x and Swagger 2.0 (JSON or YAML), Postman collection v2.x, manual entry and calls observed in UI discovery.
Everything here is pure (no network, no storage) so it can be unit tested with plain documents.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlparse

from ats.api.models import ApiBody, ApiEndpoint, ApiParam, ApiResponseSpec, ApiSecurity
from ats.errors import GenerationError
from ats.models import HTTP_METHODS, PageSnapshot

MAX_DOCUMENT_BYTES = 8_000_000
MAX_ENDPOINTS = 1500
MAX_REF_DEPTH = 9


@dataclass
class ParsedApi:
    endpoints: list[ApiEndpoint] = field(default_factory=list)
    base_url: str = ""
    title: str = ""
    kind: str = ""
    warnings: list[str] = field(default_factory=list)


# ----------------------------------------------------------------------------------------
# loading
# ----------------------------------------------------------------------------------------
def load_document(text: str) -> dict[str, Any]:
    """Decode JSON, falling back to YAML. Raises ``GenerationError`` with a readable message."""
    if len(text.encode("utf-8", errors="ignore")) > MAX_DOCUMENT_BYTES:
        raise GenerationError("The API definition is too large (limit 8 MB).")
    stripped = text.lstrip("\ufeff \t\r\n")
    data: Any = None
    try:
        data = json.loads(stripped)
    except ValueError:
        try:
            import yaml

            data = yaml.safe_load(stripped)
        except Exception as exc:  # noqa: BLE001 - any parser error means "not a definition"
            raise GenerationError("The file is neither valid JSON nor valid YAML.") from exc
    if not isinstance(data, dict):
        raise GenerationError("The API definition must be a JSON or YAML object.")
    return data


def detect_kind(doc: dict[str, Any]) -> str:
    if str(doc.get("openapi", "")).startswith("3"):
        return "openapi3"
    if str(doc.get("swagger", "")).startswith("2"):
        return "swagger2"
    info = doc.get("info")
    if isinstance(doc.get("item"), list) and (isinstance(info, dict) and ("schema" in info or "_postman_id" in info) or "collection" in doc):
        return "postman"
    if isinstance(doc.get("item"), list) and isinstance(info, dict):
        return "postman"
    return ""


def parse_definition(doc: dict[str, Any]) -> ParsedApi:
    """Parse any supported document, choosing the parser from its content."""
    if isinstance(doc.get("collection"), dict) and detect_kind(doc.get("collection", {})) == "postman":
        doc = doc["collection"]  # Postman API export wraps the collection
    kind = detect_kind(doc)
    if kind in {"openapi3", "swagger2"}:
        return parse_openapi(doc)
    if kind == "postman":
        return parse_postman(doc)
    raise GenerationError("This is not an OpenAPI 3.x, Swagger 2.0 or Postman v2 definition.")


def parse_text(text: str) -> ParsedApi:
    return parse_definition(load_document(text))


# ----------------------------------------------------------------------------------------
# schema helpers
# ----------------------------------------------------------------------------------------
class _Resolver:
    """Expands local ``$ref`` pointers and ``allOf`` (cycle and depth safe) so schemas are self-contained."""

    def __init__(self, doc: dict[str, Any]) -> None:
        self.doc = doc

    def pointer(self, ref: str) -> Any:
        if not ref.startswith("#/"):
            return {}
        node: Any = self.doc
        for part in ref[2:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            if isinstance(node, dict) and part in node:
                node = node[part]
            elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
                node = node[int(part)]
            else:
                return {}
        return node

    def expand(self, node: Any, depth: int = 0, stack: tuple[str, ...] = ()) -> Any:
        if depth > MAX_REF_DEPTH:
            return {}
        if isinstance(node, list):
            return [self.expand(item, depth + 1, stack) for item in node]
        if not isinstance(node, dict):
            return node
        if isinstance(node.get("$ref"), str):
            ref = node["$ref"]
            if ref in stack:
                return {"type": "object", "description": f"recursive reference to {ref.rsplit('/', 1)[-1]}"}
            target = self.expand(self.pointer(ref), depth + 1, (*stack, ref))
            extra = {k: v for k, v in node.items() if k != "$ref"}
            return {**target, **self.expand(extra, depth + 1, stack)} if isinstance(target, dict) and extra else target
        result = {key: self.expand(value, depth + 1, stack) for key, value in node.items() if key != "allOf"}
        if isinstance(node.get("allOf"), list):
            for part in node["allOf"]:
                part = self.expand(part, depth + 1, stack)
                if not isinstance(part, dict):
                    continue
                for key, value in part.items():
                    if key == "properties" and isinstance(value, dict):
                        result.setdefault("properties", {}).update(value)
                    elif key == "required" and isinstance(value, list):
                        result["required"] = sorted({*result.get("required", []), *value})
                    else:
                        result.setdefault(key, value)
            result.setdefault("type", "object")
        return result


def _schema_type(schema: dict[str, Any]) -> str:
    value = schema.get("type")
    if isinstance(value, list):
        value = next((v for v in value if v != "null"), "string")
    if value:
        return str(value)
    if "properties" in schema:
        return "object"
    if "items" in schema:
        return "array"
    return "string"


def example_from_schema(schema: Any, depth: int = 0) -> Any:
    """A plausible, valid example value for a schema (explicit examples win)."""
    if not isinstance(schema, dict) or depth > 6:
        return None
    for key in ("example", "default"):
        if schema.get(key) is not None:
            return schema[key]
    if isinstance(schema.get("examples"), list) and schema["examples"]:
        return schema["examples"][0]
    if schema.get("enum"):
        return schema["enum"][0]
    for combo in ("oneOf", "anyOf"):
        if isinstance(schema.get(combo), list) and schema[combo]:
            return example_from_schema(schema[combo][0], depth + 1)
    kind = _schema_type(schema)
    if kind == "object":
        props = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        return {name: example_from_schema(sub, depth + 1) for name, sub in props.items()}
    if kind == "array":
        item = example_from_schema(schema.get("items"), depth + 1)
        return [] if item is None else [item]
    if kind == "integer":
        return int(schema.get("minimum", 1)) if schema.get("minimum") is not None else 1
    if kind == "number":
        return float(schema.get("minimum", 1.5)) if schema.get("minimum") is not None else 1.5
    if kind == "boolean":
        return True
    fmt = str(schema.get("format", ""))
    return {
        "email": "user@example.com", "date-time": "2024-01-15T10:30:00Z", "date": "2024-01-15", "uuid": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "uri": "https://example.com/resource", "password": "Passw0rd!x", "hostname": "example.com", "ipv4": "192.0.2.10",
    }.get(fmt, "string")


def schema_from_example(value: Any, depth: int = 0) -> dict[str, Any]:
    """A loose JSON schema describing an example (types and required fields only)."""
    if depth > 6:
        return {}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    if isinstance(value, str):
        return {"type": "string"}
    if isinstance(value, list):
        return {"type": "array", "items": schema_from_example(value[0], depth + 1) if value else {}}
    if isinstance(value, dict):
        return {"type": "object", "properties": {k: schema_from_example(v, depth + 1) for k, v in value.items()}, "required": list(value)}
    return {}


def _json_content(content: Any) -> tuple[str, dict[str, Any]]:
    """Pick the preferred media type of an OpenAPI ``content`` map."""
    if not isinstance(content, dict) or not content:
        return "", {}
    for name in content:
        if "json" in name.lower():
            return name, content[name] or {}
    name = next(iter(content))
    return name, content[name] or {}


def _media_example(media: dict[str, Any], schema: dict[str, Any]) -> Any:
    if media.get("example") is not None:
        return media["example"]
    examples = media.get("examples")
    if isinstance(examples, dict) and examples:
        first = next(iter(examples.values()))
        if isinstance(first, dict) and first.get("value") is not None:
            return first["value"]
    return example_from_schema(schema)


# ----------------------------------------------------------------------------------------
# OpenAPI 3.x and Swagger 2.0
# ----------------------------------------------------------------------------------------
def _server_url(doc: dict[str, Any]) -> str:
    servers = doc.get("servers")
    if isinstance(servers, list) and servers and isinstance(servers[0], dict):
        url = str(servers[0].get("url", ""))
        for name, spec in (servers[0].get("variables") or {}).items():
            url = url.replace("{" + name + "}", str((spec or {}).get("default", "")))
        return url.rstrip("/")
    if doc.get("host"):  # Swagger 2.0
        schemes = doc.get("schemes") or ["https"]
        scheme = "https" if "https" in schemes else schemes[0]
        return f"{scheme}://{doc['host']}{doc.get('basePath', '') or ''}".rstrip("/")
    if doc.get("basePath"):
        return str(doc["basePath"]).rstrip("/")
    return ""


def _security_schemes(doc: dict[str, Any], resolver: _Resolver) -> dict[str, dict[str, Any]]:
    raw = (doc.get("components") or {}).get("securitySchemes") or doc.get("securityDefinitions") or {}
    return {name: resolver.expand(spec) for name, spec in raw.items() if isinstance(spec, dict)}


def _security(requirements: Any, schemes: dict[str, dict[str, Any]]) -> list[ApiSecurity]:
    found: list[ApiSecurity] = []
    for requirement in requirements or []:
        if not isinstance(requirement, dict):
            continue
        for name, scopes in requirement.items():
            spec = schemes.get(name, {})
            kind = str(spec.get("type", ""))
            http_scheme = str(spec.get("scheme", "")).lower() if kind == "http" else ("basic" if kind == "basic" else "")
            found.append(
                ApiSecurity(
                    scheme=name, type="http" if kind == "basic" else kind, location=str(spec.get("in", "")), name=str(spec.get("name", "")),
                    http_scheme=http_scheme, scopes=[str(s) for s in scopes or []],
                )
            )
    seen: set[str] = set()
    return [s for s in found if not (s.scheme in seen or seen.add(s.scheme))]


def _parameter(raw: dict[str, Any], resolver: _Resolver, swagger2: bool) -> ApiParam | None:
    param = resolver.expand(raw)
    if not isinstance(param, dict) or not param.get("name"):
        return None
    schema = param.get("schema") if isinstance(param.get("schema"), dict) else {k: v for k, v in param.items() if k in {"type", "format", "enum", "items", "minimum", "maximum", "minLength", "maxLength", "pattern", "default"}}
    example = param.get("example")
    if example is None and isinstance(param.get("examples"), dict) and param["examples"]:
        first = next(iter(param["examples"].values()))
        example = first.get("value") if isinstance(first, dict) else None
    if example is None:
        example = example_from_schema(schema) if schema else None
    return ApiParam(
        name=str(param["name"]), location=str(param.get("in", "query")), required=bool(param.get("required") or param.get("in") == "path"),
        type=_schema_type(schema) if schema else "string", description=str(param.get("description", ""))[:200], example=example, schema=schema,
    )


def parse_openapi(doc: dict[str, Any]) -> ParsedApi:
    resolver = _Resolver(doc)
    swagger2 = str(doc.get("swagger", "")).startswith("2")
    schemes = _security_schemes(doc, resolver)
    global_security = doc.get("security")
    consumes_default = doc.get("consumes") or ["application/json"]
    produces_default = doc.get("produces") or ["application/json"]
    parsed = ParsedApi(base_url=_server_url(doc), title=str((doc.get("info") or {}).get("title", "")), kind="swagger2" if swagger2 else "openapi3")
    paths = doc.get("paths") if isinstance(doc.get("paths"), dict) else {}
    for path, item in paths.items():
        item = resolver.expand(item) if isinstance(item, dict) and "$ref" in item else item
        if not isinstance(item, dict):
            continue
        shared = [p for p in item.get("parameters", []) if isinstance(p, dict)]
        for method in HTTP_METHODS:
            operation = item.get(method.lower())
            if not isinstance(operation, dict):
                continue
            if len(parsed.endpoints) >= MAX_ENDPOINTS:
                parsed.warnings.append(f"Stopped at {MAX_ENDPOINTS} endpoints.")
                return parsed
            params: dict[tuple[str, str], ApiParam] = {}
            body: ApiBody | None = None
            for raw in [*shared, *[p for p in operation.get("parameters", []) if isinstance(p, dict)]]:
                expanded = resolver.expand(raw)
                location = expanded.get("in") if isinstance(expanded, dict) else ""
                if swagger2 and location == "body":
                    schema = expanded.get("schema") if isinstance(expanded.get("schema"), dict) else {}
                    body = ApiBody(content_type=str((operation.get("consumes") or consumes_default)[0]), required=bool(expanded.get("required")), schema=schema, example=example_from_schema(schema))
                    continue
                if swagger2 and location == "formData":
                    props = body.schema_.setdefault("properties", {}) if body else {}
                    body = body or ApiBody(content_type="application/x-www-form-urlencoded", schema={"type": "object", "properties": props})
                    props[str(expanded.get("name"))] = {"type": expanded.get("type", "string")}
                    body.example = example_from_schema(body.schema_)
                    continue
                param = _parameter(raw, resolver, swagger2)
                if param:
                    params[(param.name, param.location)] = param
            if not swagger2 and isinstance(operation.get("requestBody"), dict):
                request = resolver.expand(operation["requestBody"])
                name, media = _json_content(request.get("content"))
                schema = media.get("schema") if isinstance(media.get("schema"), dict) else {}
                body = ApiBody(content_type=name or "application/json", required=bool(request.get("required")), schema=schema, example=_media_example(media, schema))
            responses: list[ApiResponseSpec] = []
            for status, raw_response in (operation.get("responses") or {}).items():
                response = resolver.expand(raw_response)
                if not isinstance(response, dict):
                    continue
                if swagger2:
                    schema = response.get("schema") if isinstance(response.get("schema"), dict) else {}
                    example = (response.get("examples") or {}).get(produces_default[0]) if isinstance(response.get("examples"), dict) else None
                    content_type = str((operation.get("produces") or produces_default)[0]) if schema else ""
                else:
                    content_type, media = _json_content(response.get("content"))
                    schema = media.get("schema") if isinstance(media.get("schema"), dict) else {}
                    example = _media_example(media, schema) if media else None
                responses.append(
                    ApiResponseSpec(
                        status=str(status), description=str(response.get("description", ""))[:200], content_type=content_type, schema=schema,
                        example=example, headers=sorted((response.get("headers") or {}).keys()) if isinstance(response.get("headers"), dict) else [],
                    )
                )
            requirements = operation["security"] if "security" in operation else global_security
            parsed.endpoints.append(
                ApiEndpoint(
                    method=method, path=str(path), summary=str(operation.get("summary") or "")[:200], description=str(operation.get("description") or "")[:600],
                    operation_id=str(operation.get("operationId") or ""), tags=[str(t) for t in operation.get("tags", [])], parameters=list(params.values()),
                    request_body=body, responses=responses, security=_security(requirements, schemes), deprecated=bool(operation.get("deprecated")), source="openapi",
                )
            )
    if not parsed.endpoints:
        parsed.warnings.append("The definition contains no operations.")
    return parsed


# ----------------------------------------------------------------------------------------
# Postman collection v2.x
# ----------------------------------------------------------------------------------------
BASE_VARIABLES = ("baseUrl", "base_url", "baseURL", "base", "host", "url", "apiUrl", "api_url", "server")
POSTMAN_VAR = re.compile(r"\{\{([^{}]+)\}\}")


def _postman_variables(doc: dict[str, Any]) -> dict[str, str]:
    return {str(v.get("key")): str(v.get("value", "")) for v in doc.get("variable", []) if isinstance(v, dict) and v.get("key")}


def _postman_auth(auth: Any) -> list[ApiSecurity]:
    if not isinstance(auth, dict) or not auth.get("type") or auth["type"] == "noauth":
        return []
    kind = str(auth["type"])
    entries = {str(e.get("key")): e.get("value") for e in auth.get(kind, []) if isinstance(e, dict)}
    if kind == "bearer":
        return [ApiSecurity(scheme="bearer", type="http", http_scheme="bearer")]
    if kind == "basic":
        return [ApiSecurity(scheme="basic", type="http", http_scheme="basic")]
    if kind == "apikey":
        return [ApiSecurity(scheme="apikey", type="apiKey", location=str(entries.get("in") or "header"), name=str(entries.get("key") or "X-API-Key"))]
    if kind.startswith("oauth2"):
        return [ApiSecurity(scheme="oauth2", type="oauth2")]
    return [ApiSecurity(scheme=kind, type=kind)]


def _json_or_text(raw: str) -> Any:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        try:
            return json.loads(POSTMAN_VAR.sub(lambda m: json.dumps("{{" + m.group(1) + "}}")[1:-1], text))
        except ValueError:
            return text


def _postman_path(url: Any, variables: dict[str, str]) -> tuple[str, str, list[tuple[str, str, bool]], list[str]]:
    """(path, base_url, query params, path variable names) of a Postman url (string or object)."""
    queries: list[tuple[str, str, bool]] = []
    if isinstance(url, dict):
        raw = str(url.get("raw", ""))
        for item in url.get("query") or []:
            if isinstance(item, dict) and item.get("key"):
                queries.append((str(item["key"]), str(item.get("value") or ""), not item.get("disabled")))
        segments = url.get("path")
        if isinstance(segments, list):
            path = "/" + "/".join(str(s.get("value") if isinstance(s, dict) else s) for s in segments)
        elif isinstance(segments, str):
            path = "/" + segments.strip("/")
        else:
            path = ""
        host = url.get("host")
        host_text = ".".join(host) if isinstance(host, list) else str(host or "")
        if not path and raw:
            path = urlparse(POSTMAN_VAR.sub("x", raw) if "://" in raw else "http://" + POSTMAN_VAR.sub("x", raw)).path
    else:
        raw = str(url or "")
        host_text, path = "", ""
    if not path:
        stripped = raw.split("?")[0]
        stripped = re.sub(r"^\{\{[^{}]+\}\}", "", stripped) if stripped.startswith("{{") else stripped
        parsed = urlparse(stripped if "://" in stripped else "http://placeholder" + (stripped if stripped.startswith("/") else "/" + stripped))
        path = parsed.path or "/"
        if not queries:
            queries = [(k, v, True) for k, v in parse_qsl(urlparse(raw).query, keep_blank_values=True)]
    base = ""
    absolute = re.match(r"^(https?://[^/{}]+)", raw)
    if absolute:
        base = absolute.group(1)
    else:
        match = POSTMAN_VAR.match(raw or host_text)
        if match:
            base = variables.get(match.group(1), "")
    path_vars: list[str] = []

    def colon_param(match: re.Match[str]) -> str:
        path_vars.append(match.group(1))
        return "/{" + match.group(1) + "}"

    path = re.sub(r"/:([A-Za-z_][\w-]*)", colon_param, path)  # :id -> {id}
    path = POSTMAN_VAR.sub(lambda m: "{" + m.group(1).strip() + "}", path)
    path_vars += [n for n in re.findall(r"\{([^{}/]+)\}", path) if n not in path_vars]
    return re.sub(r"/+", "/", path) or "/", base.rstrip("/"), queries, path_vars


def parse_postman(doc: dict[str, Any]) -> ParsedApi:
    variables = _postman_variables(doc)
    base_url = next((variables[name] for name in BASE_VARIABLES if variables.get(name, "").startswith("http")), "")
    parsed = ParsedApi(title=str((doc.get("info") or {}).get("name", "")), kind="postman")
    collection_auth = doc.get("auth")

    def walk(items: list[Any], folders: list[str], inherited: Any) -> None:
        for item in items:
            if not isinstance(item, dict):
                continue
            auth = item.get("auth", inherited)
            if isinstance(item.get("item"), list):
                walk(item["item"], [*folders, str(item.get("name", "")).strip()], auth)
                continue
            request = item.get("request")
            if isinstance(request, str):
                request = {"method": "GET", "url": request}
            if not isinstance(request, dict) or len(parsed.endpoints) >= MAX_ENDPOINTS:
                continue
            path, base, queries, path_vars = _postman_path(request.get("url"), variables)
            if base and not parsed.base_url:
                parsed.base_url = base
            params: list[ApiParam] = [ApiParam(name=name, location="path", required=True, example=variables.get(name) or "1") for name in path_vars]
            params += [ApiParam(name=k, location="query", required=False, example=v or None) for k, v, enabled in queries if enabled]
            content_type = "application/json"
            for header in request.get("header") or []:
                if not isinstance(header, dict) or header.get("disabled") or not header.get("key"):
                    continue
                key = str(header["key"])
                if key.lower() == "content-type":
                    content_type = str(header.get("value") or content_type)
                elif key.lower() not in {"accept", "authorization", "user-agent", "host", "content-length"}:
                    params.append(ApiParam(name=key, location="header", example=str(header.get("value") or "")))
            body = None
            raw_body = request.get("body")
            if isinstance(raw_body, dict) and raw_body.get("mode"):
                mode = raw_body["mode"]
                if mode == "raw":
                    example = _json_or_text(str(raw_body.get("raw", "")))
                    body = ApiBody(content_type=content_type, required=True, schema=schema_from_example(example) if isinstance(example, (dict, list)) else {}, example=example)
                elif mode in {"urlencoded", "formdata"}:
                    fields = {str(f.get("key")): str(f.get("value", "")) for f in raw_body.get(mode, []) if isinstance(f, dict) and f.get("key") and not f.get("disabled")}
                    body = ApiBody(content_type="application/x-www-form-urlencoded" if mode == "urlencoded" else "multipart/form-data", required=True, schema=schema_from_example(fields), example=fields)
                elif mode == "graphql":
                    body = ApiBody(content_type="application/json", required=True, example=raw_body.get("graphql"))
            responses = []
            for example in item.get("response") or []:
                if not isinstance(example, dict):
                    continue
                payload = _json_or_text(str(example.get("body", "")))
                responses.append(
                    ApiResponseSpec(
                        status=str(example.get("code") or "200"), description=str(example.get("status") or example.get("name") or "")[:120],
                        content_type="application/json" if isinstance(payload, (dict, list)) else "", schema=schema_from_example(payload) if isinstance(payload, (dict, list)) else {},
                        example=payload if isinstance(payload, (dict, list)) else None,
                    )
                )
            unique: dict[str, ApiResponseSpec] = {}
            for response in responses:
                unique.setdefault(response.status, response)
            parsed.endpoints.append(
                ApiEndpoint(
                    method=str(request.get("method") or "GET").upper(), path=path, summary=str(item.get("name") or "")[:200], tags=[" / ".join(f for f in folders if f)] if any(folders) else [],
                    parameters=params, request_body=body, responses=list(unique.values()), security=_postman_auth(auth), source="postman",
                )
            )

    walk(doc.get("item") or [], [], collection_auth)
    if not parsed.base_url:
        parsed.base_url = base_url
    if not parsed.endpoints:
        parsed.warnings.append("The collection contains no requests.")
    return parsed


# ----------------------------------------------------------------------------------------
# observed traffic and manual entry
# ----------------------------------------------------------------------------------------
_ID_SEGMENT = re.compile(r"^(\d+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{16,})$", re.I)
_STATIC = re.compile(r"\.(js|css|png|jpe?g|gif|svg|ico|woff2?|ttf|map|html?)$", re.I)


def parse_observed(pages: list[PageSnapshot], app_url: str = "", include_external: bool = False) -> ParsedApi:
    """Endpoints seen as fetch/xhr calls while the UI was explored. Numeric and UUID path segments become ``{id}`` parameters."""
    app_host = (urlparse(app_url).hostname or "").lower()
    seen: dict[str, ApiEndpoint] = {}
    hosts: dict[str, int] = {}
    for page in pages:
        for call in page.network:
            url, method = str(call.get("url", "")), str(call.get("method", "GET")).upper()
            parsed = urlparse(url)
            if not parsed.hostname or method not in HTTP_METHODS or _STATIC.search(parsed.path):
                continue
            if not include_external and app_host and (parsed.hostname or "").lower() != app_host:
                continue
            origin = f"{parsed.scheme}://{parsed.netloc}"
            hosts[origin] = hosts.get(origin, 0) + 1
            counter = 0
            segments: list[str] = []
            params: list[ApiParam] = []
            for segment in [s for s in parsed.path.split("/") if s]:
                if _ID_SEGMENT.match(segment):
                    counter += 1
                    name = "id" if counter == 1 else f"id{counter}"
                    segments.append("{" + name + "}")
                    params.append(ApiParam(name=name, location="path", required=True, example=segment))
                else:
                    segments.append(segment)
            path = "/" + "/".join(segments)
            endpoint = seen.get(f"{method} {path}")
            status = str(call.get("status") or "")
            if endpoint is None:
                endpoint = ApiEndpoint(method=method, path=path, summary="Observed while exploring the UI", tags=[segments[0] if segments and not segments[0].startswith("{") else "observed"], parameters=params, source="observed")
                seen[endpoint.key] = endpoint
            if status and all(r.status != status for r in endpoint.responses):
                endpoint.responses.append(ApiResponseSpec(status=status, description="seen in the browser"))
    base = max(hosts, key=hosts.get) if hosts else ""
    result = ParsedApi(endpoints=list(seen.values()), base_url=base, kind="observed")
    if not result.endpoints:
        result.warnings.append("No fetch/XHR calls were recorded during discovery.")
    return result


def manual_endpoint(
    method: str, path: str, summary: str = "", tags: str = "", query: str = "", body: str = "", success_status: str = "", auth_scheme: str = ""
) -> ApiEndpoint:
    """Build an endpoint from the manual form. ``query`` is one ``name=value`` per line, ``body`` an example JSON document."""
    if not path.strip():
        raise GenerationError("Enter the endpoint path, for example /users/{id}.")
    params = [ApiParam(name=name, location="path", required=True, example="1") for name in re.findall(r"\{([^{}/]+)\}", path)]
    for line in query.splitlines():
        name, _, value = line.partition("=")
        if name.strip():
            params.append(ApiParam(name=name.strip(), location="query", example=value.strip() or None))
    request_body = None
    if body.strip():
        try:
            example = json.loads(body)
        except ValueError as exc:
            raise GenerationError("The sample body must be valid JSON.") from exc
        request_body = ApiBody(content_type="application/json", required=True, schema=schema_from_example(example), example=example)
    responses = [ApiResponseSpec(status=success_status.strip(), description="expected success status")] if success_status.strip() else []
    security = [ApiSecurity(scheme=auth_scheme, type="http", http_scheme="bearer")] if auth_scheme.strip() else []
    return ApiEndpoint(
        method=method, path=path.strip(), summary=summary.strip(), tags=tags, parameters=params, request_body=request_body, responses=responses, security=security, source="manual"
    )
