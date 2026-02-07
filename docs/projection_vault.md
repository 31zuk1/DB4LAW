# Projection Vault Launcher (`db4law-proj`)

`db4law-proj` builds a lightweight temporary vault that keeps the existing
`[[laws/...]]` links unchanged.

## Quick start

Create a session with selected laws:

```bash
uv run db4law-proj create --laws 140AC0000000045,129AC0000000089
```

Create and open in Obsidian:

```bash
uv run db4law-proj create --laws 140AC0000000045 --open
```

Add laws later:

```bash
uv run db4law-proj add --session-id <session_id> --laws 323AC0000000131
```

Check unresolved `laws/*` links:

```bash
uv run db4law-proj doctor --session-id <session_id>
```

Check nested source `.obsidian` markers (dry run):

```bash
uv run db4law-proj clean-markers --session-id <session_id>
```

Remove nested source `.obsidian` markers:

```bash
uv run db4law-proj clean-markers --session-id <session_id> --apply
```

## Notes

- Source vault stays unchanged: `Vault/laws/*`.
- Projection sessions are created under `.runtime/projections/`.
- Each projection contains `laws/<law_id>` symlinks to source directories.
- `.obsidian` is expected only inside projection sessions.
- If source law directories contain `.obsidian`, Obsidian may open the wrong vault.
- `open` auto-registers projection roots into Obsidian's vault registry (`obsidian.json`) before launch.
- `doctor` reports missing links to laws that are not included in the session.

## Troubleshooting

- `db4law-proj: command not found`
  - Use `uv run db4law-proj ...`.
- `Vault not found` on open
  - Run `uv sync --reinstall-package legalkg` and retry.
  - Check and clean nested source `.obsidian` with `clean-markers`.
