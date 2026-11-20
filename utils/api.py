"""API test runtime: sends requests, substitutes saved values and secrets, checks expectations and writes masked evidence.

Generated tests call ``api.step(...)`` and ``api.send({...})``. Nothing in this file (or in the tests) contains a credential: connections
are described by environment-variable NAMES in config/api.json and the values are read from the environment at run time.
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

ROOT = Path(__file__).resolve().parent.parent
VAR_PATTERN = re.compile(r"\{\{\s*var\.([^{}\s]+)\s*\}\}")
ENV_PATTERN = re.compile(r"\{\{\s*env:([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
SENSITIVE_KEY = re.compile(r"(?i)^(.*[-_.])?(pass(word|wd)?|secret|token|api[-_]?key|apikey|authorization|cookie|set-cookie|credentials?)$")
SECRETISH_VARIABLE = re.compile(r"(?i)(token|secret|password|passwd|key|auth|credential)")
BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/\-]{8,}=*")
MAX_BODY_CHARS = 4000
_TOKEN_CACHE: dict[str, tuple[str, float]] = {}


class ApiTestError(AssertionError):
    """A failed expectation or an unusable request. ``kind`` tells why: assertion, connection, timeout, credentials, variable, automation."""

    def __init__(self, message: str, kind: str = "assertion", problems: list[str] | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.problems = problems or [message]


# ----------------------------------------------------------------------------------------
# masking
# ----------------------------------------------------------------------------------------
class Masker:
    """Hides every secret value this session has seen (environment values, tokens) and credential-looking keys in evidence."""

    def __init__(self) -> None:
        self.secrets: set[str] = set()

    def add(self, value: Any) -> None:
        text = str(value) if value is not None else ""
        if len(text) >= 4:
            self.secrets.add(text)

    def text(self, value: str) -> str:
        for secret in sorted(self.secrets, key=len, reverse=True):
            value = value.replace(secret, "***")
        return BEARER.sub("Bearer ***", value)

    def obj(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, dict):
            return {k: ("***" if SENSITIVE_KEY.match(str(k)) and v not in (None, "", False) else self.obj(v)) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.obj(v) for v in value]
        return value


# ----------------------------------------------------------------------------------------
# JSON path
# ----------------------------------------------------------------------------------------
_TOKEN = re.compile(r"""\[\s*(\*|-?\d+)\s*\]|\[\s*'([^']*)'\s*\]|\[\s*"([^"]*)"\s*\]|\.?([^.\[\]]+)""")


def parse_path(path: str) -> list[str | int]:
    """Tokens of a JSON path: ``$.a.b[0]``, ``a.b.0`` and ``$['a']`` are all accepted; ``[*]`` is the wildcard."""
    text = (path or "").strip()
    if text.startswith("$"):
        text = text[1:]
    tokens: list[str | int] = []
    for match in _TOKEN.finditer(text):
        index, single, double, name = match.groups()
        if index is not None:
            tokens.append("*" if index == "*" else int(index))
        elif single is not None or double is not None:
            tokens.append(single if single is not None else double)
        elif name:
            tokens.append(name)
    return tokens


def json_path(data: Any, path: str) -> tuple[bool, Any]:
    """``(found, value)``. A wildcard returns the list of matches (found when at least one element matched)."""
    return _walk(data, parse_path(path))


def _walk(node: Any, tokens: list[str | int]) -> tuple[bool, Any]:
    if not tokens:
        return True, node
    head, rest = tokens[0], tokens[1:]
    if head == "*":
        if not isinstance(node, list):
            return False, None
        results = [value for ok, value in (_walk(item, rest) for item in node) if ok]
        return bool(results) or not node, results
    if isinstance(node, list):
        index = head if isinstance(head, int) else int(head) if str(head).lstrip("-").isdigit() else None
        if index is None or not -len(node) <= index < len(node):
            return False, None
        return _walk(node[index], rest)
    if isinstance(node, dict) and str(head) in node:
        return _walk(node[str(head)], rest)
    return False, None


