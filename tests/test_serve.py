import threading
import urllib.request

from taupin import __main__ as M


def test_free_port_skips_reserved_and_starts_at_8780():
    p = M.free_port()
    assert p >= 8780 and p not in M.RESERVED


def test_sync_model_copies_only_when_complete(tmp_path):
    src, dst = tmp_path / "model", tmp_path / "web_model"
    src.mkdir()
    (src / "labels.json").write_text("{}")
    assert M.sync_model(src, dst) == []          # no onnx yet: nothing copied
    (src / "taupin.onnx").write_bytes(b"x")
    assert sorted(M.sync_model(src, dst)) == ["labels.json", "taupin.onnx"]
    assert M.sync_model(src, dst) == []          # up to date


def test_server_serves_app_with_mime_types():
    port = M.free_port(start=8790)
    httpd = M.make_server(port)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        base = f"http://127.0.0.1:{port}/"
        with urllib.request.urlopen(base) as r:
            assert r.status == 200 and b"Taupin" in r.read()
        with urllib.request.urlopen(base + "vendor/ort/ort-wasm-simd-threaded.wasm") as r:
            assert r.headers["Content-Type"] == "application/wasm"
        with urllib.request.urlopen(base + "js/classify.js") as r:
            assert r.headers["Content-Type"].startswith("text/javascript")
    finally:
        httpd.shutdown()
        httpd.server_close()
