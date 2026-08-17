import os
from pathlib import Path

from ingestion.adapters.ocr import resolve_tesseract_cmd


class TestTesseractResolution:
    def test_directory_path_appends_exe(self, tmp_path):
        fake_dir = tmp_path / "tesseract"
        fake_dir.mkdir()
        fake = fake_dir / "tesseract.exe"
        fake.write_bytes(b"MZ")
        assert resolve_tesseract_cmd(str(fake_dir)) == str(fake)

    def test_explicit_exe_path_when_exists(self, tmp_path):
        fake = tmp_path / "tesseract.exe"
        fake.write_bytes(b"MZ")
        assert resolve_tesseract_cmd(str(fake)) == str(fake)

    def test_env_var_preferred(self, tmp_path, monkeypatch):
        fake_dir = tmp_path / "tesseract"
        fake_dir.mkdir()
        fake = fake_dir / "tesseract.exe"
        fake.write_bytes(b"MZ")
        monkeypatch.setenv("TESSERACT_CMD", str(fake_dir))
        assert resolve_tesseract_cmd("") == str(fake)

    def test_default_libs_path(self, monkeypatch):
        monkeypatch.delenv("TESSERACT_CMD", raising=False)
        resolved = resolve_tesseract_cmd("")
        # Se libs/tesseract/tesseract.exe existir, deve apontar para ele
        # (caminho absoluto); senão, cai no PATH (vazio).
        from ingestion.adapters.ocr import _project_root

        libs = _project_root() / "libs" / "tesseract" / "tesseract.exe"
        if libs.exists():
            assert resolved == str(libs)
        else:
            assert resolved == ""

    def test_missing_dir_uses_default(self, tmp_path, monkeypatch):
        # Um diretório inválido não quebra: recai no padrão libs/tesseract.
        monkeypatch.delenv("TESSERACT_CMD", raising=False)
        resolved = resolve_tesseract_cmd(str(tmp_path / "nao_existe"))
        from ingestion.adapters.ocr import _project_root

        assert resolved == str(_project_root() / "libs" / "tesseract" / "tesseract.exe")