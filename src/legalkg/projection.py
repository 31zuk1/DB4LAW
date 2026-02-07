from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Set
from urllib.parse import quote

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_VAULT = PROJECT_ROOT / "Vault"
DEFAULT_PROJECTIONS_ROOT = PROJECT_ROOT / ".runtime" / "projections"
DEFAULT_OBSIDIAN_JSON = Path.home() / "Library" / "Application Support" / "obsidian" / "obsidian.json"

METADATA_FILENAME = ".db4law_projection.json"
WIKILINK_PATTERN = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
LAW_ID_FROM_WIKILINK_PATTERN = re.compile(r"^laws/([^/\]]+)(?:/|$)")
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


class ProjectionError(RuntimeError):
    pass


@dataclass
class ProjectionSession:
    session_id: str
    session_dir: Path
    source_vault: Path
    laws: List[str]
    created_at: str

    @property
    def metadata_path(self) -> Path:
        return self.session_dir / METADATA_FILENAME

    @property
    def laws_dir(self) -> Path:
        return self.session_dir / "laws"


@dataclass
class DoctorReport:
    total_files: int
    total_wikilinks: int
    total_laws_prefixed_links: int
    broken_count: int
    broken_targets: List[str]
    missing_law_ids: List[str]
    broken_by_file: Dict[str, int]


def ensure_source_vault(source_vault: Path) -> Path:
    source_vault = source_vault.resolve()
    laws_dir = source_vault / "laws"
    if not source_vault.is_dir():
        raise ProjectionError(f"source vault not found: {source_vault}")
    if not laws_dir.is_dir():
        raise ProjectionError(f"laws directory not found: {laws_dir}")
    return source_vault


def parse_law_tokens(raw: str) -> List[str]:
    tokens: List[str] = []
    for token in raw.split(","):
        token = token.strip()
        if token:
            tokens.append(token)
    return tokens


def normalize_law_token(token: str, source_vault: Path) -> str:
    source_vault = ensure_source_vault(source_vault)
    laws_root = (source_vault / "laws").resolve()

    path = Path(token)
    if path.exists():
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(laws_root)
        except ValueError as exc:
            raise ProjectionError(
                f"law path is outside source vault laws directory: {resolved}"
            ) from exc
        law_id = relative.parts[0] if relative.parts else ""
    else:
        law_id = token

    law_dir = laws_root / law_id
    if not law_dir.is_dir():
        raise ProjectionError(f"law directory not found: {law_dir}")
    return law_id


def resolve_law_ids(tokens: Iterable[str], source_vault: Path) -> List[str]:
    seen: Set[str] = set()
    resolved: List[str] = []
    for token in tokens:
        law_id = normalize_law_token(token, source_vault)
        if law_id not in seen:
            seen.add(law_id)
            resolved.append(law_id)
    if not resolved:
        raise ProjectionError("no valid law ids were provided")
    return resolved


def generate_session_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{ts}-{uuid.uuid4().hex[:6]}"


def validate_session_id(session_id: str) -> None:
    if not SESSION_ID_PATTERN.fullmatch(session_id):
        raise ProjectionError(
            "invalid session id. only [A-Za-z0-9._-] are allowed"
        )


def _create_law_symlink(session_dir: Path, source_vault: Path, law_id: str) -> None:
    link_path = session_dir / "laws" / law_id
    target_path = (source_vault / "laws" / law_id).resolve()

    if not target_path.is_dir():
        raise ProjectionError(f"law directory not found: {target_path}")

    if link_path.exists() or link_path.is_symlink():
        if link_path.is_symlink() and link_path.resolve() == target_path:
            return
        raise ProjectionError(f"link path already exists: {link_path}")

    link_path.symlink_to(target_path, target_is_directory=True)


def _metadata_to_session(metadata: dict, session_dir: Path) -> ProjectionSession:
    return ProjectionSession(
        session_id=metadata["session_id"],
        session_dir=session_dir,
        source_vault=Path(metadata["source_vault"]),
        laws=list(metadata.get("laws", [])),
        created_at=metadata["created_at"],
    )


