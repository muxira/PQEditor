"""Application state: list of open packs, undo/redo, recent files."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Optional

from platformdirs import user_config_dir

from .io import LoadedPack, load_pq, save_pq
from .model import Pack

APP_NAME = "PQEditor"
APP_AUTHOR = "PQEditor"


def config_path() -> Path:
    p = Path(user_config_dir(APP_NAME, APP_AUTHOR)) / "config.json"
    return p


class UndoStack:
    def __init__(self, initial: Pack, limit: int = 100):
        self._stack: list[Pack] = [copy.deepcopy(initial)]
        self._index: int = 0
        self._limit = limit

    def push(self, pack: Pack) -> None:
        # truncate future
        self._stack = self._stack[: self._index + 1]
        self._stack.append(copy.deepcopy(pack))
        self._index += 1
        if len(self._stack) > self._limit:
            self._stack.pop(0)
            self._index -= 1

    def can_undo(self) -> bool:
        return self._index > 0

    def can_redo(self) -> bool:
        return self._index < len(self._stack) - 1

    def undo(self) -> Pack:
        if not self.can_undo():
            raise IndexError("cannot undo")
        self._index -= 1
        return copy.deepcopy(self._stack[self._index])

    def redo(self) -> Pack:
        if not self.can_redo():
            raise IndexError("cannot redo")
        self._index += 1
        return copy.deepcopy(self._stack[self._index])

    def current(self) -> Pack:
        return copy.deepcopy(self._stack[self._index])


class OpenPack:
    def __init__(self, loaded: LoadedPack, file_path: Optional[Path] = None):
        self.loaded: LoadedPack = loaded
        self.file_path: Optional[Path] = file_path
        self.dirty: bool = False
        self.undo = UndoStack(loaded.pack)

    @property
    def pack(self) -> Pack:
        return self.loaded.pack

    @property
    def title(self) -> str:
        name = self.loaded.pack.Name or "Untitled"
        if self.dirty:
            name += " *"
        return name

    def mark_dirty(self) -> None:
        self.dirty = True

    def commit(self) -> None:
        """Push current pack onto undo stack and mark dirty."""
        self.undo.push(self.loaded.pack)
        self.dirty = True

    def undo_action(self) -> bool:
        if self.undo.can_undo():
            self.loaded.pack = self.undo.undo()
            self.dirty = True
            return True
        return False

    def redo_action(self) -> bool:
        if self.undo.can_redo():
            self.loaded.pack = self.undo.redo()
            self.dirty = True
            return True
        return False

    def save(self, path: Optional[Path] = None) -> Path:
        target = path or self.file_path
        if target is None:
            raise ValueError("No file path for save")
        # Ensure media paths consistent? caller keeps them consistent on export
        from .io import save_pq as _save
        _save(self.loaded.pack, self.loaded.media, target)
        self.file_path = target
        self.dirty = False
        # Update recent
        AppState.instance().add_recent(target) if AppState._instance else None
        return target


class AppState:
    _instance: Optional["AppState"] = None

    @classmethod
    def instance(cls) -> "AppState":
        if cls._instance is None:
            cls._instance = AppState()
        return cls._instance

    def __init__(self):
        self.open_packs: list[OpenPack] = []
        self.current_index: int = -1
        self.recent: list[str] = []
        self._load_config()

    # -- config persistence
    def _load_config(self) -> None:
        try:
            p = config_path()
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                self.recent = data.get("recent", [])[:20]
        except Exception:
            self.recent = []

    def _save_config(self) -> None:
        try:
            p = config_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"recent": self.recent[:20]}, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def add_recent(self, path: Path) -> None:
        s = str(path)
        if s in self.recent:
            self.recent.remove(s)
        self.recent.insert(0, s)
        self.recent = self.recent[:20]
        self._save_config()

    # -- pack management
    def add_pack(self, loaded: LoadedPack, file_path: Optional[Path] = None) -> int:
        op = OpenPack(loaded, file_path)
        self.open_packs.append(op)
        self.current_index = len(self.open_packs) - 1
        if file_path:
            self.add_recent(file_path)
        return self.current_index

    def close_pack(self, index: int) -> None:
        if 0 <= index < len(self.open_packs):
            del self.open_packs[index]
            if self.current_index >= len(self.open_packs):
                self.current_index = len(self.open_packs) - 1

    def current_pack(self) -> Optional[OpenPack]:
        if 0 <= self.current_index < len(self.open_packs):
            return self.open_packs[self.current_index]
        return None

    def set_current(self, index: int) -> None:
        if 0 <= index < len(self.open_packs):
            self.current_index = index

    def open_file(self, path: Path) -> int:
        loaded = load_pq(path)
        return self.add_pack(loaded, path)