# ----------------------------------------------------------------------------------------
# substitution
# ----------------------------------------------------------------------------------------
def _text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return "" if value is None else str(value)


def _lookup_var(path: str, variables: dict[str, Any]) -> Any:
    found, value = json_path(variables, "$." + path)
    if not found:
        tokens = parse_path(path)
        name = tokens[0] if tokens else path
        raise ApiTestError(f"Variable '{name}' is not available: no earlier request saved it (or the saved value has no '{path}')", kind="automation")
    return value


def _lookup_env(name: str, masker: Masker | None) -> str:
    if name not in os.environ:
        raise ApiTestError(f"Environment variable {name} is not set", kind="variable")
    if masker is not None:
        masker.add(os.environ[name])
    return os.environ[name]


def substitute(value: Any, variables: dict[str, Any], masker: Masker | None = None) -> Any:
    """Replace ``{{var.name}}`` (value saved by an earlier request) and ``{{env:NAME}}`` (environment) anywhere inside ``value``.

    A string that is exactly one ``{{var...}}`` placeholder keeps the saved value's type (an id stays a number)."""
    if isinstance(value, str):
        whole = VAR_PATTERN.fullmatch(value.strip())
        if whole:
            return _lookup_var(whole.group(1), variables)
        text = VAR_PATTERN.sub(lambda m: _text(_lookup_var(m.group(1), variables)), value)
        return ENV_PATTERN.sub(lambda m: _lookup_env(m.group(1), masker), text)
    if isinstance(value, list):
        return [substitute(item, variables, masker) for item in value]
    if isinstance(value, dict):
        return {key: substitute(item, variables, masker) for key, item in value.items()}
    return value


# ----------------------------------------------------------------------------------------
# assertions
# ----------------------------------------------------------------------------------------
def type_of(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def _same(actual: Any, expected: Any) -> bool:
    if isinstance(actual, bool) or isinstance(expected, bool):
        return isinstance(actual, bool) and isinstance(expected, bool) and actual == expected
    if actual == expected:
        return True
    numeric = (int, float)
    if isinstance(actual, numeric) and isinstance(expected, str) or isinstance(expected, numeric) and isinstance(actual, str):
        return str(actual) == str(expected)  # an id written as "5" matches 5
    return False


def _show(value: Any, limit: int = 120) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str) if not isinstance(value, str) else repr(value)
    return text if len(text) <= limit else text[:limit] + "..."


def check_value(op: str, found: bool, actual: Any, expected: Any) -> str:
    """Empty string when the check holds, otherwise a clear message about what was found."""
    if op == "exists":
        if expected is False:
            return "" if not found else "is present but must be absent"
        return "" if found else "is missing"
    if not found:
        return "is missing"
    if op == "equals":
        return "" if _same(actual, expected) else f"is {_show(actual)}, expected {_show(expected)}"
    if op == "type":
        wanted = expected if isinstance(expected, list) else [expected]
        if type_of(actual) in wanted or (type_of(actual) == "integer" and "number" in wanted):
            return ""
        return f"is {type_of(actual)} ({_show(actual)}), expected {' or '.join(map(str, wanted))}"
    if op == "matches":
        return "" if re.search(str(expected), _text(actual)) else f"is {_show(actual)}, which does not match /{expected}/"
    if op == "contains":
        if isinstance(actual, str):
            return "" if str(expected) in actual else f"is {_show(actual)}, which does not contain {_show(expected)}"
        if isinstance(actual, (list, tuple)):
            return "" if any(_same(item, expected) for item in actual) else f"{_show(actual)} does not contain {_show(expected)}"
        if isinstance(actual, dict):
            return "" if str(expected) in actual else f"has no key {_show(expected)}"
        return f"is {_show(actual)} and cannot contain anything"
    if op in ("gt", "lt"):
        try:
            number, limit = float(actual), float(expected)
        except (TypeError, ValueError):
            return f"is {_show(actual)}, which is not a number"
        good = number > limit if op == "gt" else number < limit
        return "" if good else f"is {_show(actual)}, expected {'greater' if op == 'gt' else 'less'} than {_show(expected)}"
    return f"uses the unknown check '{op}'"


