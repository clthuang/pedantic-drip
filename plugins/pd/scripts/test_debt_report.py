#!/usr/bin/env python3
"""FR-8 /pd:test-debt-report — read-only test-debt aggregator.

Per spec FR-8 + design I-5. Stdlib-only.

Aggregates:
- All `docs/features/*/.qa-gate.json` findings with severity in {MED, LOW, MEDIUM}.
- `docs/backlog.md` lines matching `^- \\*\\*#[0-9]+\\*\\* \\[[^/]+/testability\\]` (active only).

Output: 4-column markdown table (File-or-Module | Category | Open Count | Source Features).
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Inlined per design TD-6 — pinned copy of qa-gate-procedure.md §4 helper.
# Widened regex per design fix: [a-zA-Z0-9]+ to handle .PY, .tsx, .JSON etc.
_NORMALIZE_LOC_RE = re.compile(r'([^/\s]+\.[a-zA-Z0-9]+:\d+)')

# Active testability backlog tag pattern.
_BACKLOG_TESTABILITY_RE = re.compile(r'^- \*\*#(\d+)\*\* \[[^/]+/testability\]')

REVIEWER_CATEGORY_MAP = {
    'pd:test-deepener': 'testability',
    'pd:security-reviewer': 'security',
    'pd:code-quality-reviewer': 'quality',
    'pd:implementation-reviewer': 'implementation',
}


def normalize_location(loc: str) -> str:
    """Inlined per spec FR-8 + TD-6. Pinned copy of qa-gate-procedure.md §4 helper."""
    m = _NORMALIZE_LOC_RE.search(loc)
    if m:
        return m.group(1)
    return loc.strip().lower()


def derive_category(finding: dict) -> str:
    """Per spec FR-8 §Category derivation rule."""
    if 'category' in finding:
        return finding['category']
    reviewer = finding.get('reviewer', '')
    return REVIEWER_CATEGORY_MAP.get(reviewer, 'uncategorized')


def parse_qa_gate_files(features_dir: Path) -> list:
    """Glob features_dir/*/.qa-gate.json; collect MED/LOW findings."""
    rows = []
    for qa_path in features_dir.glob('*/.qa-gate.json'):
        try:
            data = json.loads(qa_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        feature_id = qa_path.parent.name
        for finding in data.get('findings', []):
            sev = (finding.get('severity') or '').lower()
            sec_sev = (finding.get('securitySeverity') or '').lower()
            if sev in ('warning', 'suggestion') or sec_sev in ('medium', 'low'):
                rows.append({
                    'location': normalize_location(finding.get('location', '')),
                    'category': derive_category(finding),
                    'feature': feature_id,
                })
    return rows


def parse_backlog_testability(backlog_path: Path) -> list:
    """Parse active testability tags from backlog.md."""
    rows = []
    if not backlog_path.exists():
        return rows
    for line in backlog_path.read_text().splitlines():
        # Skip strikethrough (closed).
        if line.startswith('- ~~'):
            continue
        m = _BACKLOG_TESTABILITY_RE.match(line)
        if m:
            rows.append({
                'location': 'backlog',
                'category': 'testability',
                'feature': f'#{m.group(1)}',
            })
    return rows


def aggregate(features_dir: Path, backlog_path: Path) -> list:
    """Group by (location, category); count + collect feature sources."""
    rows = parse_qa_gate_files(features_dir) + parse_backlog_testability(backlog_path)
    grouped = defaultdict(lambda: {'count': 0, 'features': set()})
    for r in rows:
        key = (r['location'], r['category'])
        grouped[key]['count'] += 1
        grouped[key]['features'].add(r['feature'])
    out = []
    for (loc, cat), val in grouped.items():
        out.append({
            'location': loc,
            'category': cat,
            'count': val['count'],
            'features': sorted(val['features']),
        })
    # Sort: count DESC, then location ASC.
    out.sort(key=lambda r: (-r['count'], r['location']))
    return out


def render_table(rows: list) -> str:
    """4-column markdown table per spec FR-8 output."""
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    lines = [
        f"# Test Debt Report ({today})",
        "",
        "| File or Module | Category | Open Count | Source Features |",
        "|----------------|----------|------------|-----------------|",
    ]
    for r in rows:
        sources = ', '.join(r['features'])
        lines.append(f"| {r['location']} | {r['category']} | {r['count']} | {sources} |")
    lines.append("")
    total_items = sum(r['count'] for r in rows)
    n_files = len(rows)
    lines.append(f"Total: {total_items} open items across {n_files} files.")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Test debt aggregator (FR-8).")
    parser.add_argument('--features-dir', default='docs/features',
                        help='Glob features_dir/*/.qa-gate.json')
    parser.add_argument('--backlog-path', default='docs/backlog.md',
                        help='Backlog file path.')
    args = parser.parse_args()

    rows = aggregate(Path(args.features_dir), Path(args.backlog_path))
    print(render_table(rows))
    return 0


if __name__ == '__main__':
    sys.exit(main())
