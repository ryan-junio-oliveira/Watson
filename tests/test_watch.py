from pathlib import Path

import watch


def test_snapshot_empty_dir(tmp_path):
    cfg = type("Cfg", (), {"documents_dir": str(tmp_path)})()
    assert watch.snapshot(cfg) == {}


def test_snapshot_lists_supported_files_only(tmp_path):
    cfg = type("Cfg", (), {"documents_dir": str(tmp_path)})()
    (tmp_path / "doc.pdf").write_bytes(b"pdf")
    (tmp_path / "img.PNG").write_bytes(b"img")
    (tmp_path / "notes.txt").write_bytes(b"text")
    (tmp_path / "notme.exe").write_bytes(b"exe")
    (tmp_path / "sub" / "nested.docx").parent.mkdir()
    (tmp_path / "sub" / "nested.docx").write_bytes(b"docx")

    state = watch.snapshot(cfg)

    assert set(state.keys()) == {"doc.pdf", "img.PNG", "notes.txt", "sub/nested.docx"}


def test_snapshot_tracks_size_and_mtime(tmp_path):
    cfg = type("Cfg", (), {"documents_dir": str(tmp_path)})()
    f = tmp_path / "a.txt"
    f.write_bytes(b"hello")

    state = watch.snapshot(cfg)
    size, mtime = state["a.txt"]

    assert size == 5
    assert mtime  # str(st_mtime), não vazio


def test_snapshot_detects_change(tmp_path):
    cfg = type("Cfg", (), {"documents_dir": str(tmp_path)})()
    f = tmp_path / "a.txt"
    f.write_bytes(b"v1")

    s1 = watch.snapshot(cfg)
    f.write_bytes(b"v2 longer content")
    s2 = watch.snapshot(cfg)

    assert s1 != s2
    assert s2["a.txt"][0] == 17


def test_snapshot_ignores_missing_dir(tmp_path):
    cfg = type("Cfg", (), {"documents_dir": str(tmp_path / "nao_existe")})()
    assert watch.snapshot(cfg) == {}