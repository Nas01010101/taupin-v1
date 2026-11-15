"""Static checks on web/: CSP hash of the inline importmap, offline shell, launcher and GIF script."""
import base64
import hashlib
import importlib.util
import re
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def test_csp_allows_the_inline_importmap():
    html = (WEB / "index.html").read_text()
    body = re.search(r'<script type="importmap">(.*?)</script>', html, re.S).group(1)
    digest = base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
    assert f"'sha256-{digest}'" in html, "importmap changed: update the hash in the CSP meta tag"


def test_service_worker_shell_files_exist():
    sw = (WEB / "sw.js").read_text()
    shell = re.search(r"const SHELL = \[(.*?)\];", sw, re.S).group(1)
    files = [f for f in re.findall(r"'([^']+)'", shell) if f != "./"]
    assert files and all((WEB / f).is_file() for f in files), [f for f in files if not (WEB / f).is_file()]


def test_no_inline_style_attributes():
    # style-src 'self' blocks inline style attributes (CSSOM writes like el.style.x are allowed).
    for f in [WEB / "index.html", *(WEB / "js").glob("*.js")]:
        assert 'style="' not in f.read_text(), f


def test_make_gif_writes_every_frame(tmp_path):
    spec = importlib.util.spec_from_file_location("make_gif", ROOT / "scripts" / "make_gif.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for i, c in enumerate(["red", "green", "blue"]):
        Image.new("RGB", (64, 36), c).save(tmp_path / f"f{i:04d}.png")
    out = tmp_path / "demo.gif"
    assert mod.make_gif(tmp_path, out, fps=10, width=32) == 3
    with Image.open(out) as g:
        assert g.n_frames == 3 and g.width == 32


def test_trap_thresholds_match_the_engine():
    """The count sheet in the browser and the rule engine compare against the same thresholds."""
    from taupin.engine import TRAP_THRESHOLD

    src = (WEB / "js/scout.js").read_text()
    body = re.search(r"export const THRESHOLDS = \{([^}]*)\}", src).group(1)
    web = {k: float(v) for k, v in re.findall(r"(\w+):\s*([\d.]+)", body)}
    assert web == TRAP_THRESHOLD
