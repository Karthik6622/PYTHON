"""Fetching API definitions from a URL without becoming a way into the local network."""

from __future__ import annotations

from urllib.parse import urljoin, urlparse

import httpx

from ats.config import get_settings
from ats.errors import GenerationError
from ats.security import UnsafeURLError, validate_target_url

MAX_BYTES = 8_000_000
MAX_REDIRECTS = 4


def fetch_text(url: str, allow_private: bool | None = None, timeout: float = 20.0, verify: bool = True) -> tuple[str, str]:
    """GET ``url`` and return ``(text, final_url)``.

    The private-network rule of the studio applies to the first address *and to every redirect*: redirects are followed by hand so
    a public host can never bounce the request to localhost or an intranet address. The body is capped at 8 MB.
    """
    allow = get_settings().allow_private_network if allow_private is None else allow_private
    current = url
    with httpx.Client(timeout=timeout, follow_redirects=False, verify=verify, headers={"Accept": "application/json, application/yaml, text/yaml, */*"}) as client:
        for _ in range(MAX_REDIRECTS + 1):
            try:
                current = validate_target_url(current, allow)
            except UnsafeURLError as exc:
                raise GenerationError(str(exc)) from exc
            try:
                with client.stream("GET", current) as response:
                    if response.status_code in (301, 302, 303, 307, 308) and response.headers.get("location"):
                        current = urljoin(current, response.headers["location"])
                        continue
                    if response.status_code >= 400:
                        raise GenerationError(f"The server answered HTTP {response.status_code} for {urlparse(current).netloc}{urlparse(current).path}.")
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_BYTES:
                            raise GenerationError("The API definition is larger than 8 MB.")
                    encoding = response.encoding or "utf-8"
            except httpx.HTTPError as exc:
                raise GenerationError(f"The address could not be fetched ({type(exc).__name__}).") from exc
            return bytes(body).decode(encoding, errors="replace"), current
    raise GenerationError("Too many redirects.")
