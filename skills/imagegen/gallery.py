"""Image gallery — metadata persistence and history management."""

import json, time, os
from pathlib import Path
from typing import Optional


class Gallery:
    def __init__(self, gallery_dir: Path):
        self.gallery_dir = gallery_dir
        self.meta_file = gallery_dir / "gallery.json"
        self._entries: list[dict] = []
        self._load()

    def _load(self):
        if self.meta_file.exists():
            try:
                self._entries = json.loads(self.meta_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, Exception):
                self._entries = []

    def _save(self):
        os.makedirs(self.gallery_dir, exist_ok=True)
        self.meta_file.write_text(json.dumps(self._entries, ensure_ascii=False, indent=1),
                                  encoding="utf-8")

    def add(self, image_path: str, prompt: str, negative_prompt: str,
            backend: str, turn_index: int = -1, task_id: str = "") -> dict:
        entry = {
            "id": f"gal_{int(time.time()*1000)}",
            "path": image_path,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "backend": backend,
            "turn_index": turn_index,
            "task_id": task_id,
            "timestamp": time.time(),
        }
        self._entries.insert(0, entry)
        self._save()
        return entry

    def list(self, page: int = 1, per_page: int = 20) -> dict:
        total = len(self._entries)
        start = (page - 1) * per_page
        end = start + per_page
        return {
            "images": self._entries[start:end],
            "total": total,
            "page": page,
            "per_page": per_page,
        }

    def get_by_task(self, task_id: str) -> Optional[dict]:
        for entry in self._entries:
            if entry.get("task_id") == task_id:
                return entry
        return None

    def get_latest_for_turn(self, turn_index: int) -> Optional[dict]:
        for entry in self._entries:
            if entry.get("turn_index") == turn_index:
                return entry
        return None

    def delete(self, entry_id: str) -> bool:
        for i, entry in enumerate(self._entries):
            if entry.get("id") == entry_id:
                img_path = Path(entry.get("path", ""))
                if img_path.exists():
                    try:
                        img_path.unlink()
                    except OSError:
                        pass
                self._entries.pop(i)
                self._save()
                return True
        return False

    def cleanup(self, max_entries: int = 500):
        if len(self._entries) > max_entries:
            removed = self._entries[max_entries:]
            self._entries = self._entries[:max_entries]
            for entry in removed:
                img_path = Path(entry.get("path", ""))
                if img_path.exists():
                    try:
                        img_path.unlink()
                    except OSError:
                        pass
            self._save()
