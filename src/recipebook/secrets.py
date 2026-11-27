"""Where the Claude API key is kept: the macOS Keychain, through the keyring library."""

from __future__ import annotations

import os

SERVICE = "recipebook"
ACCOUNT = "claude-api-key"


class KeychainStore:
    def _saved(self) -> str | None:
        try:
            import keyring

            return keyring.get_password(SERVICE, ACCOUNT) or None
        except Exception:
            return None

    def get(self) -> str | None:
        return self._saved() or os.environ.get("ANTHROPIC_API_KEY") or None

    def source(self) -> str | None:
        """'keychain', 'environment' (ANTHROPIC_API_KEY), or None."""
        if self._saved():
            return "keychain"
        return "environment" if os.environ.get("ANTHROPIC_API_KEY") else None

    def set(self, key: str) -> None:
        import keyring

        keyring.set_password(SERVICE, ACCOUNT, key.strip())

    def clear(self) -> None:
        import keyring

        try:
            keyring.delete_password(SERVICE, ACCOUNT)
        except Exception:
            pass


class MemoryStore:
    """For tests."""

    def __init__(self, key: str | None = None, environment: str | None = None):
        self._key = key
        self._environment = environment

    def get(self) -> str | None:
        return self._key or self._environment

    def source(self) -> str | None:
        if self._key:
            return "keychain"
        return "environment" if self._environment else None

    def set(self, key: str) -> None:
        self._key = key.strip()

    def clear(self) -> None:
        self._key = None
