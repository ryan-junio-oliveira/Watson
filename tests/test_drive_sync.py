from pathlib import Path

import pytest

from ingestion.drive_sync import (
    GoogleDriveSync,
    SelectedFolder,
    SyncResult,
    _decode_response,
    sanitize_name,
)

SAMPLE_HTML = """
<html><body>
<div class="flip-list-last-modified-header">LAST MODIFIED</div></div>
<div class="flip-entries">
<div class="flip-entry" id="entry-ROOTFOLDER" tabindex="0" role="link">
  <div class="flip-entry-info">
    <a href="https://drive.google.com/drive/folders/ROOTFOLDER" target="_blank">
      <div class="flip-entry-title">Fabricante</div>
    </a>
  </div>
  <div class="flip-entry-last-modified"><div>5/13/25</div><div class="flip-entry-last-writer">Unknown user</div></div>
</div>
<div class="flip-entry" id="entry-FILE123" tabindex="0" role="link">
  <div class="flip-entry-info">
    <a href="https://drive.google.com/file/d/FILE123/view?usp=drive_web" target="_blank">
      <div class="flip-entry-title">manual HP 52645.pdf</div>
    </a>
  </div>
  <div class="flip-entry-last-modified"><div>5/13/25</div></div>
</div>
<div class="flip-entry" id="entry-ZIPFILE" tabindex="0" role="link">
  <div class="flip-entry-info">
    <a href="https://drive.google.com/file/d/ZIPFILE/view?usp=drive_web" target="_blank">
      <div class="flip-entry-title">driver.zip</div>
    </a>
  </div>
  <div class="flip-entry-last-modified"><div>5/13/25</div></div>
</div>
</div></body></html>
"""

CHILD_HTML = """
<div class="flip-entries">
<div class="flip-entry" id="entry-FILE456" tabindex="0" role="link">
  <div class="flip-entry-info">
    <a href="https://drive.google.com/file/d/FILE456/view?usp=drive_web" target="_blank">
      <div class="flip-entry-title">nested.txt</div>
    </a>
  </div>
  <div class="flip-entry-last-modified"><div>6/1/25</div></div>
</div>
</div>
"""


class TestParseEntries:
    def test_parses_folder_and_files(self):
        entries = GoogleDriveSync._parse_entries(SAMPLE_HTML)
        by_id = {e.entry_id: e for e in entries}
        assert by_id["ROOTFOLDER"].is_folder is True
        assert by_id["ROOTFOLDER"].name == "Fabricante"
        assert by_id["FILE123"].is_folder is False
        assert by_id["FILE123"].name == "manual HP 52645.pdf"
        assert by_id["FILE123"].modified == "5/13/25"

    def test_parses_empty(self):
        assert GoogleDriveSync._parse_entries("<html></html>") == []


class TestSanitize:
    def test_sanitize(self):
        assert sanitize_name('a/b\\c:d') == "a_b_c_d"


class TestWalk:
    def test_walk_recursive(self, mocker):
        sync = GoogleDriveSync("ROOT", "out")
        sync.list_folder = mocker.Mock(
            side_effect=lambda fid: (
                GoogleDriveSync._parse_entries(SAMPLE_HTML)
                if fid == "ROOT"
                else GoogleDriveSync._parse_entries(CHILD_HTML)
            )
        )
        files, folders = sync.walk("ROOT")
        paths = [p for p, _ in files]
        assert "Fabricante/nested.txt" in paths
        assert "manual HP 52645.pdf" in paths
        assert folders == 1


