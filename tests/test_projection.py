from __future__ import annotations

import json
import subprocess
from pathlib import Path
from urllib.parse import quote

from legalkg.projection import (
    add_laws_to_session,
    collect_linked_law_ids,
    create_session,
    ensure_obsidian_vault_registered,
    find_nested_obsidian_dirs,
    open_with_obsidian,
    remove_nested_obsidian_dirs,
    resolve_law_ids,
    run_doctor,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_source_vault(tmp_path: Path) -> Path:
    source = tmp_path / "Vault"

    # Law A references law B
    _write(
        source / "laws" / "LAW_A" / "A_law.md",
        """---
title: LAW_A
---
""",
    )
    _write(
        source / "laws" / "LAW_A" / "本文" / "第1条.md",
        """---
parent: '[[laws/LAW_A/A_law.md|LAW_A]]'
---
LAW_A references [[laws/LAW_B/B_law.md|LAW_B]].
""",
    )

    # Law B references law C
    _write(
        source / "laws" / "LAW_B" / "B_law.md",
        """---
title: LAW_B
---
""",
    )
    _write(
        source / "laws" / "LAW_B" / "本文" / "第1条.md",
        """---
parent: '[[laws/LAW_B/B_law.md|LAW_B]]'
---
LAW_B references [[laws/LAW_C/C_law.md|LAW_C]].
""",
    )

    _write(
        source / "laws" / "LAW_C" / "C_law.md",
        """---
title: LAW_C
---
""",
    )
    return source


def test_create_session_creates_symlinks_and_metadata(tmp_path: Path):
    source = _make_source_vault(tmp_path)
    projections_root = tmp_path / ".runtime" / "projections"

    session = create_session(
        source_vault=source,
        projections_root=projections_root,
        law_ids=["LAW_A"],
        session_id="session-a",
    )

    link_path = session.session_dir / "laws" / "LAW_A"
    assert link_path.is_symlink()
    assert link_path.resolve() == (source / "laws" / "LAW_A").resolve()

    metadata = json.loads((session.session_dir / ".db4law_projection.json").read_text(encoding="utf-8"))
    assert metadata["session_id"] == "session-a"
    assert metadata["laws"] == ["LAW_A"]


def test_doctor_detects_missing_cross_law_links_then_add_resolves(tmp_path: Path):
    source = _make_source_vault(tmp_path)
    projections_root = tmp_path / ".runtime" / "projections"

    session = create_session(
        source_vault=source,
        projections_root=projections_root,
        law_ids=["LAW_A"],
        session_id="session-doctor",
    )

    report = run_doctor(session.session_dir)
    assert report.broken_count > 0
    assert "LAW_B" in report.missing_law_ids

    add_laws_to_session(session.session_dir, ["LAW_B"])
    report_after = run_doctor(session.session_dir)
    assert report_after.broken_count > 0
    assert "LAW_C" in report_after.missing_law_ids

    add_laws_to_session(session.session_dir, ["LAW_C"])
    report_final = run_doctor(session.session_dir)
    assert report_final.broken_count == 0
    assert report_final.missing_law_ids == []


def test_resolve_law_ids_supports_law_paths(tmp_path: Path):
    source = _make_source_vault(tmp_path)
    law_a_path = source / "laws" / "LAW_A"
    resolved = resolve_law_ids(
        [str(law_a_path), "LAW_B", "LAW_A"],
        source_vault=source,
    )
    assert resolved == ["LAW_A", "LAW_B"]


def test_collect_linked_law_ids_depth(tmp_path: Path):
    source = _make_source_vault(tmp_path)
    projections_root = tmp_path / ".runtime" / "projections"
    session = create_session(
        source_vault=source,
        projections_root=projections_root,
        law_ids=["LAW_A"],
        session_id="session-depth",
    )

    linked_depth_1 = collect_linked_law_ids(
        session_dir=session.session_dir,
        source_vault=source,
        seed_law_ids=["LAW_A"],
        depth=1,
    )
    assert linked_depth_1 == ["LAW_B"]

    linked_depth_2 = collect_linked_law_ids(
        session_dir=session.session_dir,
        source_vault=source,
        seed_law_ids=["LAW_A"],
        depth=2,
    )
    assert linked_depth_2 == ["LAW_B", "LAW_C"]


def test_find_nested_obsidian_dirs(tmp_path: Path):
    source = _make_source_vault(tmp_path)
    marker = source / "laws" / "LAW_A" / ".obsidian"
    marker.mkdir(parents=True)

    markers = find_nested_obsidian_dirs(source, ["LAW_A", "LAW_B"])
    assert markers == [marker]


def test_remove_nested_obsidian_dirs(tmp_path: Path):
    source = _make_source_vault(tmp_path)
    marker = source / "laws" / "LAW_A" / ".obsidian"
    marker.mkdir(parents=True)

    removed = remove_nested_obsidian_dirs(source, ["LAW_A", "LAW_B"])
    assert removed == [marker]
    assert not marker.exists()


def test_ensure_obsidian_vault_registered_adds_entry(tmp_path: Path):
    vault_dir = tmp_path / "projection-session"
    vault_dir.mkdir(parents=True)
    obsidian_json = tmp_path / "obsidian.json"
    obsidian_json.write_text('{"vaults":{}}', encoding="utf-8")

    vault_id = ensure_obsidian_vault_registered(vault_dir, obsidian_json)
    payload = json.loads(obsidian_json.read_text(encoding="utf-8"))

    assert vault_id in payload["vaults"]
    assert payload["vaults"][vault_id]["path"] == str(vault_dir.resolve())


def test_ensure_obsidian_vault_registered_reuses_existing(tmp_path: Path):
    vault_dir = tmp_path / "projection-session"
    vault_dir.mkdir(parents=True)
    obsidian_json = tmp_path / "obsidian.json"
    obsidian_json.write_text(
        json.dumps(
            {
                "vaults": {
                    "aaaaaaaaaaaaaaaa": {
                        "path": str(vault_dir.resolve()),
                        "ts": 0,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    vault_id = ensure_obsidian_vault_registered(vault_dir, obsidian_json)
    payload = json.loads(obsidian_json.read_text(encoding="utf-8"))

    assert vault_id == "aaaaaaaaaaaaaaaa"
    assert list(payload["vaults"].keys()) == ["aaaaaaaaaaaaaaaa"]


def test_open_with_obsidian_prefers_registered_uri(tmp_path: Path, monkeypatch):
    session_dir = tmp_path / "projection-session"
    session_dir.mkdir(parents=True)

    calls = []

    def fake_which(name: str):
        if name == "open":
            return "/usr/bin/open"
        return None

    def fake_run(cmd, check):
        if len(calls) == 0:
            calls.append(cmd)
            raise subprocess.CalledProcessError(returncode=1, cmd=cmd)
        calls.append(cmd)
        return 0

    def fake_register(vault_dir):
        assert vault_dir == session_dir.resolve()
        return "aaaaaaaaaaaaaaaa"

    monkeypatch.setattr("legalkg.projection.shutil.which", fake_which)
    monkeypatch.setattr("legalkg.projection.subprocess.run", fake_run)
    monkeypatch.setattr(
        "legalkg.projection.ensure_obsidian_vault_registered", fake_register
    )

    open_with_obsidian(session_dir)

    assert calls
    encoded = quote(session_dir.resolve().name, safe="")
    assert calls[0] == ["open", f"obsidian://open?vault={encoded}"]


def test_open_with_obsidian_builds_entry_note_uri_for_symlinked_law(
    tmp_path: Path, monkeypatch
):
    source = _make_source_vault(tmp_path)
    projections_root = tmp_path / ".runtime" / "projections"
    session = create_session(
        source_vault=source,
        projections_root=projections_root,
        law_ids=["LAW_A"],
        session_id="session-open-link",
    )

    calls = []

    def fake_which(name: str):
        if name == "open":
            return "/usr/bin/open"
        return None

    def fake_run(cmd, check):
        if len(calls) == 0:
            calls.append(cmd)
            raise subprocess.CalledProcessError(returncode=1, cmd=cmd)
        calls.append(cmd)
        return 0

    monkeypatch.setattr("legalkg.projection.shutil.which", fake_which)
    monkeypatch.setattr("legalkg.projection.subprocess.run", fake_run)
    monkeypatch.setattr(
        "legalkg.projection.ensure_obsidian_vault_registered", lambda _: "dummyvaultid"
    )

    open_with_obsidian(session.session_dir)

    assert len(calls) >= 2
    assert "file=laws%2FLAW_A%2FA_law.md" in calls[1][1]
