# Provenance Tracking

DB4LAW implements provenance tracking to ensure Vault files are reproducible and verifiable.

## Overview

Every build operation writes a manifest file to `Vault/.db4law/manifest.json` containing:

- Git commit hash of the generator code
- Build timestamp
- Configuration hash (targets.yaml)
- Build options used

This enables:
1. **Reproducibility verification** - Confirm Vault was built with specific code version
2. **Change detection** - Identify when regeneration is needed
3. **Audit trail** - Track build history and configuration

## Manifest Schema

```json
{
  "manifest_schema_version": "1.0",
  "generator_repo_commit": "3f7d9e10b52202cc9781bc67657e64c0c8635171",
  "generator_repo_dirty": false,
  "build_timestamp": "2026-01-29T10:30:00.000000Z",
  "targets_hash": "sha256:abc123...",
  "targets_path": "/path/to/targets.yaml",
  "edge_schema": "v2",
  "extract_edges": true,
  "generate_structure": false
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `manifest_schema_version` | string | Schema version for future compatibility |
| `generator_repo_commit` | string | Git commit hash of generator code |
| `generator_repo_dirty` | boolean | True if built from dirty working directory |
| `build_timestamp` | string | ISO 8601 UTC timestamp |
| `targets_hash` | string | SHA-256 hash of targets.yaml |
| `targets_path` | string | Path to targets file used |
| `edge_schema` | string | Edge schema version (v1/v2) |
| `extract_edges` | boolean | Whether edge extraction was enabled |
| `generate_structure` | boolean | Whether structure nodes were generated |

## Usage

### During Build

Manifest is automatically written by default:

```bash
# Writes manifest
python -m legalkg build-tier1 --vault ./Vault --targets targets.yaml --extract-edges

# Skip manifest (not recommended)
python -m legalkg build-tier1 --vault ./Vault --targets targets.yaml --no-write-manifest
```

### Verification

Use the audit script to verify provenance:

```bash
python scripts/qa/audit_vault.py --vault ./Vault --targets targets.yaml
```

The audit will check:
1. Manifest exists
2. Current git commit matches manifest
3. targets.yaml hash matches manifest
4. Working directory cleanliness

### Programmatic Access

```python
from legalkg.core.provenance import read_manifest, verify_manifest, needs_regeneration

# Read manifest
manifest = read_manifest(vault_path)
print(f"Built at: {manifest.build_timestamp}")
print(f"Commit: {manifest.generator_repo_commit}")

# Verify against current state
result = verify_manifest(vault_path, targets_path)
if result['issues']:
    print("Issues found:")
    for issue in result['issues']:
        print(f"  - {issue}")

# Check if regeneration needed
needs_regen, reasons = needs_regeneration(vault_path, targets_path)
if needs_regen:
    print("Regeneration needed:")
    for reason in reasons:
        print(f"  - {reason}")
```

## Best Practices

1. **Always commit before builds** - Avoid dirty builds for reproducibility
2. **Check manifest before edits** - Verify Vault provenance before manual changes
3. **Include manifest in version control** - Track `Vault/.db4law/manifest.json`
4. **Regenerate after code changes** - Run audit to detect stale Vaults

## Integration with CI/CD

Example GitHub Actions workflow:

```yaml
- name: Build Vault
  run: |
    python -m legalkg build-tier1 --vault ./Vault --targets targets.yaml --extract-edges

- name: Verify Provenance
  run: |
    python scripts/qa/audit_vault.py --vault ./Vault --targets targets.yaml --report-only
```
