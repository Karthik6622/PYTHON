"""Sign in with GitHub using the OAuth Device Flow (the same sign-in `gh auth login` uses).

The visitor gets a short code, opens github.com/login/device, types the code and approves. No secret is stored in this app:
only the public client id of a GitHub OAuth App (with "Enable Device Flow" ticked) is needed, so every visitor signs in with their
own GitHub account and gets their own token.
"""

from __future__ import annotations

import ssl
from typing import Any

import httpx

DEVICE_CODE_URL = "https://github.com/login/device/code"
ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
DEFAULT_SCOPE = "repo"


class DeviceFlowError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _post(url: str, data: dict[str, str], transport: httpx.BaseTransport | None) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"timeout": httpx.Timeout(20.0), "headers": {"Accept": "application/json", "User-Agent": "rk-studio"}}
    if transport is not None:
        kwargs["transport"] = transport
    else:
        kwargs["verify"] = ssl.create_default_context()
    try:
        with httpx.Client(**kwargs) as client:
            response = client.post(url, data=data)
    except httpx.TimeoutException as exc:
        raise DeviceFlowError("GitHub did not answer in time. Try again.") from exc
    except httpx.HTTPError as exc:
        raise DeviceFlowError("Could not reach GitHub. Check the network connection.") from exc
    try:
        body = response.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    if response.status_code >= 500:
        raise DeviceFlowError(f"GitHub had a problem ({response.status_code}). Try again in a moment.")
    return body


def start(client_id: str, scope: str = DEFAULT_SCOPE, transport: httpx.BaseTransport | None = None) -> dict[str, Any]:
    """Asks GitHub for a code. Returns user_code, verification_uri, device_code, interval and expires_in."""
    body = _post(DEVICE_CODE_URL, {"client_id": client_id, "scope": scope}, transport)
    if body.get("error") == "device_flow_disabled":
        raise DeviceFlowError("Device Flow is not enabled for this GitHub OAuth App. Tick 'Enable Device Flow' in its settings.")
    if not body.get("device_code") or not body.get("user_code"):
        raise DeviceFlowError(str(body.get("error_description") or "GitHub did not start the sign-in. Check GITHUB_CLIENT_ID."))
    return {
        "device_code": str(body["device_code"]),
        "user_code": str(body["user_code"]),
        "verification_uri": str(body.get("verification_uri") or "https://github.com/login/device"),
        "interval": max(5, int(body.get("interval") or 5)),
        "expires_in": int(body.get("expires_in") or 900),
    }


def poll(client_id: str, device_code: str, transport: httpx.BaseTransport | None = None) -> dict[str, Any]:
    """One check. status is ok (with token), pending, slow_down, expired or denied."""
    body = _post(ACCESS_TOKEN_URL, {
        "client_id": client_id, "device_code": device_code, "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
    }, transport)
    if body.get("access_token"):
        return {"status": "ok", "token": str(body["access_token"])}
    error = str(body.get("error") or "")
    if error == "authorization_pending":
        return {"status": "pending"}
    if error == "slow_down":
        return {"status": "slow_down", "interval": int(body.get("interval") or 10)}
    if error == "expired_token":
        return {"status": "expired"}
    if error == "access_denied":
        return {"status": "denied"}
    raise DeviceFlowError(str(body.get("error_description") or "GitHub rejected the sign-in."))
