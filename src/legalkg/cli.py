import typer
from pathlib import Path
from .core.tier0 import Tier0Builder
from typing import Optional

app = typer.Typer(add_completion=False)

@app.command()
def build_tier0(
    vault: Path = typer.Option(..., help="Path to Vault root"),
    as_of: str = typer.Option(..., help="Date string YYYY-MM-DD")
):
    """
    Fetch law list and generate Tier 0 metadata (law.md).
    """
    builder = Tier0Builder(vault, as_of)
    builder.build()

@app.command()
def build_tier1(
    vault: Path = typer.Option(..., help="Path to Vault root"),
    targets: Path = typer.Option(..., help="Path to targets.yaml"),
    extract_edges: bool = typer.Option(False, help="Extract edges (Tier 2)"),
    generate_structure: bool = typer.Option(False, help="Generate Chapter/Section structure nodes"),
    edge_schema: str = typer.Option("v1", help="Edge schema version: v1 (Phase A compatible) or v2 (experimental unified)")
):
    """
    Generate Tier 1 & 2 (Articles & Edges).

    --edge-schema:
      v1: Phase A 互換（既存形式を完全維持）- デフォルト
      v2: 実験用統一スキーマ（refs + containment edges）
    """
    from .core.tier1 import Tier1Builder
    from .core.edge_schema import EdgeSchema

    # スキーマバリデーション
    if edge_schema not in ("v1", "v2"):
        raise typer.BadParameter(f"Invalid edge-schema: {edge_schema}. Must be 'v1' or 'v2'.")

    schema = EdgeSchema.V1 if edge_schema == "v1" else EdgeSchema.V2
    builder = Tier1Builder(vault, targets)
    builder.build(extract_edges, generate_structure=generate_structure, edge_schema=schema)

@app.command()
def enrich_ndl(
    vault: Path = typer.Option(..., help="Path to Vault root"),
    targets: Optional[Path] = typer.Option(None, help="Path to targets.yaml")
):
    """
    Enrich with NDL data.
    """
    from .core.enrichment import Enricher
    enricher = Enricher(vault, targets)
    enricher.enrich()

@app.command()
def summarize(
    vault: Path = typer.Option(..., help="Path to Vault root"),
    targets: Path = typer.Option(..., help="Path to targets.yaml"),
    force: bool = typer.Option(False, help="Regenerate summaries even if they exist")
):
    """
    Generate AI summaries for articles using Gemini API.
    """
    from .core.summarizer import Summarizer
    summarizer = Summarizer(vault, targets, force=force)
    summarizer.summarize()

if __name__ == "__main__":
    app()