def normalize_schema(schema: Any) -> Any:
    """JSON Schema as ``jsonschema`` understands it: OpenAPI 3.0 ``nullable`` and boolean ``exclusiveMinimum/Maximum`` are translated."""
    if isinstance(schema, list):
        return [normalize_schema(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    dropped = {"discriminator", "xml", "externalDocs", "example", "examples", "readOnly", "writeOnly", "deprecated"}
    result = {key: normalize_schema(value) for key, value in schema.items() if key not in dropped}
    if result.pop("nullable", False) is True:
        kind = result.get("type")
        if isinstance(kind, str):
            result["type"] = [kind, "null"]
        elif isinstance(kind, list) and "null" not in kind:
            result["type"] = [*kind, "null"]
        if "enum" in result and None not in result["enum"]:
            result["enum"] = [*result["enum"], None]
    for flag, limit in (("exclusiveMinimum", "minimum"), ("exclusiveMaximum", "maximum")):
        if isinstance(result.get(flag), bool):
            if result.pop(flag) and limit in result:
                result[flag] = result.pop(limit)
    return result


def schema_problems(schema: dict[str, Any], instance: Any, limit: int = 4) -> list[str]:
    try:
        import jsonschema
    except ImportError as exc:  # pragma: no cover - requirements.txt installs it
        raise ApiTestError("The 'jsonschema' package is not installed (pip install -r requirements.txt)", kind="automation") from exc
    schema = normalize_schema(schema)
    validator = jsonschema.validators.validator_for(schema)(schema)
    problems = []
    for error in sorted(validator.iter_errors(instance), key=lambda e: list(map(str, e.absolute_path)))[:limit]:
        where = "$" + "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in error.absolute_path)
        problems.append(f"{where}: {error.message[:200]}")
    return problems


# ----------------------------------------------------------------------------------------
# configuration and helpers
# ----------------------------------------------------------------------------------------
def load_config() -> dict[str, Any]:
    path = ROOT / "config" / "api.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _media_equal(actual: str, expected: str) -> bool:
    a, e = actual.strip().lower(), expected.strip().lower()
    return a == e or a.startswith(e + ";") or a.startswith(e + " ")


def _maybe_json(text: str) -> Any:
    if not text:
        return ""
    try:
        return json.loads(text)
    except ValueError:
        return text


def substitute_expect(expect: dict[str, Any], variables: dict[str, Any], masker: Masker | None = None) -> dict[str, Any]:
    """Expected values may use ``{{var.name}}`` (for example the name returned by the create request)."""
    result = dict(expect)
    result["json"] = [{**c, "value": substitute(c.get("value"), variables, masker)} for c in expect.get("json") or []]
    result["headers"] = substitute(expect.get("headers") or {}, variables, masker)
    return result


class ApiSession:
    """One test case's HTTP client, saved variables and evidence."""

    def __init__(self, test_case_id: str) -> None:
        self.test_case_id = test_case_id
        self.config = load_config()
        self.base_url = (os.environ.get("API_BASE_URL") or os.environ.get("BASE_URL") or self.config.get("base_url") or "").rstrip("/")
        self.timeout = float(os.environ.get("API_TIMEOUT") or self.config.get("timeout") or 30)
        self.variables: dict[str, Any] = {}
        self.steps: list[dict[str, Any]] = []
        self.exchanges: list[dict[str, Any]] = []
        self.failure: dict[str, Any] = {}
        self.masker = Masker()
        self.client = httpx.Client(
            timeout=self.timeout, follow_redirects=False, verify=os.environ.get("IGNORE_HTTPS_ERRORS") != "1", transport=httpx.HTTPTransport(retries=0)
        )

    def close(self) -> None:
        self.client.close()

    # ------------------------------------------------------------------ steps
    @contextmanager
    def step(self, description: str, method: str = "", path: str = ""):
        record = {"index": len(self.steps) + 1, "description": description, "action": "request", "element": f"{method} {path}".strip(), "status": "running"}
        self.steps.append(record)
        try:
            yield
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = self.masker.text(str(exc))[:1500]
            self.failure.update({"step": record["index"], "action": "request", "element": "", "error": record["error"], "kind": getattr(exc, "kind", "assertion")})
            raise
        else:
            record["status"] = "passed"

    # ------------------------------------------------------------------ authentication
    def _env(self, name: str) -> str:
        if not name or name not in os.environ:
            raise ApiTestError(f"Environment variable {name or '(unnamed)'} is not set", kind="variable")
        self.masker.add(os.environ[name])
        return os.environ[name]

    def _oauth_token(self, name: str, descriptor: dict[str, Any]) -> str:
        cached = _TOKEN_CACHE.get(name)
        if cached and cached[1] > time.time() + 30:
            self.masker.add(cached[0])
            return cached[0]
        url = self._env(descriptor.get("token_url_env", ""))
        client_id, client_secret = self._env(descriptor.get("client_id_env", "")), self._env(descriptor.get("client_secret_env", ""))
        data = {"grant_type": "client_credentials"}
        scope = os.environ.get(descriptor.get("scope_env") or "-", "")
        if scope:
            data["scope"] = scope
        headers = {"Accept": "application/json"}
        if descriptor.get("auth_style") == "basic":
            headers["Authorization"] = "Basic " + base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        else:
            data.update({"client_id": client_id, "client_secret": client_secret})
        try:
            response = self.client.post(url, data=data, headers=headers)
        except httpx.HTTPError as exc:
            raise ApiTestError(f"Could not reach the OAuth2 token endpoint of connection '{name}' ({type(exc).__name__})", kind="connection") from exc
        if response.status_code >= 400:
            raise ApiTestError(f"Could not obtain an OAuth2 token for connection '{name}': the token endpoint answered HTTP {response.status_code}", kind="credentials")
        try:
            body = response.json()
            token = str(body["access_token"])
        except (ValueError, KeyError, TypeError) as exc:
            raise ApiTestError(f"The token endpoint of connection '{name}' did not return an access_token", kind="credentials") from exc
        self.masker.add(token)
        try:
            lifetime = float(body.get("expires_in", 300))
        except (TypeError, ValueError):
            lifetime = 300.0
        _TOKEN_CACHE[name] = (token, time.time() + lifetime)
        return token

    def _apply_auth(self, name: str, headers: dict[str, str], params: dict[str, Any]) -> None:
        descriptor = (self.config.get("connections") or {}).get(name)
        if descriptor is None:
            raise ApiTestError(f"Connection '{name}' is not configured for this project: save it on the Connections page, then run again", kind="credentials")
        kind = descriptor.get("type")
        if kind == "api_key":
            value = self._env(descriptor.get("env", ""))
            if descriptor.get("in") == "query":
                params.setdefault(descriptor.get("name") or "api_key", value)
            else:
                headers.setdefault(descriptor.get("name") or "X-API-Key", value)
        elif kind == "bearer":
            headers.setdefault("Authorization", f"Bearer {self._env(descriptor.get('env', ''))}")
        elif kind == "basic":
            pair = f"{self._env(descriptor.get('username_env', ''))}:{self._env(descriptor.get('password_env', ''))}"
            encoded = base64.b64encode(pair.encode()).decode()
            self.masker.add(encoded)
            headers.setdefault("Authorization", f"Basic {encoded}")
        elif kind == "oauth2":
            headers.setdefault("Authorization", f"Bearer {self._oauth_token(name, descriptor)}")
        else:
            raise ApiTestError(f"Connection '{name}' has type '{kind}', which cannot authenticate a request", kind="credentials")

    # ------------------------------------------------------------------ sending
    def _build(self, spec: dict[str, Any]) -> httpx.Request:
        if not self.base_url:
            raise ApiTestError("The API base URL is not set: set API_BASE_URL (or BASE_URL)", kind="variable")
        path = str(spec.get("path") or "/")
        for key, value in substitute(spec.get("path_params") or {}, self.variables, self.masker).items():
            path = path.replace("{" + key + "}", quote(_text(value), safe=""))
        path = substitute(path, self.variables, self.masker)
        left = re.findall(r"\{([^{}/]+)\}", path)
        if left:
            raise ApiTestError(f"Path parameter '{left[0]}' has no value for {spec.get('method', 'GET')} {spec.get('path')}", kind="automation")
        query = {k: v for k, v in substitute(spec.get("query") or {}, self.variables, self.masker).items() if v is not None}
        headers = {str(k): _text(v) for k, v in substitute(spec.get("headers") or {}, self.variables, self.masker).items()}
        headers.setdefault("Accept", "application/json")
        if spec.get("auth"):
            self._apply_auth(str(spec["auth"]), headers, query)
        kwargs: dict[str, Any] = {"params": query, "headers": headers}
        body = substitute(spec.get("body"), self.variables, self.masker)
        if body is not None:
            content_type = next((v for k, v in headers.items() if k.lower() == "content-type"), "application/json")
            if "x-www-form-urlencoded" in content_type and isinstance(body, dict):
                kwargs["data"] = body
            elif isinstance(body, (dict, list)) or "json" in content_type:
                kwargs["json"] = body
            else:
                kwargs["content"] = _text(body)
        return self.client.build_request(str(spec.get("method") or "GET").upper(), self.base_url + path, **kwargs)

    def _summarise(self, request: httpx.Request, response: httpx.Response | None, elapsed_ms: float | None, spec: dict[str, Any]) -> dict[str, Any]:
        sent = self.masker.obj(_maybe_json(request.content.decode("utf-8", "replace") if request.content else ""))
        exchange: dict[str, Any] = {
            "method": request.method, "url": self.masker.text(str(request.url)), "auth": spec.get("auth") or "",
            "request": {"headers": self.masker.obj(dict(request.headers)), "body": sent[:MAX_BODY_CHARS] if isinstance(sent, str) else sent},
        }  # fmt: skip
        if response is not None:
            received = self.masker.obj(_maybe_json(response.text if response.content else ""))
            exchange["response"] = {
                "status": response.status_code, "headers": self.masker.obj(dict(response.headers)), "elapsed_ms": round(elapsed_ms or 0, 1),
                "body": received[:MAX_BODY_CHARS] if isinstance(received, str) else received,
            }  # fmt: skip
        return exchange

    def send(self, spec: dict[str, Any]) -> httpx.Response:
        """Send one request, check its expectations, save the requested values. Raises ``ApiTestError`` (an AssertionError) on any problem."""
        method, path = str(spec.get("method") or "GET").upper(), str(spec.get("path") or "/")
        try:
            request = self._build(spec)
        except ApiTestError as exc:
            self.failure["api"] = {"method": method, "url": f"{self.base_url}{path}", "auth": spec.get("auth") or "", "expected": spec.get("expect") or {}, "kind": exc.kind}
            raise
        started = time.perf_counter()
        try:
            response = self.client.send(request)
        except httpx.TimeoutException as exc:
            self._record_failure(request, None, None, spec, "timeout", [])
            raise ApiTestError(f"Request {method} {self.masker.text(str(request.url))} timed out after {self.timeout:g}s ({type(exc).__name__}: request timed out)", kind="timeout") from exc
        except httpx.HTTPError as exc:
            self._record_failure(request, None, None, spec, "connection", [])
            raise ApiTestError(f"Request {method} {self.masker.text(str(request.url))} failed: connection error ({type(exc).__name__}: {self.masker.text(str(exc))[:160]})", kind="connection") from exc
        elapsed_ms = (time.perf_counter() - started) * 1000
        self.exchanges.append(self._summarise(request, response, elapsed_ms, spec))
        problems = self._check(substitute_expect(spec.get("expect") or {}, self.variables, self.masker), response, elapsed_ms)
        if problems:
            self._record_failure(request, response, elapsed_ms, spec, "assertion", problems)
            raise ApiTestError(f"{method} {path} -> HTTP {response.status_code}: " + "; ".join(problems), kind="assertion", problems=problems)
        self._save(spec.get("save") or {}, response, request, spec, elapsed_ms)
        return response

    def _record_failure(self, request: httpx.Request, response: httpx.Response | None, elapsed_ms: float | None, spec: dict[str, Any], kind: str, problems: list[str]) -> None:
        if response is not None and self.exchanges:
            exchange = self.exchanges[-1]
        else:
            exchange = self._summarise(request, response, elapsed_ms, spec)
            self.exchanges.append(exchange)
        self.failure["api"] = {**exchange, "expected": self.masker.obj(spec.get("expect") or {}), "mismatch": [self.masker.text(p) for p in problems], "kind": kind}

    # ------------------------------------------------------------------ expectations
    def _check(self, expect: dict[str, Any], response: httpx.Response, elapsed_ms: float) -> list[str]:
        problems: list[str] = []
        status = expect.get("status")
        if status is not None:
            allowed = status if isinstance(status, list) else [status]
            if response.status_code not in [int(s) for s in allowed]:
                problems.append(f"expected status {' or '.join(str(s) for s in allowed)} but got {response.status_code}")
        for name, wanted in (expect.get("headers") or {}).items():
            actual = response.headers.get(name)
            if actual is None:
                problems.append(f"header '{name}' is missing")
            elif str(wanted) not in ("*", "") and not _media_equal(actual, str(wanted)):
                problems.append(f"header '{name}' is {self.masker.text(actual)!r}, expected {wanted!r}")
        checks, schema = expect.get("json") or [], expect.get("schema")
        if checks or schema:
            try:
                data = response.json()
            except ValueError:
                problems.append("the response body is not valid JSON" + (f" (content-type {response.headers.get('content-type')})" if response.headers.get("content-type") else ""))
            else:
                for check in checks:
                    found, actual = json_path(data, check.get("path", "$"))
                    message = check_value(str(check.get("op", "equals")), found, actual, check.get("value"))
                    if message:
                        problems.append(f"{check.get('path', '$')} {self.masker.text(message)}")
                if schema:
                    problems += [f"schema: {self.masker.text(p)}" for p in schema_problems(schema, data)]
        max_ms = expect.get("max_ms")
        if max_ms and elapsed_ms > float(max_ms):
            problems.append(f"the response took {elapsed_ms:.0f} ms, more than the allowed {max_ms} ms")
        return problems

    def _save(self, save: dict[str, str], response: httpx.Response, request: httpx.Request, spec: dict[str, Any], elapsed_ms: float) -> None:
        if not save:
            return
        try:
            data = response.json()
        except ValueError:
            data = None
        for variable, path in save.items():
            found, value = json_path(data, path) if data is not None else (False, None)
            if not found:
                self._record_failure(request, response, elapsed_ms, spec, "assertion", [f"cannot save '{variable}': {path} is not in the response"])
                raise ApiTestError(f"Cannot save '{variable}': {path} is not in the response of {spec.get('method', 'GET')} {spec.get('path')}", kind="assertion")
            self.variables[variable] = value
            if SECRETISH_VARIABLE.search(variable):
                self.masker.add(value)

    # ------------------------------------------------------------------ evidence
    def finish(self, failed: bool) -> None:
        folder = ROOT / "reports" / "evidence" / self.test_case_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "steps.json").write_text(json.dumps(self.steps, indent=2), encoding="utf-8")
        (folder / "requests.json").write_text(json.dumps(self.exchanges, indent=2, default=str), encoding="utf-8")
        if failed:
            info = {"test_case_id": self.test_case_id, "saved_variables": sorted(self.variables), **self.failure}
            (folder / "failure.json").write_text(json.dumps(self.masker.obj(info), indent=2, default=str), encoding="utf-8")
