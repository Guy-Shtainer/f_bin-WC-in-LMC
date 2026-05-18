"""mock_inspector_app/settings.py — JSON-backed persistence for UI controls.

Atomic write (tmp + rename) so a crashed write never leaves a half-file.
All keys live under the top-level "inspector" section.
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Any

_HERE = os.path.dirname(os.path.abspath(__file__))
_SETTINGS_PATH = os.path.join(_HERE, 'settings.json')


class SettingsManager:
    """Tiny JSON settings manager mirroring the API used elsewhere in the app.

    Usage
    -----
        sm = SettingsManager()
        sm.get('insp_sigma_single', 15.0)
        sm.save('insp_sigma_single', 17.0)

    All values are stored under a single top-level key 'inspector' so the
    file remains a flat JSON dict and is easy to hand-edit if needed.
    """

    SECTION = 'inspector'

    def __init__(self, path: str = _SETTINGS_PATH) -> None:
        self.path = path
        self._cache: dict | None = None

    def _load(self) -> dict:
        if self._cache is not None:
            return self._cache
        if not os.path.exists(self.path):
            self._cache = {self.SECTION: {}}
            return self._cache
        try:
            with open(self.path, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                data = {self.SECTION: {}}
            data.setdefault(self.SECTION, {})
            self._cache = data
            return data
        except (json.JSONDecodeError, OSError):
            # Corrupt or unreadable file — start fresh in memory; do NOT
            # overwrite on disk until the user changes something.
            self._cache = {self.SECTION: {}}
            return self._cache

    def _persist(self) -> None:
        if self._cache is None:
            return
        # Atomic write: write to a tmp file in the same dir, then rename.
        dir_ = os.path.dirname(self.path) or '.'
        os.makedirs(dir_, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix='.settings_', suffix='.json',
                                         dir=dir_)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as fh:
                json.dump(self._cache, fh, indent=2, sort_keys=True,
                          default=str)
            os.replace(tmp_path, self.path)
        except OSError:
            # Best-effort cleanup of the tmp file on failure.
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def get(self, key: str, default: Any = None) -> Any:
        section = self._load().get(self.SECTION, {})
        return section.get(key, default)

    def save(self, key: str, value: Any) -> None:
        data = self._load()
        data.setdefault(self.SECTION, {})[key] = value
        self._persist()

    def all(self) -> dict:
        """Return a shallow copy of the inspector section."""
        return dict(self._load().get(self.SECTION, {}))
