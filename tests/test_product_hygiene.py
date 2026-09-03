from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_no_source_product_or_country_specific_residue():
    forbidden = ("ten" + "dly", "esto" + "nian", "esto" + "nia", "ee" + "sti")
    checked = [*ROOT.glob("*.py"), *ROOT.glob("*.md"), *ROOT.glob("*.sample"), *ROOT.glob("*.toml"),
               *ROOT.joinpath("fastdps").rglob("*.py"), *ROOT.joinpath("static").rglob("*.js"), *ROOT.joinpath("static").rglob("*.css")]
    for path in checked:
        content = path.read_text(encoding="utf-8").lower()
        for term in forbidden:
            assert term not in content, f"{term!r} found in {path.relative_to(ROOT)}"


def test_no_committed_secret_file_or_database():
    tracked = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", ".env", "*.sqlite", "*.db"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert not tracked.stdout.strip()
    if (ROOT / ".env").exists():
        ignored = subprocess.run(
            ["git", "-C", str(ROOT), "check-ignore", "-q", ".env"],
            check=False,
        )
        assert ignored.returncode == 0
