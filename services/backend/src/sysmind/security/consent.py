from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


class ConsentError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class IssuedConsent:
    ticket: str
    digest: str
    expires_at: str


class ConsentService:
    def __init__(self, session_binding: str, *, ttl_seconds: int = 120) -> None:
        self._key = secrets.token_bytes(32)
        self._session = hashlib.sha256(session_binding.encode()).hexdigest()
        self._ttl = ttl_seconds

    @property
    def ttl_seconds(self) -> int:
        return self._ttl

    def issue(
        self,
        action_id: str,
        tool_name: str,
        target_id: str,
        observed_revision: str,
        *,
        ttl_seconds: int | None = None,
    ) -> IssuedConsent:
        now = datetime.now(UTC)
        # A shorter per-issue TTL keeps the advertised ticket expiry honest when the
        # action plan itself has a tighter, action-specific window.
        effective_ttl = self._ttl if ttl_seconds is None else max(1, ttl_seconds)
        expires = now + timedelta(seconds=effective_ttl)
        payload = {
            "action_id": action_id,
            "tool": tool_name,
            "target_hash": hashlib.sha256(target_id.encode()).hexdigest(),
            "revision": observed_revision,
            "session": self._session,
            "exp": int(expires.timestamp()),
            "nonce": secrets.token_urlsafe(18),
        }
        encoded = base64.urlsafe_b64encode(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).decode()
        signature = hmac.new(self._key, encoded.encode(), hashlib.sha256).hexdigest()
        ticket = f"{encoded}.{signature}"
        return IssuedConsent(
            ticket, hashlib.sha256(ticket.encode()).hexdigest(), expires.isoformat()
        )

    def verify(
        self, ticket: str, action_id: str, tool_name: str, target_id: str, observed_revision: str
    ) -> str:
        try:
            encoded, signature = ticket.rsplit(".", 1)
            expected = hmac.new(self._key, encoded.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise ConsentError("Consent ticket is invalid.")
            payload = json.loads(base64.urlsafe_b64decode(encoded.encode()))
        except (ValueError, json.JSONDecodeError) as error:
            raise ConsentError("Consent ticket is invalid.") from error
        if not isinstance(payload, dict):
            raise ConsentError("Consent ticket is invalid.")
        if payload.get("action_id") != action_id or payload.get("tool") != tool_name:
            raise ConsentError("Consent ticket does not match this action.")
        if payload.get("target_hash") != hashlib.sha256(target_id.encode()).hexdigest():
            raise ConsentError("Consent ticket target was changed.")
        if payload.get("revision") != observed_revision or payload.get("session") != self._session:
            raise ConsentError("Consent ticket context was changed.")
        try:
            expires_at = int(payload.get("exp", 0))
        except (TypeError, ValueError, OverflowError) as error:
            raise ConsentError("Consent ticket is invalid.") from error
        if expires_at < int(datetime.now(UTC).timestamp()):
            raise ConsentError("Consent ticket expired.")
        return hashlib.sha256(ticket.encode()).hexdigest()
