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
    extract_edges: bool = typer.Option(False, help="Extract edges (Tier 2)")
):
    """
    Generate Tier 1 & 2 (Articles & Edges).
    """
    from .core.tier1 import Tier1Builder
    builder = Tier1Builder(vault, targets)
    builder.build(extract_edges)

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

if __name__ == "__main__":
    app()
