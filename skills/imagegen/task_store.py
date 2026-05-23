"""In-memory task queue with thread-safe status tracking."""

import time
import threading
from typing import Optional


class TaskStore:
    def __init__(self):
        self._tasks: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._counter = 0

    def create_task(self, prompt: str, backend: str, turn_index: int = -1) -> str:
        with self._lock:
            self._counter += 1
            task_id = f"img_{self._counter:04d}_{int(time.time())}"
            self._tasks[task_id] = {
                "task_id": task_id,
                "status": "pending",
                "progress": 0.0,
                "prompt": prompt,
                "backend": backend,
                "turn_index": turn_index,
                "image_path": None,
                "error": None,
                "created_at": time.time(),
                "completed_at": None,
            }
            return task_id

    def update_status(self, task_id: str, status: str, progress: float = 0.0,
                      image_path: Optional[str] = None, error: Optional[str] = None):
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            task["status"] = status
            task["progress"] = progress
            if image_path:
                task["image_path"] = image_path
            if error:
                task["error"] = error
            if status in ("done", "error"):
                task["completed_at"] = time.time()

    def get_task(self, task_id: str) -> Optional[dict]:
        with self._lock:
            task = self._tasks.get(task_id)
            return dict(task) if task else None

    def list_tasks(self, limit: int = 50) -> list[dict]:
        with self._lock:
            tasks = sorted(self._tasks.values(), key=lambda t: t["created_at"], reverse=True)
            return [dict(t) for t in tasks[:limit]]

    def list_pending(self) -> list[dict]:
        with self._lock:
            return [dict(t) for t in self._tasks.values() if t["status"] == "pending"]

    def cleanup_old(self, max_age_seconds: int = 86400):
        now = time.time()
        with self._lock:
            to_remove = [tid for tid, t in self._tasks.items()
                         if t["completed_at"] and now - t["completed_at"] > max_age_seconds]
            for tid in to_remove:
                del self._tasks[tid]
