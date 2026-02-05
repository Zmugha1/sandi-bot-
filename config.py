"""
Sandi Bot - API key management.
Session-only storage (not saved to disk). Password-masked input for sidebar.
"""
import re
from typing import Optional


def validate_openai_key(key: Optional[str]) -> bool:
    """True if key looks like an OpenAI API key (starts with sk-)."""
    if not key or not isinstance(key, str):
        return False
    k = key.strip()
    return bool(k.startswith("sk-") and len(k) > 20)


def get_api_key_from_session(session_state) -> Optional[str]:
    """Return stored API key from session if set and valid."""
    key = session_state.get("openai_api_key")
    if validate_openai_key(key):
        return key.strip()
    return None


def set_api_key_in_session(session_state, key: Optional[str]) -> None:
    """Store API key in session only. Pass None to clear."""
    if key is None or key == "":
        session_state.pop("openai_api_key", None)
    else:
        session_state["openai_api_key"] = key.strip()
