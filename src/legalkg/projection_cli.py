from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import typer

from .projection import (
    DEFAULT_PROJECTIONS_ROOT,
    DEFAULT_SOURCE_VAULT,
    ProjectionError,
    add_laws_to_session,
    clean_sessions,
    collect_linked_law_ids,
    create_session,
    find_nested_obsidian_dirs,
    get_session_dir,
    list_sessions,
    open_with_obsidian,
    parse_law_tokens,
    read_session,
    remove_nested_obsidian_dirs,
    remove_laws_from_session,
    resolve_law_ids,
    run_doctor,
)

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _parse_laws_or_die(raw: str, source_vault: Path) -> List[str]:
    tokens = parse_law_tokens(raw)
    if not tokens:
        raise typer.BadParameter("no laws were provided")
    try:
        return resolve_law_ids(tokens, source_vault)
    except ProjectionError as exc:
        raise typer.BadParameter(str(exc)) from exc


def _session_dir_or_die(projections_root: Path, session_id: str) -> Path:
    session_dir = get_session_dir(projections_root, session_id)
    if not session_dir.is_dir():
        raise typer.BadParameter(f"session not found: {session_id}")
    return session_dir


@app.command()
def create(
    laws: str = typer.Option(
        ...,
        "--laws",
        help="Comma-separated law ids or law directory paths.",
    ),
    source_vault: Path = typer.Option(
        DEFAULT_SOURCE_VAULT,
        "--source-vault",
        help="Source vault root (contains laws/).",
    ),
    projections_root: Path = typer.Option(
        DEFAULT_PROJECTIONS_ROOT,
        "--projections-root",
        help="Projection sessions root directory.",
    ),
    session_id: Optional[str] = typer.Option(
        None,
        "--session-id",
        help="Optional fixed session id.",
    ),
    include_linked_laws: bool = typer.Option(
        False,
        "--include-linked-laws",
        help="Automatically add referenced law ids from selected laws.",
    ),
    include_linked_depth: int = typer.Option(
        1,
        "--include-linked-depth",
        min=1,
        help="Traversal depth for --include-linked-laws.",
    ),
    open_obsidian: bool = typer.Option(
        False,
        "--open",
        help="Open created projection in Obsidian.",
    ),
):
    """
    Create a projection vault session.
    """
    law_ids = _parse_laws_or_die(laws, source_vault)

    try:
        session = create_session(
            source_vault=source_vault,
            projections_root=projections_root,
            law_ids=law_ids,
            session_id=session_id,
        )

        if include_linked_laws:
            linked = collect_linked_law_ids(
                session_dir=session.session_dir,
                source_vault=session.source_vault,
                seed_law_ids=session.laws,
                depth=include_linked_depth,
            )
            if linked:
                session = add_laws_to_session(session.session_dir, linked)

        typer.echo(f"session_id: {session.session_id}")
        typer.echo(f"session_dir: {session.session_dir}")
        typer.echo(f"law_count: {len(session.laws)}")

        markers = find_nested_obsidian_dirs(session.source_vault, session.laws)
        if markers:
            typer.echo("warning: nested .obsidian found in source law directories:", err=True)
            for marker in markers:
                typer.echo(f"- {marker}", err=True)
            typer.echo(
                "warning: these can hijack vault opening. remove them if you see wrong vault view.",
                err=True,
            )

        if open_obsidian:
            open_with_obsidian(session.session_dir)
            typer.echo("opened: Obsidian")
    except ProjectionError as exc:
        raise typer.BadParameter(str(exc)) from exc


@app.command("list")
def list_cmd(
    projections_root: Path = typer.Option(
        DEFAULT_PROJECTIONS_ROOT,
        "--projections-root",
        help="Projection sessions root directory.",
    ),
):
    """
    List projection sessions.
    """
    sessions = list_sessions(projections_root)
    if not sessions:
        typer.echo("no sessions")
        return

    for session in sessions:
        typer.echo(
            f"{session.session_id}\t{len(session.laws)} laws\t{session.created_at}\t{session.session_dir}"
        )


@app.command()
def add(
    session_id: str = typer.Option(..., "--session-id", help="Session id."),
    laws: str = typer.Option(
        ...,
        "--laws",
        help="Comma-separated law ids or law directory paths.",
    ),
    projections_root: Path = typer.Option(
        DEFAULT_PROJECTIONS_ROOT,
        "--projections-root",
        help="Projection sessions root directory.",
    ),
):
    """
    Add laws to an existing session.
    """
    session_dir = _session_dir_or_die(projections_root, session_id)
    session = read_session(session_dir)
    law_ids = _parse_laws_or_die(laws, session.source_vault)
    updated = add_laws_to_session(session_dir, law_ids)
    typer.echo(f"session_id: {updated.session_id}")
    typer.echo(f"law_count: {len(updated.laws)}")


