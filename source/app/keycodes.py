"""Small platform-independent keyboard key-name helpers."""

import re


def chat_key_vk(config) -> int:
    """Return a virtual-key code for a letter/digit or an F1–F24 key."""
    key = str(config.get("game_chat_key", "t")).strip().upper() or "T"
    if len(key) == 1 and key.isascii() and key.isalnum():
        return ord(key)
    match = re.fullmatch(r"F(\d{1,2})", key)
    if match and 1 <= int(match.group(1)) <= 24:
        return 0x70 + int(match.group(1)) - 1
    raise ValueError(f"неизвестная клавиша чата «{key}»")
