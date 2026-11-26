"""Where the Claude API key is kept: the macOS Keychain, through the keyring library."""

from __future__ import annotations

import os

SERVICE = "recipebook"
ACCOUNT = "claude-api-key"


class KeychainStore:
    def get(self) -> str | None:
        try:
            import keyring

            saved = keyring.get_password(SERVICE, ACCOUNT)
        except Exception:
            saved = None
        return saved or os.environ.get("ANTHROPIC_API_KEY") or None

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

    def __init__(self, key: str | None = None):
        self._key = key

    def get(self) -> str | None:
        return self._key

    def set(self, key: str) -> None:
        self._key = key.strip()

    def clear(self) -> None:
        self._key = None