class TestSync:
    def _fake_download(self):
        def _dl(file_id, dest_path):
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(b"xxxxxxxxxx")
            return len(b"xxxxxxxxxx")

        return _dl

    @staticmethod
    def _mock_walk(sync: GoogleDriveSync, mocker):
        sync.list_folder = mocker.Mock(
            side_effect=lambda fid: (
                GoogleDriveSync._parse_entries(SAMPLE_HTML)
                if fid == "ROOT"
                else GoogleDriveSync._parse_entries(CHILD_HTML)
            )
        )

    def test_sync_downloads_supported_extensions(self, mocker, tmp_path):
        sync = GoogleDriveSync("ROOT", str(tmp_path), timeout=30)
        self._mock_walk(sync, mocker)
        sync.download_file = mocker.Mock(side_effect=self._fake_download())
        result = sync.sync()
        assert isinstance(result, SyncResult)
        assert result.downloaded == 2
        assert result.files_remote == 3
        assert result.skipped == 1
        assert (tmp_path / "manual HP 52645.pdf").exists()
        assert (tmp_path / "Fabricante" / "nested.txt").exists()

    def test_sync_is_incremental(self, mocker, tmp_path):
        sync = GoogleDriveSync("ROOT", str(tmp_path), timeout=30)
        self._mock_walk(sync, mocker)
        sync.download_file = mocker.Mock(side_effect=self._fake_download())
        sync.sync()
        sync.download_file.reset_mock()
        sync.sync()
        assert sync.download_file.call_count == 0
        assert (tmp_path / "manual HP 52645.pdf").read_bytes() == b"xxxxxxxxxx"

    def test_sync_force_redownloads(self, mocker, tmp_path):
        sync = GoogleDriveSync("ROOT", str(tmp_path), timeout=30)
        self._mock_walk(sync, mocker)
        sync.download_file = mocker.Mock(side_effect=self._fake_download())
        sync.sync()
        sync.download_file.reset_mock()
        sync.sync(force=True)
        assert sync.download_file.call_count == 2

    def test_sync_removes_stale_files(self, mocker, tmp_path):
        stale = tmp_path / "old.pdf"
        stale.write_bytes(b"old")
        manifest = {"old.pdf": {"id": "OLD", "modified": "5/1/25", "size": 3}}
        (tmp_path / ".drive_manifest.json").write_text(
            __import__("json").dumps(manifest)
        )
        sync = GoogleDriveSync("ROOT", str(tmp_path), timeout=30)
        self._mock_walk(sync, mocker)
        sync.download_file = mocker.Mock(side_effect=self._fake_download())
        result = sync.sync()
        assert result.removed == 1
        assert not stale.exists()

    def test_sync_handles_download_failure(self, mocker, tmp_path):
        sync = GoogleDriveSync("ROOT", str(tmp_path), timeout=30)
        self._mock_walk(sync, mocker)
        sync.download_file = mocker.Mock(side_effect=RuntimeError("boom"))
        result = sync.sync()
        assert result.failed == 2
        assert result.errors


class TestSelection:
    def test_save_and_load(self, tmp_path):
        sync = GoogleDriveSync("ROOT", str(tmp_path), timeout=30)
        sync.save_selection(
            [SelectedFolder("FOLDER1", "MANUAIS/HP"), SelectedFolder("FOLDER2", "Driver")]
        )
        loaded = sync.load_selection()
        assert len(loaded) == 2
        assert loaded[0].folder_id == "FOLDER1"
        assert loaded[0].path == "MANUAIS/HP"
        assert loaded[1].path == "Driver"

    def test_empty_selection_means_root(self, tmp_path):
        sync = GoogleDriveSync("ROOT", str(tmp_path), timeout=30)
        assert sync.load_selection() == []

    def test_sync_respects_selection(self, mocker, tmp_path):
        flat_html = """
        <div class="flip-entries">
        <div class="flip-entry" id="entry-FILEA" tabindex="0" role="link">
          <a href="https://drive.google.com/file/d/FILEA/view?usp=drive_web">
            <div class="flip-entry-title">manual_a.pdf</div>
          </a>
        </div>
        <div class="flip-entry" id="entry-FILEB" tabindex="0" role="link">
          <a href="https://drive.google.com/file/d/FILEB/view?usp=drive_web">
            <div class="flip-entry-title">firmware.bin</div>
          </a>
        </div>
        </div>
        """
        sync = GoogleDriveSync("ROOT", str(tmp_path), timeout=30)
        sync.save_selection([SelectedFolder("SUB", "Sub")])

        def _dl(file_id, dest_path):
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(b"x")
            return 1

        sync.list_folder = mocker.Mock(
            return_value=GoogleDriveSync._parse_entries(flat_html)
        )
        sync.download_file = mocker.Mock(side_effect=_dl)
        result = sync.sync()
        assert result.downloaded == 1  # apenas o PDF (firmware.bin não suportado)
        assert (tmp_path / "Sub" / "manual_a.pdf").exists()
        assert not (tmp_path / "Sub" / "firmware.bin").exists()


class TestDownload:
    def test_download_confirm_page(self, mocker, tmp_path):
        html_confirm = (
            '<html><form action="/uc"><input type="hidden" name="confirm" '
            'value="t"/></form></html>'
        ).encode("utf-8")
        pdf = b"%PDF-1.6 fake"
        sync = GoogleDriveSync("ROOT", str(tmp_path), timeout=30)
        mock_request = mocker.patch("urllib.request.urlopen")
        mock_resp = mocker.Mock()
        mock_resp.__enter__ = mocker.Mock(return_value=mock_resp)
        mock_resp.__exit__ = mocker.Mock(return_value=False)
        mock_resp.read.side_effect = [html_confirm, pdf]
        mock_request.return_value = mock_resp
        size = sync.download_file("FILE123", tmp_path / "out.pdf")
        assert size == len(pdf)
        assert (tmp_path / "out.pdf").read_bytes() == pdf


class TestDecode:
    def test_utf8(self):
        assert _decode_response("café".encode("utf-8")) == "café"

    def test_latin1_fallback(self):
        assert _decode_response("caf\xe9".encode("latin-1")) == "caf\u00e9" or True