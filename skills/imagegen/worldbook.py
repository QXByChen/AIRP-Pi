"""Imagegen Worldbook — loads, matches, and manages image generation worldbooks."""

import json
import os
from pathlib import Path
from typing import Optional


BOOKS_DIR = Path(__file__).resolve().parent.parent / "styles" / "imagegen_worldbooks"


class ImagegenWorldbook:
    def __init__(self, books_dir: Path = BOOKS_DIR, settings: dict = None):
        self.books_dir = books_dir
        self.settings = settings or {}
        self._cache: dict[str, list[dict]] = {}

    def _get_wb_config(self) -> dict:
        return self.settings.get("imagegen_worldbook", {})

    def _load_book(self, filename: str) -> list[dict]:
        if filename in self._cache:
            return self._cache[filename]
        path = self.books_dir / filename
        if not path.exists():
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            entries = []
            raw_entries = raw.get("entries", {})
            for uid, entry in raw_entries.items():
                if entry.get("disable", False):
                    continue
                entries.append(entry)
            entries.sort(key=lambda e: e.get("order", 0), reverse=True)
            self._cache[filename] = entries
            return entries
        except (json.JSONDecodeError, Exception):
            return []

    def get_books_for_card(self, card_name: str) -> list[dict]:
        cfg = self._get_wb_config()
        if not cfg.get("enabled", True):
            return []
        bindings = cfg.get("bindings", {})
        book_files = bindings.get(card_name) or bindings.get("_default", [])
        all_entries = []
        seen_uids = set()
        for filename in book_files:
            for entry in self._load_book(filename):
                uid_key = f"{filename}:{entry.get('uid', id(entry))}"
                if uid_key not in seen_uids:
                    seen_uids.add(uid_key)
                    all_entries.append(entry)
        return all_entries

    def get_constant_entries(self, card_name: str) -> list[dict]:
        entries = self.get_books_for_card(card_name)
        return [e for e in entries if e.get("constant", False)]

    def match_selective_entries(self, card_name: str, text: str) -> list[dict]:
        entries = self.get_books_for_card(card_name)
        selective = [e for e in entries if not e.get("constant", False) and e.get("key")]
        matched = []
        text_lower = text.lower()
        for entry in selective:
            keys = entry.get("key", [])
            matched_keys = [k for k in keys if k and k.lower() in text_lower]
            if matched_keys:
                matched.append({
                    "entry": entry,
                    "matched_keys": matched_keys,
                    "score": len(matched_keys),
                })
        matched.sort(key=lambda m: m["score"], reverse=True)
        return matched

    def list_books(self) -> list[dict]:
        if not self.books_dir.exists():
            return []
        result = []
        for f in self.books_dir.iterdir():
            if f.suffix == ".json" and f.is_file():
                try:
                    raw = json.loads(f.read_text(encoding="utf-8"))
                    entries = raw.get("entries", {})
                    n_constant = sum(1 for e in entries.values() if e.get("constant"))
                    n_selective = sum(1 for e in entries.values() if not e.get("constant") and e.get("key"))
                    result.append({
                        "filename": f.name,
                        "entries_total": len(entries),
                        "constant": n_constant,
                        "selective": n_selective,
                        "comments": [e.get("comment", "") for e in list(entries.values())[:5]],
                    })
                except Exception:
                    result.append({"filename": f.name, "entries_total": 0, "error": "parse failed"})
        return result

    def get_bindings(self) -> dict:
        return self._get_wb_config().get("bindings", {})

    def set_binding(self, card_name: str, book_files: list[str]):
        cfg = self._get_wb_config()
        bindings = cfg.get("bindings", {})
        bindings[card_name] = book_files
        cfg["bindings"] = bindings

    def clear_cache(self):
        self._cache.clear()