@app.command()
def remove(
    session_id: str = typer.Option(..., "--session-id", help="Session id."),
    laws: str = typer.Option(
        ...,
        "--laws",
        help="Comma-separated law ids or law directory paths.",
    ),
    projections_root: Path = typer.Option(
        DEFAULT_PROJECTIONS_ROOT,
        "--projections-root",
        help="Projection sessions root directory.",
    ),
):
    """
    Remove laws from an existing session.
    """
    session_dir = _session_dir_or_die(projections_root, session_id)
    session = read_session(session_dir)
    law_ids = _parse_laws_or_die(laws, session.source_vault)
    updated = remove_laws_from_session(session_dir, law_ids)
    typer.echo(f"session_id: {updated.session_id}")
    typer.echo(f"law_count: {len(updated.laws)}")


@app.command()
def doctor(
    session_id: str = typer.Option(..., "--session-id", help="Session id."),
    projections_root: Path = typer.Option(
        DEFAULT_PROJECTIONS_ROOT,
        "--projections-root",
        help="Projection sessions root directory.",
    ),
    max_examples: int = typer.Option(
        20,
        "--max-examples",
        min=1,
        help="Max broken target examples to print.",
    ),
):
    """
    Check unresolved laws/* wikilinks in a session.
    """
    session_dir = _session_dir_or_die(projections_root, session_id)
    session = read_session(session_dir)
    markers = find_nested_obsidian_dirs(session.source_vault, session.laws)
    if markers:
        typer.echo("warning: nested .obsidian found in source law directories:", err=True)
        for marker in markers:
            typer.echo(f"- {marker}", err=True)
        typer.echo(
            "warning: these can hijack vault opening. remove them if you see wrong vault view.",
            err=True,
        )
    report = run_doctor(session_dir)

    typer.echo(f"files: {report.total_files}")
    typer.echo(f"wikilinks_total: {report.total_wikilinks}")
    typer.echo(f"laws_prefixed_links: {report.total_laws_prefixed_links}")
    typer.echo(f"broken_links: {report.broken_count}")

    if report.missing_law_ids:
        typer.echo("missing_law_ids: " + ", ".join(report.missing_law_ids))
    if report.broken_targets:
        typer.echo("broken_targets_examples:")
        for target in report.broken_targets[:max_examples]:
            typer.echo(f"- {target}")


@app.command()
def open(
    session_id: str = typer.Option(..., "--session-id", help="Session id."),
    projections_root: Path = typer.Option(
        DEFAULT_PROJECTIONS_ROOT,
        "--projections-root",
        help="Projection sessions root directory.",
    ),
):
    """
    Open an existing projection session in Obsidian.
    """
    session_dir = _session_dir_or_die(projections_root, session_id)
    session = read_session(session_dir)
    markers = find_nested_obsidian_dirs(session.source_vault, session.laws)
    if markers:
        typer.echo("warning: nested .obsidian found in source law directories:", err=True)
        for marker in markers:
            typer.echo(f"- {marker}", err=True)
        typer.echo(
            "warning: these can hijack vault opening. remove them if you see wrong vault view.",
            err=True,
        )
    try:
        open_with_obsidian(session_dir)
    except ProjectionError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"opened: {session_dir}")


@app.command()
def clean(
    older_than_days: int = typer.Option(
        7,
        "--older-than-days",
        min=0,
        help="Remove sessions older than this number of days.",
    ),
    projections_root: Path = typer.Option(
        DEFAULT_PROJECTIONS_ROOT,
        "--projections-root",
        help="Projection sessions root directory.",
    ),
):
    """
    Remove stale projection sessions.
    """
    removed = clean_sessions(projections_root, older_than_days)
    typer.echo(f"removed_sessions: {len(removed)}")
    for session_id in removed:
        typer.echo(f"- {session_id}")


@app.command("clean-markers")
def clean_markers(
    session_id: str = typer.Option(..., "--session-id", help="Session id."),
    projections_root: Path = typer.Option(
        DEFAULT_PROJECTIONS_ROOT,
        "--projections-root",
        help="Projection sessions root directory.",
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Actually remove nested .obsidian directories.",
    ),
):
    """
    Scan or remove nested source .obsidian markers for laws in a session.
    """
    session_dir = _session_dir_or_die(projections_root, session_id)
    session = read_session(session_dir)
    markers = find_nested_obsidian_dirs(session.source_vault, session.laws)
    if not markers:
        typer.echo("nested_markers: 0")
        return

    typer.echo(f"nested_markers: {len(markers)}")
    for marker in markers:
        typer.echo(f"- {marker}")

    if not apply:
        typer.echo("dry_run: true (use --apply to remove)")
        return

    removed = remove_nested_obsidian_dirs(session.source_vault, session.laws)
    typer.echo(f"removed_markers: {len(removed)}")


if __name__ == "__main__":
    app()
