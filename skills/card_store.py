"""Card storage helpers for the AIRP-Pi bridge.

Manages multi-card directory structure. Each card lives in 角色卡/<name>/.
Uses import_card.run_import() for card initialization, and reads
card data directly from the filesystem.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path


SKILLS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SKILLS_DIR.parent
CARDS_DIR = PROJECT_ROOT / "角色卡"
TRASH_DIR = CARDS_DIR / ".trash"
CURRENT_CARD_FILE = PROJECT_ROOT / "current-card.txt"
CARD_META_FILE = PROJECT_ROOT / ".card_meta.json"


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


def _load_card_meta() -> dict:
    """Load card metadata (favorites, last_used timestamps)."""
    return _read_json(CARD_META_FILE, {})


def _save_card_meta(meta: dict):
    atomic_json(CARD_META_FILE, meta)


def atomic_json(path, data):
    """Write JSON atomically via tmp+rename to prevent corruption."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def ensure_card_runtime(card_id: str) -> dict:
    """Ensure card has all runtime files. Runs import if .card_data.json missing."""
    card_dir = get_card_dir(card_id)
    card_data_path = card_dir / ".card_data.json"
    if card_data_path.exists():
        return _read_json(card_data_path, {})
    from import_card import run_import
    result = run_import(str(card_dir), str(PROJECT_ROOT))
    return result if isinstance(result, dict) else {}


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
    ensure_card_runtime(card_id)
    CURRENT_CARD_FILE.write_text(card_id, encoding="utf-8")
    # Track last used
    meta = _load_card_meta()
    meta.setdefault(card_id, {})["last_used"] = datetime.now().isoformat(timespec="seconds")
    _save_card_meta(meta)


def get_card_dir(card_id: str | None = None) -> Path:
    name = card_id or get_current_card_name()
    if not name:
        raise FileNotFoundError("没有可用角色卡")
    return CARDS_DIR / name


def list_cards(sort_by: str = "name", search: str = "", tag_filter: str = "") -> list[dict]:
    active = get_current_card_name()
    meta = _load_card_meta()
    cards = []
    search_lower = search.lower().strip()
    tag_filter_list = [t.strip() for t in tag_filter.split(",") if t.strip()] if tag_filter else []

    for card_id in list_available_card_ids():
        try:
            card_dir = CARDS_DIR / card_id
            card_data = _read_json(card_dir / ".card_data.json", {})
            chat = _read_json(card_dir / "chat_log.json", [])
            name = card_data.get("name") or card_id
            tags = card_data.get("tags", [])
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]

            # Search filter
            if search_lower:
                searchable = f"{name} {card_id} {' '.join(tags)}".lower()
                if search_lower not in searchable:
                    continue

            # Tag filter
            if tag_filter_list:
                if not any(t in tags for t in tag_filter_list):
                    continue

            # Find avatar PNG
            avatar = ""
            pngs = list(card_dir.glob("*.png"))
            if pngs:
                avatar = str(pngs[0].relative_to(PROJECT_ROOT)).replace("\\", "/")

            card_meta = meta.get(card_id, {})
            cards.append({
                "id": card_id,
                "name": name,
                "active": card_id == active,
                "messages": len(chat) if isinstance(chat, list) else 0,
                "updatedAt": _mtime_iso(card_dir / "chat_log.json"),
                "tags": tags,
                "avatar": avatar,
                "fav": card_meta.get("fav", False),
                "lastUsed": card_meta.get("last_used", ""),
            })
        except Exception as exc:
            cards.append({"id": card_id, "name": card_id, "active": card_id == active, "error": str(exc)})

    # Sort
    def sort_key(c):
        if sort_by == "recent":
            return c.get("lastUsed") or c.get("updatedAt") or ""
        elif sort_by == "messages":
            return c.get("messages", 0)
        elif sort_by == "fav":
            return (1 if c.get("fav") else 0, c.get("name", "").lower())
        return c.get("name", "").lower()

    reverse = sort_by in ("recent", "messages", "fav")
    cards.sort(key=sort_key, reverse=reverse)

    return cards


