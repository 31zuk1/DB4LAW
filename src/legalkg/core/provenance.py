"""
Provenance tracking for DB4LAW Vault builds.

This module provides functionality to track and verify the origin and
configuration of generated Vault files.
"""

import json
import hashlib
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class BuildManifest:
    """Manifest containing build provenance information."""

    # Git information
    generator_repo_commit: str
    generator_repo_dirty: bool

    # Build timestamp
    build_timestamp: str

    # Configuration hashes
    targets_hash: str
    targets_path: str

    # Build options
    edge_schema: str
    extract_edges: bool
    generate_structure: bool

    # Schema version for future compatibility
    manifest_schema_version: str = "1.0"

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'BuildManifest':
        """Create from dictionary."""
        return cls(**data)


def get_git_commit() -> tuple[str, bool]:
    """
    Get current git commit hash and dirty status.

    Returns:
        Tuple of (commit_hash, is_dirty)
    """
    try:
        # Get commit hash
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            capture_output=True,
            text=True,
            timeout=5
        )
        commit = result.stdout.strip() if result.returncode == 0 else "unknown"

        # Check if working directory is dirty
        result = subprocess.run(
            ['git', 'status', '--porcelain'],
            capture_output=True,
            text=True,
            timeout=5
        )
        is_dirty = bool(result.stdout.strip()) if result.returncode == 0 else False

        return commit, is_dirty
    except Exception:
        return "unknown", False


def compute_file_hash(file_path: Path) -> str:
    """
    Compute SHA-256 hash of a file.

    Args:
        file_path: Path to the file

    Returns:
        Hex-encoded SHA-256 hash
    """
    if not file_path.exists():
        return "file_not_found"

    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def create_manifest(
    targets_path: Path,
    edge_schema: str,
    extract_edges: bool,
    generate_structure: bool
) -> BuildManifest:
    """
    Create a build manifest with current provenance information.

    Args:
        targets_path: Path to targets.yaml
        edge_schema: Edge schema version (v1 or v2)
        extract_edges: Whether edges were extracted
        generate_structure: Whether structure nodes were generated

    Returns:
        BuildManifest instance
    """
    commit, is_dirty = get_git_commit()
    targets_hash = compute_file_hash(targets_path)

    return BuildManifest(
        generator_repo_commit=commit,
        generator_repo_dirty=is_dirty,
        build_timestamp=datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        targets_hash=targets_hash,
        targets_path=str(targets_path),
        edge_schema=edge_schema,
        extract_edges=extract_edges,
        generate_structure=generate_structure
    )


def write_manifest(manifest: BuildManifest, vault_root: Path) -> Path:
    """
    Write manifest to Vault/.db4law/manifest.json.

    Args:
        manifest: BuildManifest instance
        vault_root: Path to Vault root

    Returns:
        Path to written manifest file
    """
    db4law_dir = vault_root / ".db4law"
    db4law_dir.mkdir(exist_ok=True)

    manifest_path = db4law_dir / "manifest.json"
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest.to_dict(), f, indent=2, ensure_ascii=False)

    return manifest_path


def read_manifest(vault_root: Path) -> Optional[BuildManifest]:
    """
    Read manifest from Vault/.db4law/manifest.json.

    Args:
        vault_root: Path to Vault root

    Returns:
        BuildManifest if exists, None otherwise
    """
    manifest_path = vault_root / ".db4law" / "manifest.json"

    if not manifest_path.exists():
        return None

    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return BuildManifest.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def verify_manifest(vault_root: Path, targets_path: Optional[Path] = None) -> dict:
    """
    Verify the current Vault against its manifest.

    Args:
        vault_root: Path to Vault root
        targets_path: Optional path to targets.yaml for hash comparison

    Returns:
        Dictionary with verification results:
        - manifest_exists: bool
        - commit_matches: bool (True if manifest commit matches current HEAD)
        - targets_hash_matches: bool (if targets_path provided)
        - is_dirty: bool (current repo state)
        - manifest: BuildManifest or None
        - issues: list of issue descriptions
    """
    result = {
        'manifest_exists': False,
        'commit_matches': False,
        'targets_hash_matches': None,
        'is_dirty': False,
        'manifest': None,
        'issues': []
    }

    manifest = read_manifest(vault_root)
    if manifest is None:
        result['issues'].append("Manifest not found - Vault provenance unknown")
        return result

    result['manifest_exists'] = True
    result['manifest'] = manifest

    # Check current git state
    current_commit, is_dirty = get_git_commit()
    result['is_dirty'] = is_dirty

    # Compare commits
    if manifest.generator_repo_commit == current_commit:
        result['commit_matches'] = True
    else:
        result['issues'].append(
            f"Commit mismatch: Vault built with {manifest.generator_repo_commit[:8]}, "
            f"current is {current_commit[:8]}"
        )

    # Compare targets hash if provided
    if targets_path is not None:
        current_hash = compute_file_hash(targets_path)
        if current_hash == manifest.targets_hash:
            result['targets_hash_matches'] = True
        else:
            result['issues'].append(
                f"Targets file changed since last build"
            )
            result['targets_hash_matches'] = False

    # Check if manifest indicated dirty build
    if manifest.generator_repo_dirty:
        result['issues'].append("Vault was built from dirty working directory")

    return result


def needs_regeneration(vault_root: Path, targets_path: Path) -> tuple[bool, list[str]]:
    """
    Determine if Vault needs regeneration.

    Args:
        vault_root: Path to Vault root
        targets_path: Path to targets.yaml

    Returns:
        Tuple of (needs_regen, reasons)
    """
    verification = verify_manifest(vault_root, targets_path)

    reasons = []

    if not verification['manifest_exists']:
        reasons.append("No manifest found")
        return True, reasons

    if not verification['commit_matches']:
        reasons.append("Generator code has changed")

    if verification['targets_hash_matches'] is False:
        reasons.append("Targets configuration has changed")

    return len(reasons) > 0, reasons
