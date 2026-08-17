"""Tests for atomic_write_json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from web_layer.config_io import atomic_write_json


class TestAtomicWriteJson:
    def test_creates_file_with_payload(self, tmp_path: Path) -> None:
        path = tmp_path / "rules.json"
        atomic_write_json(path, {"rules": [{"name": "a"}]})
        assert json.loads(path.read_text(encoding="utf-8")) == {"rules": [{"name": "a"}]}

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "dir" / "zones.json"
        atomic_write_json(path, {"porch": [[0, 0], [1, 0], [1, 1]]})
        assert path.exists()

    def test_rotates_existing_to_bak(self, tmp_path: Path) -> None:
        path = tmp_path / "rules.json"
        path.write_text('{"original": true}', encoding="utf-8")

        atomic_write_json(path, {"updated": True})

        bak = path.with_suffix(path.suffix + ".bak")
        assert bak.exists()
        assert json.loads(bak.read_text(encoding="utf-8")) == {"original": True}
        assert json.loads(path.read_text(encoding="utf-8")) == {"updated": True}

    def test_no_tmp_left_behind(self, tmp_path: Path) -> None:
        path = tmp_path / "rules.json"
        atomic_write_json(path, {"k": 1})
        assert not path.with_suffix(path.suffix + ".tmp").exists()

    def test_simulated_crash_leaves_original_intact(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """If ``os.replace`` never fires, the live config stays valid."""
        path = tmp_path / "rules.json"
        original = {"rules": ["original"]}
        path.write_text(json.dumps(original), encoding="utf-8")

        from web_layer import config_io as mod

        def _boom(*_a, **_kw):
            raise RuntimeError("simulated crash before replace")

        monkeypatch.setattr(mod.os, "replace", _boom)

        with pytest.raises(RuntimeError):
            atomic_write_json(path, {"rules": ["new"]})

        # Live config untouched
        assert json.loads(path.read_text(encoding="utf-8")) == original
        # .bak holds the pre-write contents
        bak = path.with_suffix(path.suffix + ".bak")
        assert bak.exists()
        assert json.loads(bak.read_text(encoding="utf-8")) == original