def get_card_payload(card_id: str | None = None) -> dict:
    card_dir = get_card_dir(card_id)
    card_data = _read_json(card_dir / ".card_data.json", {})
    meta = _load_card_meta()
    card_meta = meta.get(card_dir.name, {})

    # Find avatar
    avatar = ""
    pngs = list(card_dir.glob("*.png"))
    if pngs:
        avatar = str(pngs[0].relative_to(PROJECT_ROOT)).replace("\\", "/")

    return {
        "id": card_dir.name,
        "path": str(card_dir),
        "avatar": avatar,
        "fav": card_meta.get("fav", False),
        "fields": {
            "name": card_data.get("name", card_dir.name),
            "description": card_data.get("description", ""),
            "personality": card_data.get("personality", ""),
            "scenario": card_data.get("scenario", ""),
            "first_mes": card_data.get("first_mes", ""),
            "alternate_greetings": card_data.get("alternate_greetings", []),
            "creator_notes": card_data.get("creator_notes", ""),
            "system_prompt": card_data.get("system_prompt", ""),
            "mes_example": card_data.get("mes_example", ""),
            "tags": card_data.get("tags", []),
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


def save_card_fields(card_id: str, fields: dict) -> dict:
    """Update card fields in .card_data.json atomically, rebuild openings."""
    card_dir = get_card_dir(card_id)
    card_data_path = card_dir / ".card_data.json"
    raw = _read_json(card_data_path, {})

    for key in ("name", "description", "personality", "scenario", "first_mes",
                "creator_notes", "system_prompt", "mes_example", "tags",
                "alternate_greetings"):
        if key in fields:
            value = fields[key]
            if key == "tags" and isinstance(value, str):
                value = [x.strip() for x in value.split(",") if x.strip()]
            if key == "alternate_greetings" and isinstance(value, str):
                value = [x.strip() for x in value.split("\n---\n") if x.strip()]
            raw[key] = value

    atomic_json(card_data_path, raw)

    openings = _build_openings(raw)
    if openings:
        atomic_json(SKILLS_DIR / "styles" / "openings.json", openings)

    return get_card_payload(card_id)


def delete_card(card_id: str) -> str:
    """Soft-delete card by moving to .trash/. Returns new active card or ''."""
    card_dir = get_card_dir(card_id)
    if not card_dir.exists():
        raise FileNotFoundError(f"角色卡不存在: {card_id}")

    TRASH_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = TRASH_DIR / f"{card_id}_{ts}"
    shutil.move(str(card_dir), str(dest))

    current = get_current_card_name()
    if current == card_id:
        cards = list_available_card_ids()
        new_active = cards[0] if cards else ""
        if new_active:
            CURRENT_CARD_FILE.write_text(new_active, encoding="utf-8")
        else:
            CURRENT_CARD_FILE.write_text("", encoding="utf-8")
        return new_active
    return get_current_card_name()


def _build_openings(card_data: dict) -> list[dict]:
    """Build openings list from card data (first_mes + alternate_greetings)."""
    openings = []
    first = card_data.get("first_mes") or ""
    if first.strip():
        label = first.strip()[:30] + ("..." if len(first.strip()) > 30 else "")
        openings.append({"id": 0, "label": label, "content": first, "source": "first_mes"})
    for idx, text in enumerate(card_data.get("alternate_greetings") or [], start=1):
        if str(text).strip():
            label = str(text).strip()[:30] + ("..." if len(str(text).strip()) > 30 else "")
            openings.append({"id": idx, "label": label, "content": str(text), "source": "alternate_greetings"})
    return openings


# ─── New Features (SillyTavern-inspired) ───────────────────────


def duplicate_card(card_id: str) -> str:
    """Duplicate a card directory. Returns the new card_id."""
    src_dir = get_card_dir(card_id)
    if not src_dir.exists():
        raise FileNotFoundError(f"角色卡不存在: {card_id}")

    # Generate unique name
    base = card_id.rstrip()
    suffix = 1
    while True:
        new_id = f"{base} (副本{suffix})" if suffix > 1 else f"{base} (副本)"
        new_dir = CARDS_DIR / new_id
        if not new_dir.exists():
            break
        suffix += 1

    shutil.copytree(str(src_dir), str(new_dir))

    # Clear chat log in the copy (fresh start)
    new_chat = new_dir / "chat_log.json"
    if new_chat.exists():
        new_chat.write_text("[]", encoding="utf-8")

    return new_id


def toggle_fav(card_id: str) -> bool:
    """Toggle favorite status. Returns new fav state."""
    meta = _load_card_meta()
    card_meta = meta.setdefault(card_id, {})
    card_meta["fav"] = not card_meta.get("fav", False)
    _save_card_meta(meta)
    return card_meta["fav"]


def list_trash() -> list[dict]:
    """List cards in the trash directory."""
    if not TRASH_DIR.exists():
        return []
    items = []
    for path in sorted(TRASH_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not path.is_dir():
            continue
        # Parse original name and timestamp from folder name like "CardName_20250523_143000"
        name = path.name
        deleted_at = ""
        m = re.match(r"^(.+)_(\d{8}_\d{6})$", name)
        if m:
            original_name = m.group(1)
            ts_str = m.group(2)
            try:
                deleted_at = datetime.strptime(ts_str, "%Y%m%d_%H%M%S").isoformat(timespec="seconds")
            except ValueError:
                pass
        else:
            original_name = name

        card_data = _read_json(path / ".card_data.json", {})
        display_name = card_data.get("name") or original_name

        items.append({
            "id": path.name,
            "original_name": original_name,
            "display_name": display_name,
            "deleted_at": deleted_at,
        })
    return items


def restore_card(trash_id: str) -> str:
    """Restore a card from trash. Returns the restored card_id."""
    if not TRASH_DIR.exists():
        raise FileNotFoundError("回收站为空")
    src = TRASH_DIR / trash_id
    if not src.exists():
        raise FileNotFoundError(f"回收站中未找到: {trash_id}")

    # Parse original name
    m = re.match(r"^(.+)_(\d{8}_\d{6})$", trash_id)
    original_name = m.group(1) if m else trash_id

    # Ensure no conflict
    dest = CARDS_DIR / original_name
    if dest.exists():
        suffix = 1
        while True:
            candidate = f"{original_name} (恢复{suffix})"
            dest = CARDS_DIR / candidate
            if not dest.exists():
                original_name = candidate
                break
            suffix += 1

    shutil.move(str(src), str(dest))
    return original_name


def export_card_json(card_id: str) -> dict:
    """Export card as V2-compatible JSON (SillyTavern format)."""
    card_dir = get_card_dir(card_id)
    card_data = _read_json(card_dir / ".card_data.json", {})

    # Build V2 spec export
    export = {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": {
            "name": card_data.get("name", card_id),
            "description": card_data.get("description", ""),
            "personality": card_data.get("personality", ""),
            "scenario": card_data.get("scenario", ""),
            "first_mes": card_data.get("first_mes", ""),
            "mes_example": card_data.get("mes_example", ""),
            "creator_notes": card_data.get("creator_notes", ""),
            "system_prompt": card_data.get("system_prompt", ""),
            "post_history_instructions": card_data.get("post_history_instructions", ""),
            "alternate_greetings": card_data.get("alternate_greetings", []),
            "tags": card_data.get("tags", []),
            "creator": card_data.get("creator", ""),
            "character_version": card_data.get("character_version", ""),
            "extensions": card_data.get("extensions", {}),
        },
    }

    # Include character_book if present
    if "character_book" in card_data:
        export["data"]["character_book"] = card_data["character_book"]

    return export


def get_avatar_path(card_id: str | None = None) -> Path | None:
    """Get the PNG avatar path for a card, or None."""
    card_dir = get_card_dir(card_id)
    pngs = list(card_dir.glob("*.png"))
    return pngs[0] if pngs else None


def get_all_tags() -> list[str]:
    """Get all unique tags across all cards."""
    tags_set = set()
    for card_id in list_available_card_ids():
        card_dir = CARDS_DIR / card_id
        card_data = _read_json(card_dir / ".card_data.json", {})
        tags = card_data.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        tags_set.update(tags)
    return sorted(tags_set)
