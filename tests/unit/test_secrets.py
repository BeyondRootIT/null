from __future__ import annotations

import os

from cti.config.secrets import resolve_secrets


def test_env_substitution(monkeypatch):
    monkeypatch.setenv("MY_TOKEN", "abc")
    out = resolve_secrets({"k": "${env:MY_TOKEN}"})
    assert out == {"k": "abc"}


def test_file_substitution(tmp_path):
    p = tmp_path / "s.txt"
    p.write_text("xyz", encoding="utf-8")
    out = resolve_secrets({"k": f"${{file:{p}}}"})
    assert out == {"k": "xyz"}


def test_recurses_lists():
    os.environ["A"] = "1"
    out = resolve_secrets([{"v": "${env:A}"}])
    assert out == [{"v": "1"}]