def write_metadata(session: ProjectionSession) -> None:
    session.session_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "session_id": session.session_id,
        "source_vault": str(session.source_vault),
        "created_at": session.created_at,
        "laws": session.laws,
    }
    session.metadata_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_session(session_dir: Path) -> ProjectionSession:
    metadata_path = session_dir / METADATA_FILENAME
    if not metadata_path.exists():
        raise ProjectionError(f"projection metadata not found: {metadata_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return _metadata_to_session(metadata, session_dir)


def create_session(
    source_vault: Path,
    projections_root: Path,
    law_ids: List[str],
    session_id: str | None = None,
) -> ProjectionSession:
    source_vault = ensure_source_vault(source_vault)
    projections_root = projections_root.resolve()
    if session_id is None:
        session_id = generate_session_id()
    validate_session_id(session_id)

    session_dir = projections_root / session_id
    if session_dir.exists():
        raise ProjectionError(f"session already exists: {session_id}")

    (session_dir / "laws").mkdir(parents=True, exist_ok=False)
    for law_id in law_ids:
        _create_law_symlink(session_dir, source_vault, law_id)

    session = ProjectionSession(
        session_id=session_id,
        session_dir=session_dir,
        source_vault=source_vault,
        laws=list(law_ids),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    write_metadata(session)
    return session


def find_nested_obsidian_dirs(source_vault: Path, law_ids: List[str]) -> List[Path]:
    """
    Detect accidental nested vault markers under source laws.

    If these exist, Obsidian may open a law directory as a separate vault.
    """
    source_vault = ensure_source_vault(source_vault)
    markers: List[Path] = []
    for law_id in law_ids:
        marker = source_vault / "laws" / law_id / ".obsidian"
        if marker.is_dir():
            markers.append(marker)
    return markers


def remove_nested_obsidian_dirs(source_vault: Path, law_ids: List[str]) -> List[Path]:
    """
    Remove nested .obsidian markers under source laws.

    This is destructive for vault-local settings under each law directory.
    """
    removed: List[Path] = []
    for marker in find_nested_obsidian_dirs(source_vault, law_ids):
        shutil.rmtree(marker)
        removed.append(marker)
    return removed


def get_session_dir(projections_root: Path, session_id: str) -> Path:
    return projections_root.resolve() / session_id


def list_sessions(projections_root: Path) -> List[ProjectionSession]:
    projections_root = projections_root.resolve()
    if not projections_root.exists():
        return []

    sessions: List[ProjectionSession] = []
    for child in sorted(projections_root.iterdir()):
        if not child.is_dir():
            continue
        metadata_path = child / METADATA_FILENAME
        if not metadata_path.exists():
            continue
        try:
            sessions.append(read_session(child))
        except Exception:
            continue
    return sessions


def add_laws_to_session(session_dir: Path, law_ids: List[str]) -> ProjectionSession:
    session = read_session(session_dir.resolve())
    existing = set(session.laws)
    for law_id in law_ids:
        _create_law_symlink(session.session_dir, session.source_vault, law_id)
        if law_id not in existing:
            session.laws.append(law_id)
            existing.add(law_id)
    write_metadata(session)
    return session


def remove_laws_from_session(session_dir: Path, law_ids: List[str]) -> ProjectionSession:
    session = read_session(session_dir.resolve())
    targets = set(law_ids)

    for law_id in targets:
        link_path = session.laws_dir / law_id
        if not link_path.exists() and not link_path.is_symlink():
            continue
        if not link_path.is_symlink():
            raise ProjectionError(f"refusing to remove non-symlink path: {link_path}")
        link_path.unlink()

    session.laws = [law_id for law_id in session.laws if law_id not in targets]
    write_metadata(session)
    return session


def _iter_markdown_files(root: Path) -> Iterable[Path]:
    for dirpath, _, filenames in os.walk(root, followlinks=True):
        for filename in filenames:
            if filename.endswith(".md"):
                yield Path(dirpath) / filename


def _extract_law_id_from_link(link_path: str) -> str | None:
    match = LAW_ID_FROM_WIKILINK_PATTERN.match(link_path)
    if not match:
        return None
    return match.group(1)


def collect_linked_law_ids(
    session_dir: Path,
    source_vault: Path,
    seed_law_ids: List[str],
    depth: int = 1,
) -> List[str]:
    if depth < 1:
        return []

    source_vault = ensure_source_vault(source_vault)
    session_dir = session_dir.resolve()
    known: Set[str] = set(seed_law_ids)
    added: List[str] = []
    frontier: Set[str] = set(seed_law_ids)

    for _ in range(depth):
        next_frontier: Set[str] = set()
        for law_id in sorted(frontier):
            law_root = source_vault / "laws" / law_id
            if not law_root.exists():
                continue
            for md_file in _iter_markdown_files(law_root):
                content = md_file.read_text(encoding="utf-8")
                for match in WIKILINK_PATTERN.finditer(content):
                    link_path = match.group(1)
                    ref_law_id = _extract_law_id_from_link(link_path)
                    if not ref_law_id or ref_law_id in known:
                        continue
                    if not (source_vault / "laws" / ref_law_id).is_dir():
                        continue
                    known.add(ref_law_id)
                    added.append(ref_law_id)
                    next_frontier.add(ref_law_id)
        frontier = next_frontier
        if not frontier:
            break

    return added


def run_doctor(session_dir: Path) -> DoctorReport:
    session = read_session(session_dir.resolve())
    broken_targets: Set[str] = set()
    missing_law_ids: Set[str] = set()
    broken_by_file: Dict[str, int] = {}
    total_files = 0
    total_wikilinks = 0
    total_laws_prefixed_links = 0
    broken_count = 0

    for law_id in session.laws:
        law_root = session.laws_dir / law_id
        if not law_root.exists():
            continue

        for md_file in _iter_markdown_files(law_root):
            total_files += 1
            content = md_file.read_text(encoding="utf-8")
            local_broken = 0

            for match in WIKILINK_PATTERN.finditer(content):
                total_wikilinks += 1
                link_path = match.group(1)
                if not link_path.startswith("laws/"):
                    continue

                total_laws_prefixed_links += 1
                target = session.session_dir / link_path
                if target.exists():
                    continue

                broken_count += 1
                local_broken += 1
                broken_targets.add(link_path)
                ref_law_id = _extract_law_id_from_link(link_path)
                if ref_law_id:
                    missing_law_ids.add(ref_law_id)

            if local_broken:
                broken_by_file[str(md_file)] = local_broken

    return DoctorReport(
        total_files=total_files,
        total_wikilinks=total_wikilinks,
        total_laws_prefixed_links=total_laws_prefixed_links,
        broken_count=broken_count,
        broken_targets=sorted(broken_targets),
        missing_law_ids=sorted(missing_law_ids),
        broken_by_file=broken_by_file,
    )


def ensure_obsidian_vault_registered(
    vault_dir: Path, obsidian_json: Path = DEFAULT_OBSIDIAN_JSON
) -> str:
    vault_dir = vault_dir.resolve()
    obsidian_json = obsidian_json.resolve()
    obsidian_json.parent.mkdir(parents=True, exist_ok=True)

    payload: dict = {}
    if obsidian_json.exists():
        try:
            payload = json.loads(obsidian_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ProjectionError(f"invalid Obsidian config JSON: {obsidian_json}") from exc
        if not isinstance(payload, dict):
            raise ProjectionError(f"invalid Obsidian config format: {obsidian_json}")

    vaults = payload.get("vaults")
    if vaults is None:
        vaults = {}
    if not isinstance(vaults, dict):
        raise ProjectionError(f"invalid Obsidian vault registry format: {obsidian_json}")

    vault_dir_str = str(vault_dir)
    for vault_id, info in vaults.items():
        if not isinstance(vault_id, str) or not isinstance(info, dict):
            continue
        path_value = info.get("path")
        if not isinstance(path_value, str):
            continue
        if path_value == vault_dir_str:
            return vault_id

    while True:
        vault_id = uuid.uuid4().hex[:16]
        if vault_id not in vaults:
            break
    vaults[vault_id] = {
        "path": vault_dir_str,
        "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
    }

    payload["vaults"] = vaults
    obsidian_json.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return vault_id


def _find_entry_markdown(session_dir: Path) -> Path | None:
    laws_dir = session_dir / "laws"
    if not laws_dir.is_dir():
        return None
    for law_dir in sorted(laws_dir.iterdir()):
        if not law_dir.is_dir():
            continue
        candidates = sorted(law_dir.glob("*_law.md"))
        if candidates:
            return candidates[0]
        for md in _iter_markdown_files(law_dir):
            return md
    return None


def open_with_obsidian(session_dir: Path) -> None:
    session_dir = session_dir.resolve()
    if not session_dir.is_dir():
        raise ProjectionError(f"session directory not found: {session_dir}")

    # Ensure Obsidian treats this directory as a vault root.
    (session_dir / ".obsidian").mkdir(exist_ok=True)
    vault_name = session_dir.name
    vault_param = quote(vault_name, safe="")
    obsidian_vault_uri = f"obsidian://open?vault={vault_param}"
    entry_note = _find_entry_markdown(session_dir)
    entry_note_uri = None
    if entry_note is not None:
        rel = entry_note.relative_to(session_dir)
        entry_note_uri = (
            f"obsidian://open?vault={vault_param}&file={quote(str(rel).replace(os.sep, '/'), safe='')}"
        )

    if shutil.which("open"):
        # Ensure vault is registered first, then open by vault name URI.
        ensure_obsidian_vault_registered(session_dir)
        app_candidates = [
            os.environ.get("DB4LAW_OBSIDIAN_APP"),
            "/Applications/Obsidian.app",
            "Obsidian",
        ]
        commands: List[List[str]] = []
        commands.append(["open", obsidian_vault_uri])
        if entry_note_uri:
            commands.append(["open", entry_note_uri])
        for app in app_candidates:
            if not app:
                continue
            commands.append(["open", "-a", app, obsidian_vault_uri])
            if entry_note_uri:
                commands.append(["open", "-a", app, entry_note_uri])
        for app in app_candidates:
            if not app:
                continue
            commands.append(["open", "-a", app, str(session_dir)])
        commands.append(["open", str(session_dir)])

        errors: List[str] = []
        for cmd in commands:
            try:
                subprocess.run(cmd, check=True)
                return
            except subprocess.CalledProcessError as exc:
                errors.append(f"{' '.join(cmd)} (exit={exc.returncode})")
                continue
        raise ProjectionError(
            "failed to open Obsidian via macOS launcher; tried: " + "; ".join(errors)
        )
    if shutil.which("xdg-open"):
        subprocess.run(["xdg-open", str(session_dir)], check=True)
        return
    raise ProjectionError("cannot find launcher command (open or xdg-open)")


def clean_sessions(projections_root: Path, older_than_days: int) -> List[str]:
    projections_root = projections_root.resolve()
    if older_than_days < 0:
        raise ProjectionError("older_than_days must be >= 0")
    if not projections_root.exists():
        return []

    now = datetime.now(timezone.utc)
    threshold = now - timedelta(days=older_than_days)
    removed: List[str] = []

    for session in list_sessions(projections_root):
        try:
            created_at = datetime.fromisoformat(session.created_at)
        except ValueError:
            created_at = datetime.fromtimestamp(
                session.session_dir.stat().st_mtime, tz=timezone.utc
            )

        if created_at > threshold:
            continue

        shutil.rmtree(session.session_dir)
        removed.append(session.session_id)

    return removed
