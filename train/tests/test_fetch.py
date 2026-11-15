"""The image downloaders refuse anything that is not an http(s) URL."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fetch_inat
import fetch_ood


def test_download_rejects_file_urls(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("x")
    row = {"photo_id": "1", "url": secret.as_uri(), "source": "gbif", "dataset": ""}
    assert fetch_inat.download(row, tmp_path) is False
    assert fetch_ood.download(row, tmp_path) is False
    assert not (tmp_path / "1.jpg").exists()
