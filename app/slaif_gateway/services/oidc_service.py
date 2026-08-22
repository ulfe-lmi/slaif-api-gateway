"""OIDC authentication service with PKCE support."""

from __future__ import annotations

import hashlib
import secrets
import time
from base64 import urlsafe_b64encode
from typing import Any
from urllib.parse import urlencode

import httpx
from authlib.jose import JsonWebToken, jwt as _jwt_module  # noqa: F401
from authlib.jose.errors import ExpiredTokenError, InvalidClaimError, JoseError

from slaif_gateway.config import Settings


class OidcError(Exception):
    def __init__(self, message: str, *, code: str = "oidc_error") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class OidcAuthService:
    """Handles OIDC authorization code flow with PKCE."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._discovery: dict[str, Any] | None = None
        self._discovery_fetched_at: float = 0

    @property
    def enabled(self) -> bool:
        return self._settings.OIDC_ENABLED

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise OidcError("OIDC is not enabled.", code="oidc_not_enabled")

    async def get_discovery(self) -> dict[str, Any]:
        """Fetch and cache the OIDC discovery document."""
        self._require_enabled()
        now = time.monotonic()
        if self._discovery is not None and (now - self._discovery_fetched_at) < 3600:
            return self._discovery
        issuer = self._settings.OIDC_ISSUER_URL.rstrip("/")
        url = f"{issuer}/.well-known/openid-configuration"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            self._discovery = resp.json()
        self._discovery_fetched_at = now
        return self._discovery

    def generate_pkce_pair(self) -> tuple[str, str]:
        """Generate a code_verifier and code_challenge pair."""
        verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        return verifier, challenge

    def generate_state(self) -> str:
        return secrets.token_urlsafe(32)

    def generate_nonce(self) -> str:
        return secrets.token_urlsafe(32)

    def build_authorization_url(
        self,
        *,
        authorization_endpoint: str,
        state: str,
        nonce: str,
        code_challenge: str,
    ) -> str:
        params = {
            "response_type": "code",
            "client_id": self._settings.OIDC_CLIENT_ID,
            "redirect_uri": self._settings.OIDC_REDIRECT_URI,
            "scope": self._settings.OIDC_SCOPES,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        separator = "&" if "?" in authorization_endpoint else "?"
        return f"{authorization_endpoint}{separator}{urlencode(params)}"

    def validate_id_token(
        self,
        *,
        id_token: str,
        expected_nonce: str,
        jwks: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate an ID token and return its claims.

        Raises OidcError on any validation failure.
        """
        discovery = self._discovery or {}
        issuer = discovery.get("issuer", self._settings.OIDC_ISSUER_URL)
        audience = self._settings.OIDC_CLIENT_ID

        try:
            jwt_client = JsonWebToken(["RS256", "ES256"])
            claims = jwt_client.decode(
                id_token,
                jwks,
                claims_options={
                    "iss": {"essential": True, "value": issuer},
                    "aud": {"essential": True, "value": audience},
                },
                claims_cls=None,
            )
        except ExpiredTokenError:
            raise OidcError("ID token has expired.", code="oidc_token_expired") from None
        except InvalidClaimError as exc:
            raise OidcError(f"ID token claim mismatch: {exc}", code="oidc_claim_mismatch") from None
        except JoseError:
            raise OidcError("ID token signature verification failed.", code="oidc_signature_invalid") from None

        # Validate nonce
        token_nonce = claims.get("nonce")
        if not token_nonce or token_nonce != expected_nonce:
            raise OidcError("ID token nonce mismatch.", code="oidc_nonce_mismatch")

        # Validate expiry with 5-minute clock skew tolerance
        exp = claims.get("exp")
        if exp is not None and isinstance(exp, (int, float)):
            skew = 300
            if time.time() > (float(exp) + skew):
                raise OidcError("ID token has expired.", code="oidc_token_expired")

        subject = claims.get("sub")
        email = claims.get("email")
        if not isinstance(subject, str) or not subject:
            raise OidcError("ID token missing required sub claim.", code="oidc_missing_sub")
        if not isinstance(email, str) or not email:
            raise OidcError("ID token missing required email claim.", code="oidc_missing_email")

        return {
            "subject": subject,
            "email": email,
            "email_verified": claims.get("email_verified", False),
            "issuer": issuer,
        }

    async def exchange_code_for_tokens(
        self,
        *,
        code: str,
        code_verifier: str,
        token_endpoint: str,
    ) -> dict[str, Any]:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._settings.OIDC_REDIRECT_URI,
            "client_id": self._settings.OIDC_CLIENT_ID,
            "client_secret": self._settings.OIDC_CLIENT_SECRET,
            "code_verifier": code_verifier,
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(token_endpoint, data=data)
            resp.raise_for_status()
            return resp.json()

    async def fetch_jwks(self, jwks_uri: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(jwks_uri)
            resp.raise_for_status()
            return resp.json()


def create_oidc_service(settings: Settings) -> OidcAuthService:
    return OidcAuthService(settings=settings)
