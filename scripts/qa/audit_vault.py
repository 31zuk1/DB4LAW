#!/usr/bin/env python3
"""
DB4LAW Vault Audit Script

Comprehensive audit tool for verifying Vault integrity including:
- Provenance verification
- Metadata schema validation
- Range node (deleted articles) consistency
- WikiLink integrity
- Known regression patterns

Usage:
    python scripts/qa/audit_vault.py --vault ./Vault --targets targets.yaml
    python scripts/qa/audit_vault.py --vault ./Vault --targets targets.yaml --fix-safe
    python scripts/qa/audit_vault.py --vault ./Vault --targets targets.yaml --report-only
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

import yaml

from legalkg.core.provenance import verify_manifest, needs_regeneration
from legalkg.utils.markdown import parse_frontmatter, serialize_frontmatter


# ============================================================================
# Target Laws Resolution
# ============================================================================

def get_target_law_names(targets_path: Path, vault_root: Path) -> Set[str]:
    """
    Read targets.yaml and resolve law IDs to law names.

    Returns a set of law directory names (e.g., {'刑法', '民法', ...}).
    """
    if not targets_path or not targets_path.exists():
        return set()

    with open(targets_path, 'r', encoding='utf-8') as f:
        targets_data = yaml.safe_load(f)

    law_ids = set(targets_data.get('targets', []))

    # Build law_id -> law_name mapping from Vault
    law_names = set()
    laws_dir = vault_root / 'laws'

    if not laws_dir.exists():
        return set()

    for law_dir in laws_dir.iterdir():
        if not law_dir.is_dir():
            continue

        # Check the parent law file for egov_law_id
        parent_file = law_dir / f"{law_dir.name}.md"
        if not parent_file.exists():
            continue

        try:
            content = parent_file.read_text(encoding='utf-8')
            doc = parse_frontmatter(content)
            if doc and doc.metadata:
                egov_id = doc.metadata.get('egov_law_id')
                if egov_id in law_ids:
                    law_names.add(law_dir.name)
        except Exception:
            continue

    return law_names


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class AuditIssue:
    """An issue found during audit."""
    category: str  # provenance, metadata, range_node, wikilink, regression
    severity: str  # critical, warning, info
    file_path: str
    message: str
    line_no: Optional[int] = None
    context: Optional[str] = None
    auto_fixable: bool = False
    fix_applied: bool = False
    fix_description: Optional[str] = None


@dataclass
class RangeNode:
    """Represents a deleted article range node."""
    file_path: str
    start_num: int
    end_num: int
    law_name: str


@dataclass
class AuditResult:
    """Complete audit result."""
    timestamp: str
    git_commit: str
    vault_path: str
    targets_path: Optional[str]

    # Summary counts
    total_files_scanned: int = 0
    total_issues: int = 0

    # Issues by category
    issues: List[AuditIssue] = field(default_factory=list)

    # Safe fixes applied
    fixes_applied: int = 0

    # Range nodes found
    range_nodes: List[RangeNode] = field(default_factory=list)


# ============================================================================
# Metadata Schema Definitions
# ============================================================================

# Required fields per type
REQUIRED_FIELDS = {
    'law': ['id', 'title', 'egov_law_id', 'type'],
    'article': ['id', 'law_id', 'law_name', 'article_num', 'part', 'type'],
    'chapter': ['id', 'law_id', 'chapter_num', 'type'],
    'section': ['id', 'law_id', 'section_num', 'type'],
    'supplement': ['id', 'law_id', 'law_name', 'article_num', 'part', 'type'],
    'amendment_fragment': ['id', 'law_id', 'article_num', 'part', 'type'],
}

# Fields that should not be empty strings
NON_EMPTY_FIELDS = ['law_name', 'id', 'law_id']


# ============================================================================
# Provenance Check
# ============================================================================

def check_provenance(vault_root: Path, targets_path: Optional[Path]) -> List[AuditIssue]:
    """Check Vault provenance against manifest."""
    issues = []

    verification = verify_manifest(vault_root, targets_path)

    if not verification['manifest_exists']:
        issues.append(AuditIssue(
            category='provenance',
            severity='critical',
            file_path=str(vault_root / '.db4law' / 'manifest.json'),
            message='Manifest not found - Vault provenance unknown. Run build-tier1 to generate.',
        ))
        return issues

    for issue_msg in verification['issues']:
        severity = 'critical' if 'mismatch' in issue_msg.lower() else 'warning'
        issues.append(AuditIssue(
            category='provenance',
            severity=severity,
            file_path=str(vault_root / '.db4law' / 'manifest.json'),
            message=issue_msg,
        ))

    return issues


# ============================================================================
# Metadata Schema Validation
# ============================================================================

def validate_metadata(file_path: Path, vault_root: Path) -> List[AuditIssue]:
    """Validate metadata schema for a single file."""
    issues = []

    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception as e:
        issues.append(AuditIssue(
            category='metadata',
            severity='warning',
            file_path=str(file_path.relative_to(vault_root)),
            message=f'Failed to read file: {e}',
        ))
        return issues

    doc = parse_frontmatter(content)
    if doc is None:
        # No frontmatter - might be acceptable for some files
        return issues

    meta = doc.metadata
    file_type = meta.get('type')
    rel_path = str(file_path.relative_to(vault_root))

    if file_type is None:
        issues.append(AuditIssue(
            category='metadata',
            severity='warning',
            file_path=rel_path,
            message='Missing "type" field in frontmatter',
        ))
        return issues

    # Check required fields for this type
    required = REQUIRED_FIELDS.get(file_type, [])
    for field in required:
        if field not in meta:
            issues.append(AuditIssue(
                category='metadata',
                severity='warning',
                file_path=rel_path,
                message=f'Missing required field "{field}" for type "{file_type}"',
            ))

    # Check for empty strings in critical fields
    for field in NON_EMPTY_FIELDS:
        if field in meta and meta[field] == '':
            # Check if we can auto-fix
            can_fix = False
            fix_value = None

            if field == 'law_name':
                # Try to derive from path
                # Path format: laws/{law_name}/...
                parts = rel_path.split('/')
                if len(parts) >= 2 and parts[0] == 'laws':
                    fix_value = parts[1]
                    can_fix = True

            issues.append(AuditIssue(
                category='metadata',
                severity='warning',
                file_path=rel_path,
                message=f'Empty string for field "{field}"',
                auto_fixable=can_fix,
                fix_description=f'Set {field} to "{fix_value}"' if can_fix else None,
            ))

    # Check parent field
    if 'parent' in meta and meta['parent'] is None:
        # For amendment_fragment, parent might legitimately be null if it's top-level
        if file_type != 'amendment_fragment':
            issues.append(AuditIssue(
                category='metadata',
                severity='info',
                file_path=rel_path,
                message='Parent field is null',
            ))

    return issues


def scan_metadata(
    vault_root: Path,
    target_laws: Optional[Set[str]] = None,
    only_prefix: Optional[str] = None
) -> Tuple[List[AuditIssue], int]:
    """
    Scan files for metadata issues.

    If target_laws is provided, only scan files within those law directories.
    Otherwise, scan all files (legacy behavior).
    """
    issues = []
    file_count = 0

    if target_laws:
        # Only scan target law directories
        for law_name in target_laws:
            law_dir = vault_root / 'laws' / law_name
            if not law_dir.exists():
                continue

            for md_file in law_dir.rglob('*.md'):
                # Skip hidden files/directories
                if any(part.startswith('.') for part in md_file.parts):
                    continue

                file_count += 1
                issues.extend(validate_metadata(md_file, vault_root))
    else:
        # Scan all files (legacy behavior)
        search_path = vault_root
        if only_prefix:
            search_path = vault_root / only_prefix

        for md_file in search_path.rglob('*.md'):
            # Skip hidden files/directories
            if any(part.startswith('.') for part in md_file.parts):
                continue
            # Skip reports
            if 'reports' in md_file.parts:
                continue

            file_count += 1
            issues.extend(validate_metadata(md_file, vault_root))

    return issues, file_count


# ============================================================================
# Range Node Analysis
# ============================================================================

def parse_range_node_filename(filename: str) -> Optional[Tuple[int, int]]:
    """Parse a range node filename like '第73:76条.md' or '第38:84条.md'."""
    match = re.match(r'第(\d+):(\d+)条\.md$', filename)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None


def build_range_node_index(vault_root: Path) -> Dict[str, List[RangeNode]]:
    """Build an index of all range nodes by law name."""
    index = defaultdict(list)

    for law_dir in (vault_root / 'laws').iterdir():
        if not law_dir.is_dir():
            continue

        honbun_dir = law_dir / '本文'
        if not honbun_dir.exists():
            continue

        law_name = law_dir.name

        for md_file in honbun_dir.iterdir():
            if not md_file.name.endswith('.md'):
                continue

            range_info = parse_range_node_filename(md_file.name)
            if range_info:
                start, end = range_info
                index[law_name].append(RangeNode(
                    file_path=str(md_file.relative_to(vault_root)),
                    start_num=start,
                    end_num=end,
                    law_name=law_name,
                ))

    return index


def check_range_node_coverage(
    broken_links: List[dict],
    range_index: Dict[str, List[RangeNode]]
) -> List[AuditIssue]:
    """
    Check if broken links to non-existent articles could be resolved by range nodes.

    If an article like 第71条 doesn't exist but a range node 第38:84条 exists,
    the link should redirect to the range node.
    """
    issues = []

    # Pattern to extract article number from path like 'laws/民法/本文/第71条.md'
    article_pattern = re.compile(r'laws/([^/]+)/本文/第(\d+)条\.md$')

    for broken in broken_links:
        target = broken.get('target_path', '')
        match = article_pattern.match(target)

        if not match:
            continue

        law_name = match.group(1)
        article_num = int(match.group(2))

        # Check if this article is covered by a range node
        ranges = range_index.get(law_name, [])
        covering_range = None

        for rn in ranges:
            if rn.start_num <= article_num <= rn.end_num:
                covering_range = rn
                break

        if covering_range:
            issues.append(AuditIssue(
                category='range_node',
                severity='warning',
                file_path=broken.get('source_file', ''),
                message=f'Broken link to {target} could redirect to range node {covering_range.file_path}',
                line_no=broken.get('line_no'),
                context=f'Article {article_num} is within range {covering_range.start_num}-{covering_range.end_num}',
            ))
        else:
            # No covering range - this is a genuine missing article
            issues.append(AuditIssue(
                category='range_node',
                severity='info',
                file_path=broken.get('source_file', ''),
                message=f'Broken link to {target} - no covering range node exists',
                line_no=broken.get('line_no'),
            ))

    return issues


# ============================================================================
# Regression Pattern Detection
# ============================================================================

def check_supplement_enumeration_scope(
    vault_root: Path,
    target_laws: Optional[Set[str]] = None
) -> List[AuditIssue]:
    """
    Detect the known regression pattern: supplement enumeration scope leak.

    Pattern: 「附則第五条、第六条、第八条」where 第八条 incorrectly links to external law
    instead of remaining as plain text reference to amendment's own supplement.
    """
    issues = []

    # Pattern to find supplement enumerations followed by wrongly linked articles
    # Looking for: 附則第N条...、[[laws/...
    pattern = re.compile(
        r'附則第[一二三四五六七八九十百千]+条[^、]*、'  # 附則第N条...、
        r'[^、\[\]]*、'  # possibly more items
        r'\[\[laws/([^/]+)/[^\]]+\|第([一二三四五六七八九十百千]+)条\]\]'  # link to external law
    )

    # Also check for direct pattern
    direct_pattern = re.compile(
        r'附則第[一二三四五六七八九十百千]+条[^、]*、'
        r'第[一二三四五六七八九十百千]+条[^、]*、'
        r'\[\[laws/([^/]+)/本文/第(\d+)条\.md\|'
    )

    # Determine which law directories to scan
    laws_to_scan = target_laws if target_laws else None

    # Scan amendment fragments
    for law_dir in (vault_root / 'laws').iterdir():
        if not law_dir.is_dir():
            continue

        # Skip if not in target laws
        if laws_to_scan and law_dir.name not in laws_to_scan:
            continue

        fuzoku_dir = law_dir / '附則'
        if not fuzoku_dir.exists():
            continue

        law_name = law_dir.name

        for md_file in fuzoku_dir.rglob('*.md'):
            try:
                content = md_file.read_text(encoding='utf-8')
            except Exception:
                continue

            # Check for the pattern
            for line_no, line in enumerate(content.split('\n'), 1):
                # Look for supplement enumeration with external law link
                if '附則第' in line and '[[laws/' in line:
                    # Check if an external law link appears in what looks like supplement enumeration
                    match = pattern.search(line) or direct_pattern.search(line)
                    if match:
                        linked_law = match.group(1)
                        # Only flag if linked to different law
                        if linked_law != law_name:
                            issues.append(AuditIssue(
                                category='regression',
                                severity='warning',
                                file_path=str(md_file.relative_to(vault_root)),
                                message=f'Possible supplement enumeration scope leak: '
                                       f'article in supplement enumeration linked to {linked_law}',
                                line_no=line_no,
                                context=line[:200] + ('...' if len(line) > 200 else ''),
                            ))

    return issues


def check_amendment_fragment_bare_refs(
    vault_root: Path,
    target_laws: Optional[Set[str]] = None
) -> List[AuditIssue]:
    """
    Check that amendment fragments don't have bare references linked to parent law.

    Per 方式B: Bare 第N条 in amendment fragments should NOT be linked,
    as they refer to the amendment law itself (which doesn't exist in e-Gov).
    """
    issues = []

    # Pattern: [[laws/X/本文/第N条.md|第N条]] where X is the parent law
    # and this appears in an amendment fragment without explicit law name prefix

    # Determine which law directories to scan
    laws_to_scan = target_laws if target_laws else None

    for law_dir in (vault_root / 'laws').iterdir():
        if not law_dir.is_dir():
            continue

        # Skip if not in target laws
        if laws_to_scan and law_dir.name not in laws_to_scan:
            continue

        fuzoku_dir = law_dir / '附則'
        if not fuzoku_dir.exists():
            continue

        law_name = law_dir.name

        for md_file in fuzoku_dir.rglob('*.md'):
            try:
                content = md_file.read_text(encoding='utf-8')
            except Exception:
                continue

            # Parse frontmatter to check if amendment_fragment
            doc = parse_frontmatter(content)
            if doc.metadata is None:
                continue
            if doc.metadata.get('type') != 'amendment_fragment':
                continue

            # Look for suspicious patterns
            # Valid: 刑法[[...]]  (explicit law name)
            # Invalid: 公布の日[[...]]  (no law name, bare ref got linked)

            # This is a heuristic check - look for links not preceded by law names
            link_pattern = re.compile(
                r'(?<![法令])\[\[laws/' + re.escape(law_name) + r'/本文/第\d+条\.md\|'
            )

            for line_no, line in enumerate(content.split('\n'), 1):
                for match in link_pattern.finditer(line):
                    # Check context before the link
                    pos = match.start()
                    context_before = line[max(0, pos-30):pos]

                    # Skip if preceded by explicit law name
                    if any(name in context_before for name in [law_name, '本法', 'この法律', '当該法']):
                        continue

                    # This might be a bare reference that got incorrectly linked
                    issues.append(AuditIssue(
                        category='regression',
                        severity='info',
                        file_path=str(md_file.relative_to(vault_root)),
                        message=f'Possible bare reference in amendment fragment linked to parent law',
                        line_no=line_no,
                        context=line[:200] + ('...' if len(line) > 200 else ''),
                    ))

    return issues


# ============================================================================
# Safe Auto-Fix
# ============================================================================

def apply_safe_fixes(issues: List[AuditIssue], vault_root: Path) -> int:
    """
    Apply safe auto-fixes and return count of fixes applied.

    Only fixes that are:
    1. Marked as auto_fixable
    2. Deterministic (same input always gives same output)
    3. Low-risk (won't break anything)
    """
    fixes_applied = 0

    # Group issues by file for batch processing
    by_file = defaultdict(list)
    for issue in issues:
        if issue.auto_fixable and not issue.fix_applied:
            by_file[issue.file_path].append(issue)

    for rel_path, file_issues in by_file.items():
        file_path = vault_root / rel_path

        try:
            content = file_path.read_text(encoding='utf-8')
            doc = parse_frontmatter(content)

            if doc.metadata is None:
                continue

            modified = False

            for issue in file_issues:
                if 'Empty string for field "law_name"' in issue.message:
                    # Derive law_name from path
                    parts = rel_path.split('/')
                    if len(parts) >= 2 and parts[0] == 'laws':
                        doc.metadata['law_name'] = parts[1]
                        issue.fix_applied = True
                        fixes_applied += 1
                        modified = True

            if modified:
                new_content = serialize_frontmatter(doc.metadata, doc.body)
                file_path.write_text(new_content, encoding='utf-8')

        except Exception as e:
            print(f"Warning: Failed to apply fix to {rel_path}: {e}", file=sys.stderr)

    return fixes_applied


# ============================================================================
# Report Generation
# ============================================================================

def generate_audit_report(result: AuditResult, output_path: Path):
    """Generate the audit report in Markdown format."""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# DB4LAW Vault Audit Report\n\n")
        f.write(f"**Generated:** {result.timestamp}\n")
        f.write(f"**Git Commit:** {result.git_commit}\n")
        f.write(f"**Vault Path:** {result.vault_path}\n")
        if result.targets_path:
            f.write(f"**Targets Path:** {result.targets_path}\n")
        f.write("\n")

        # Summary
        f.write("## Summary\n\n")
        f.write(f"- **Files Scanned:** {result.total_files_scanned:,}\n")
        f.write(f"- **Total Issues:** {result.total_issues:,}\n")
        f.write(f"- **Safe Fixes Applied:** {result.fixes_applied:,}\n")
        f.write(f"- **Range Nodes Found:** {len(result.range_nodes):,}\n")
        f.write("\n")

        # Issues by category
        by_category = defaultdict(list)
        for issue in result.issues:
            by_category[issue.category].append(issue)

        # Critical issues first
        critical = [i for i in result.issues if i.severity == 'critical']
        if critical:
            f.write("## Critical Issues (Requires Immediate Attention)\n\n")
            for issue in critical:
                f.write(f"### {issue.category}: {issue.file_path}\n\n")
                f.write(f"**{issue.message}**\n\n")
                if issue.context:
                    f.write(f"Context: `{issue.context[:100]}...`\n\n")

        # Issues requiring review (not auto-fixable)
        needs_review = [i for i in result.issues
                       if i.severity == 'warning' and not i.auto_fixable]
        if needs_review:
            f.write("## Issues Requiring Review\n\n")
            f.write("These issues need manual review and decision:\n\n")

            for issue in needs_review:
                f.write(f"- **[{issue.category}]** `{issue.file_path}`")
                if issue.line_no:
                    f.write(f" (L{issue.line_no})")
                f.write(f": {issue.message}\n")
                if issue.context:
                    f.write(f"  - Context: `{issue.context[:80]}...`\n")
            f.write("\n")

        # Auto-fixed issues
        auto_fixed = [i for i in result.issues if i.fix_applied]
        if auto_fixed:
            f.write("## Safely Auto-Fixed Issues\n\n")
            for issue in auto_fixed:
                f.write(f"- `{issue.file_path}`: {issue.message}")
                if issue.fix_description:
                    f.write(f" -> {issue.fix_description}")
                f.write("\n")
            f.write("\n")

        # Info-level issues (collapsible in future)
        info_issues = [i for i in result.issues if i.severity == 'info']
        if info_issues:
            f.write("## Informational Findings\n\n")
            f.write(f"Found {len(info_issues)} informational items (low priority).\n\n")

            # Show first few
            for issue in info_issues[:20]:
                f.write(f"- `{issue.file_path}`: {issue.message}\n")
            if len(info_issues) > 20:
                f.write(f"\n... and {len(info_issues) - 20} more\n")
            f.write("\n")

        # Range nodes summary
        if result.range_nodes:
            f.write("## Range Nodes (Deleted Articles)\n\n")
            f.write("These range nodes represent deleted article ranges:\n\n")

            by_law = defaultdict(list)
            for rn in result.range_nodes:
                by_law[rn.law_name].append(rn)

            for law_name, nodes in sorted(by_law.items()):
                f.write(f"### {law_name}\n\n")
                for rn in sorted(nodes, key=lambda x: x.start_num):
                    f.write(f"- 第{rn.start_num}条〜第{rn.end_num}条: `{rn.file_path}`\n")
                f.write("\n")


def generate_json_report(result: AuditResult, output_path: Path):
    """Generate machine-readable JSON report."""
    data = {
        'timestamp': result.timestamp,
        'git_commit': result.git_commit,
        'vault_path': result.vault_path,
        'targets_path': result.targets_path,
        'summary': {
            'files_scanned': result.total_files_scanned,
            'total_issues': result.total_issues,
            'fixes_applied': result.fixes_applied,
            'range_nodes_count': len(result.range_nodes),
        },
        'issues': [asdict(i) for i in result.issues],
        'range_nodes': [asdict(rn) for rn in result.range_nodes],
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='DB4LAW Vault Audit Script'
    )
    parser.add_argument(
        '--vault',
        type=Path,
        default=Path('./Vault'),
        help='Path to Vault root (default: ./Vault)'
    )
    parser.add_argument(
        '--targets',
        type=Path,
        default=None,
        help='Path to targets.yaml for provenance verification'
    )
    parser.add_argument(
        '--fix-safe',
        action='store_true',
        help='Apply safe auto-fixes'
    )
    parser.add_argument(
        '--report-only',
        action='store_true',
        help='Only generate report, no fixes'
    )
    parser.add_argument(
        '--only-prefix',
        type=str,
        default='laws/',
        help='Limit scan to specific prefix (default: laws/)'
    )

    args = parser.parse_args()

    vault_root = args.vault.resolve()
    if not vault_root.exists():
        print(f"Error: Vault not found: {vault_root}", file=sys.stderr)
        sys.exit(2)

    # Get git commit
    import subprocess
    try:
        git_result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            capture_output=True, text=True, timeout=5
        )
        git_commit = git_result.stdout.strip() if git_result.returncode == 0 else 'unknown'
    except Exception:
        git_commit = 'unknown'

    # Initialize result
    result = AuditResult(
        timestamp=datetime.now(timezone.utc).isoformat(),
        git_commit=git_commit,
        vault_path=str(vault_root),
        targets_path=str(args.targets) if args.targets else None,
    )

    print("=" * 60)
    print("DB4LAW Vault Audit")
    print("=" * 60)

    # Resolve target laws from targets.yaml
    target_laws = None
    if args.targets:
        target_laws = get_target_law_names(args.targets, vault_root)
        print(f"\nTarget laws: {len(target_laws)} ({', '.join(sorted(target_laws)[:5])}{'...' if len(target_laws) > 5 else ''})")

    # A. Provenance Check
    print("\n[A] Checking provenance...")
    provenance_issues = check_provenance(vault_root, args.targets)
    result.issues.extend(provenance_issues)
    print(f"    Found {len(provenance_issues)} provenance issues")

    # B. Metadata Schema Validation (only target laws)
    print("\n[B] Validating metadata schemas...")
    metadata_issues, file_count = scan_metadata(vault_root, target_laws, args.only_prefix)
    result.issues.extend(metadata_issues)
    result.total_files_scanned = file_count
    print(f"    Scanned {file_count:,} files, found {len(metadata_issues)} metadata issues")

    # C. Range Node Analysis
    print("\n[C] Analyzing range nodes...")
    range_index = build_range_node_index(vault_root)
    total_ranges = sum(len(v) for v in range_index.values())
    print(f"    Found {total_ranges} range nodes across {len(range_index)} laws")

    # Store range nodes
    for law_name, nodes in range_index.items():
        result.range_nodes.extend(nodes)

    # D. WikiLink Check Integration
    print("\n[D] Loading WikiLink check results...")
    broken_links_path = vault_root / 'reports' / 'link_check_broken.json'
    if broken_links_path.exists():
        with open(broken_links_path, 'r', encoding='utf-8') as f:
            broken_data = json.load(f)
        broken_links = broken_data.get('broken_links', [])
        print(f"    Found {len(broken_links)} broken links")

        # Check range node coverage
        range_issues = check_range_node_coverage(broken_links, range_index)
        result.issues.extend(range_issues)
        print(f"    {len([i for i in range_issues if 'could redirect' in i.message])} "
              "could potentially redirect to range nodes")
    else:
        print("    No broken links report found - run check_wikilinks.py first")

    # E. Regression Pattern Detection (only target laws)
    print("\n[E] Checking for known regression patterns...")

    print("    - Checking supplement enumeration scope...")
    scope_issues = check_supplement_enumeration_scope(vault_root, target_laws)
    result.issues.extend(scope_issues)
    print(f"      Found {len(scope_issues)} potential scope leak issues")

    print("    - Checking amendment fragment bare refs...")
    bare_ref_issues = check_amendment_fragment_bare_refs(vault_root, target_laws)
    result.issues.extend(bare_ref_issues)
    print(f"      Found {len(bare_ref_issues)} potential bare ref issues")

    result.total_issues = len(result.issues)

    # Apply safe fixes if requested
    if args.fix_safe and not args.report_only:
        print("\n[F] Applying safe fixes...")
        fixes = apply_safe_fixes(result.issues, vault_root)
        result.fixes_applied = fixes
        print(f"    Applied {fixes} safe fixes")

    # Generate reports
    print("\n[G] Generating reports...")
    reports_dir = vault_root / 'reports'
    reports_dir.mkdir(exist_ok=True)

    md_report = reports_dir / 'audit_report.md'
    json_report = reports_dir / 'audit_report.json'

    generate_audit_report(result, md_report)
    generate_json_report(result, json_report)

    print(f"    - {md_report}")
    print(f"    - {json_report}")

    # Summary
    print("\n" + "=" * 60)
    print("Audit Complete")
    print("=" * 60)

    critical = len([i for i in result.issues if i.severity == 'critical'])
    warnings = len([i for i in result.issues if i.severity == 'warning'])
    info = len([i for i in result.issues if i.severity == 'info'])

    print(f"  Critical:  {critical}")
    print(f"  Warnings:  {warnings}")
    print(f"  Info:      {info}")
    print(f"  Fixes:     {result.fixes_applied}")

    # Exit code
    # In --report-only mode, always exit 0 (CI will check specific conditions separately)
    if args.report_only:
        sys.exit(0)
    elif critical > 0:
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
