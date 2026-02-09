import subprocess
import sys
from pathlib import Path


def _write_markdown(path: Path, metadata: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{metadata}---\n{body}", encoding="utf-8")


def test_fix_structure_headings_apply(tmp_path):
    vault = tmp_path / "Vault"
    law_id = "TEST001"
    law_dir = vault / "laws" / law_id

    chapter_file = law_dir / "章" / "第1章.md"
    _write_markdown(
        chapter_file,
        "type: chapter\nchapter_num: 1\nchapter_title: 第一章　総則\n",
        "\n# 第1章 第一章　総則\n\n## この章の節\n\n- [[laws/TEST001/節/第1章第1節.md|第1節 第一節　通則]]\n",
    )

    subprocess.run(
        [
            sys.executable,
            "scripts/migration/fix_structure_headings.py",
            "--vault",
            str(vault),
            "--law",
            law_id,
            "--apply",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    updated = chapter_file.read_text(encoding="utf-8")
    assert "# 第1章 総則" in updated
    assert "|第1節 通則]]" in updated
    assert "第1章 第一章" not in updated
    assert "第1節 第一節" not in updated
