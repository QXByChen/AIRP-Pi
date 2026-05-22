"""Card storage helpers for the AIRP-Pi bridge.

Manages multi-card directory structure. Each card lives in 角色卡/<name>/.
Uses import_card.run_import() for card initialization, and reads
card data directly from the filesystem.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


SKILLS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SKILLS_DIR.parent
CARDS_DIR = PROJECT_ROOT / "角色卡"
CURRENT_CARD_FILE = PROJECT_ROOT / "current-card.txt"


def _read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _mtime_iso(path) -> str:
    try:
        return datetime.fromtimestamp(Path(path).stat().st_mtime).isoformat(timespec="seconds")
    except Exception:
        return ""


def list_available_card_ids() -> list[str]:
    CARDS_DIR.mkdir(parents=True, exist_ok=True)
    ids = []
    for path in sorted(CARDS_DIR.iterdir(), key=lambda p: p.name.lower()):
        if not path.is_dir():
            continue
        if (any(path.glob("*.png")) or any(path.glob("*.json"))
                or any(path.glob("*.txt"))):
            ids.append(path.name)
    return ids


def get_current_card_name() -> str:
    if CURRENT_CARD_FILE.exists():
        name = CURRENT_CARD_FILE.read_text(encoding="utf-8", errors="replace").strip()
        if name:
            return name
    cards = list_available_card_ids()
    if cards:
        CURRENT_CARD_FILE.write_text(cards[0], encoding="utf-8")
        return cards[0]
    return ""


def set_current_card_name(card_id: str) -> None:
    card_dir = get_card_dir(card_id)
    if not card_dir.exists():
        raise FileNotFoundError(f"角色卡不存在: {card_id}")
    CURRENT_CARD_FILE.write_text(card_id, encoding="utf-8")


def get_card_dir(card_id: str | None = None) -> Path:
    name = card_id or get_current_card_name()
    if not name:
        raise FileNotFoundError("没有可用角色卡")
    return CARDS_DIR / name


def list_cards() -> list[dict]:
    active = get_current_card_name()
    cards = []
    for card_id in list_available_card_ids():
        try:
            card_dir = CARDS_DIR / card_id
            card_data = _read_json(card_dir / ".card_data.json", {})
            chat = _read_json(card_dir / "chat_log.json", [])
            name = card_data.get("name") or card_id
            cards.append({
                "id": card_id,
                "name": name,
                "active": card_id == active,
                "messages": len(chat) if isinstance(chat, list) else 0,
                "updatedAt": _mtime_iso(card_dir / "chat_log.json"),
            })
        except Exception as exc:
            cards.append({"id": card_id, "name": card_id, "active": card_id == active, "error": str(exc)})
    return cards


def get_card_payload(card_id: str | None = None) -> dict:
    card_dir = get_card_dir(card_id)
    card_data = _read_json(card_dir / ".card_data.json", {})
    return {
        "id": card_dir.name,
        "path": str(card_dir),
        "fields": {
            "name": card_data.get("name", card_dir.name),
            "description": card_data.get("description", ""),
            "personality": card_data.get("personality", ""),
            "scenario": card_data.get("scenario", ""),
            "first_mes": card_data.get("first_mes", ""),
        },
    }


def get_chat_log_path(card_id: str | None = None) -> Path:
    return get_card_dir(card_id) / "chat_log.json"


def list_worldbooks(card_id: str | None = None) -> list[dict]:
    card_dir = get_card_dir(card_id)
    memory_dir = card_dir / "memory"
    result = []
    ref_path = memory_dir / "reference.md"
    if ref_path.exists():
        result.append({"id": "reference", "name": "reference", "updatedAt": _mtime_iso(ref_path)})
    wb_index = _read_json(memory_dir / ".worldbook_index.json", [])
    if wb_index:
        result.append({"id": "index", "name": "worldbook_index", "entries": len(wb_index)})
    return result


def get_worldbook_payload(book_name: str = "index", card_id: str | None = None) -> dict:
    card_dir = get_card_dir(card_id)
    memory_dir = card_dir / "memory"
    wb_index = _read_json(memory_dir / ".worldbook_index.json", [])
    return {"cardId": card_dir.name, "id": book_name, "entries": wb_index}


def get_openings(card_id: str | None = None) -> list[dict]:
    card_dir = get_card_dir(card_id)
    styles_dir = SKILLS_DIR / "styles"
    data = _read_json(styles_dir / "openings.json", [])
    return data if isinstance(data, list) else []
