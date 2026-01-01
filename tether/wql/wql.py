#!/usr/bin/env python3
"""
WQL - Workspace Query Language
A query language for Tether workspace knowledge graphs.
"""

import re
import sys
import json
import argparse
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Set
from collections import defaultdict


@dataclass
class WorkspaceFile:
    """Represents a parsed workspace file."""
    path: Path
    sequence: str
    slug: str
    status: str
    parent: Optional[str] = None
    parent_slug: Optional[str] = None  # For resolving parent in multi-chain workspaces
    format: str = "nnn"  # "nnn" or "date"

    @property
    def key(self) -> str:
        """Unique key for this file (sequence_slug)."""
        return f"{self.sequence}_{self.slug}"

    @classmethod
    def from_path(cls, path: Path) -> Optional['WorkspaceFile']:
        """Parse a workspace file from its path."""
        name = path.stem

        # Pattern: NNN_slug_status[_from-NNN]
        nnn_pattern = r'^(\d{3})_(.+?)_([^_]+?)(?:_from-(\d{3}))?$'
        match = re.match(nnn_pattern, name)
        if match:
            return cls(
                path=path,
                sequence=match.group(1),
                slug=match.group(2),
                status=match.group(3),
                parent=match.group(4),
                format="nnn"
            )

        # Pattern: YYYYMMDD_slug_status (legacy)
        date_pattern = r'^(\d{8})_(.+?)_([^_]+)$'
        match = re.match(date_pattern, name)
        if match:
            return cls(
                path=path,
                sequence=match.group(1),
                slug=match.group(2),
                status=match.group(3),
                format="date"
            )

        return None


class WorkspaceIndex:
    """Index of workspace files with lineage relationships."""

    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path
        self.files: Dict[str, WorkspaceFile] = {}  # key -> WorkspaceFile
        self.by_seq: Dict[str, List[str]] = defaultdict(list)  # seq -> [keys]
        self.children: Dict[str, List[str]] = defaultdict(list)  # key -> [child keys]
        self._build_index()

    def _build_index(self):
        """Build the index from workspace files."""
        # First pass: collect all files
        for path in sorted(self.workspace_path.glob("*.md")):
            wf = WorkspaceFile.from_path(path)
            if wf:
                self.files[wf.key] = wf
                self.by_seq[wf.sequence].append(wf.key)

        # Second pass: resolve parent relationships
        for key, wf in self.files.items():
            if wf.parent:
                # Find parent by sequence number
                # If multiple files with same parent seq, try to find matching chain
                parent_keys = self.by_seq.get(wf.parent, [])
                if len(parent_keys) == 1:
                    parent_key = parent_keys[0]
                    self.children[parent_key].append(key)
                elif len(parent_keys) > 1:
                    # Heuristic: look for slug overlap or content reference
                    # For now, use the first one (could be improved)
                    parent_key = parent_keys[0]
                    self.children[parent_key].append(key)
    
    def _resolve_key(self, selector: str) -> Optional[str]:
        """Resolve a selector (seq or key) to a file key."""
        if selector in self.files:
            return selector
        # Try as sequence number
        keys = self.by_seq.get(selector, [])
        if len(keys) == 1:
            return keys[0]
        if len(keys) > 1:
            return keys[0]  # Return first match
        # Try partial match on filename
        for key in self.files:
            if selector in key:
                return key
        return None

    def _find_parent_key(self, wf: WorkspaceFile) -> Optional[str]:
        """Find the key of a file's parent."""
        if not wf.parent:
            return None
        parent_keys = self.by_seq.get(wf.parent, [])
        if parent_keys:
            return parent_keys[0]
        return None

    def get_ancestors(self, key: str) -> List[str]:
        """Get all ancestors of a file (oldest first)."""
        chain = []
        current = key
        while current:
            chain.append(current)
            wf = self.files.get(current)
            if wf:
                current = self._find_parent_key(wf)
            else:
                current = None
        return list(reversed(chain))

    def get_descendants(self, key: str) -> List[str]:
        """Get all descendants (breadth-first)."""
        result = []
        queue = list(self.children.get(key, []))
        while queue:
            current = queue.pop(0)
            result.append(current)
            queue.extend(self.children.get(current, []))
        return result

    def get_depth(self, key: str) -> int:
        """Get the depth of a file (1 = root)."""
        return len(self.get_ancestors(key))

    def get_orphans(self) -> List[str]:
        """Find files with invalid parent references."""
        orphans = []
        for key, wf in self.files.items():
            if wf.parent:
                parent_keys = self.by_seq.get(wf.parent, [])
                if not parent_keys:
                    orphans.append(key)
        return orphans

    def get_roots(self) -> List[str]:
        """Get all root files (no parent)."""
        return [key for key, wf in self.files.items() if not wf.parent]

    def get_leaves(self) -> List[str]:
        """Get all leaf files (no children)."""
        return [key for key in self.files if key not in self.children]

    def get_longest_chain(self) -> List[str]:
        """Find the longest lineage chain."""
        longest = []
        for key in self.files:
            chain = self.get_ancestors(key)
            if len(chain) > len(longest):
                longest = chain
        return longest

    def get_section(self, key: str, section: str) -> str:
        """Extract a section from a workspace file."""
        wf = self.files.get(key)
        if not wf:
            return ""

        content = wf.path.read_text()

        if section == "path":
            match = re.search(r'^Path:\s*(.+)$', content, re.MULTILINE)
            return match.group(1) if match else ""

        if section == "delta":
            match = re.search(r'^Delta:\s*(.+)$', content, re.MULTILINE)
            return match.group(1) if match else ""

        # Section extraction (## Section to next ##)
        section_map = {
            "anchor": "Anchor",
            "traces": "Thinking Traces",
            "thinking": "Thinking Traces",
            "delivered": "Delivered",
            "blocked": "Blocked",
            "findings": "Key Findings"
        }

        section_name = section_map.get(section, section)
        pattern = rf'^## {re.escape(section_name)}.*?\n(.*?)(?=^## |\Z)'
        match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
        return match.group(1).strip() if match else ""


def cmd_lineage(idx: WorkspaceIndex, args):
    """Handle lineage commands."""
    if args.orphans:
        orphans = idx.get_orphans()
        print("Orphans (parent reference not found):")
        for key in orphans:
            wf = idx.files[key]
            print(f"  {wf.path.name} -> missing parent: {wf.parent}")
        if not orphans:
            print("  (none)")
        return

    if args.longest:
        chain = idx.get_longest_chain()
        seqs = [idx.files[k].sequence for k in chain]
        print(f"Longest chain (depth: {len(chain)}):")
        print(f"  {' -> '.join(seqs)}")
        print()
        for key in chain:
            print(f"  {idx.files[key].path.name}")
        return

    if args.roots:
        roots = idx.get_roots()
        print("Root files (no parent):")
        for key in sorted(roots):
            print(f"  {idx.files[key].path.name}")
        return

    if args.leaves:
        leaves = idx.get_leaves()
        print("Leaf files (no children):")
        for key in sorted(leaves):
            print(f"  {idx.files[key].path.name}")
        return

    if args.min_depth:
        print(f"Chains with depth > {args.min_depth}:")
        print()
        for key in idx.files:
            chain = idx.get_ancestors(key)
            if len(chain) > args.min_depth:
                seqs = [idx.files[k].sequence for k in chain]
                print(f"Chain (depth: {len(chain)}): {' -> '.join(seqs)}")
                for k in chain:
                    print(f"  {idx.files[k].path.name}")
                print()
        return

    if args.selector:
        # Resolve selector to key
        key = idx._resolve_key(args.selector)

        if not key:
            print(f"File not found: {args.selector}")
            return

        if args.direction in ("up", "both"):
            chain = idx.get_ancestors(key)
            seqs = [idx.files[k].sequence for k in chain]
            print(f"Ancestors (depth: {len(chain)}):")
            print(f"  {' -> '.join(seqs)}")
            print()
            for k in chain:
                print(f"  {idx.files[k].path.name}")

        if args.direction == "both":
            print()

        if args.direction in ("down", "both"):
            descendants = idx.get_descendants(key)
            print(f"Descendants of {idx.files[key].sequence}:")
            print(f"  {idx.files[key].path.name}")
            for k in descendants:
                depth = idx.get_depth(k) - idx.get_depth(key)
                indent = "  " * (depth + 1)
                print(f"{indent}{idx.files[k].path.name}")
    else:
        # Show all trees
        print("All lineage trees:")
        print()
        for root in sorted(idx.get_roots()):
            _print_tree(idx, root, 0)
            print()


def _print_tree(idx: WorkspaceIndex, key: str, level: int):
    """Print a tree rooted at key."""
    indent = "  " * level
    wf = idx.files[key]
    status_indicator = {"complete": "+", "active": "~", "blocked": "!"}
    marker = status_indicator.get(wf.status, " ")
    print(f"{indent}[{marker}] {wf.path.name}")
    for child in sorted(idx.children.get(key, [])):
        _print_tree(idx, child, level + 1)


def cmd_grep(idx: WorkspaceIndex, args):
    """Handle grep commands."""
    pattern = re.compile(args.pattern, re.IGNORECASE if args.ignore_case else 0)

    for key in sorted(idx.files.keys()):
        wf = idx.files[key]

        # Apply status filter
        if args.status and wf.status != args.status:
            continue

        # Get content
        if args.section:
            content = idx.get_section(key, args.section)
        else:
            content = wf.path.read_text()

        # Search
        matches = list(pattern.finditer(content))
        if matches:
            if args.names_only:
                print(wf.path.name)
            else:
                print(f"=== {wf.path.name} ===")
                if args.section:
                    print(f"[{args.section}]")
                for i, line in enumerate(content.split('\n'), 1):
                    if pattern.search(line):
                        print(f"{i}: {line}")
                print()


def cmd_find(idx: WorkspaceIndex, args):
    """Handle find commands."""
    results = []

    for key in sorted(idx.files.keys()):
        wf = idx.files[key]

        if args.status and wf.status != args.status:
            continue

        depth = idx.get_depth(key)
        if args.depth and depth != args.depth:
            continue
        if args.min_depth and depth <= args.min_depth:
            continue

        if args.slug_contains and args.slug_contains not in wf.slug:
            continue

        if args.path_no_arrows:
            path = idx.get_section(key, "path")
            if "->" in path:
                continue

        results.append((key, wf))

    for key, wf in results:
        if args.names_only:
            print(wf.path.name)
        else:
            print(wf.path.name)
            print(f"  Status: {wf.status}")
            if wf.parent:
                print(f"  Parent: {wf.parent}")
            print(f"  Depth: {idx.get_depth(key)}")
            print()


def cmd_stat(idx: WorkspaceIndex, args):
    """Handle stat commands."""
    if args.stat_type == "status":
        print("Status Distribution")
        print("===================")
        counts = defaultdict(int)
        for wf in idx.files.values():
            counts[wf.status] += 1
        for status, count in sorted(counts.items()):
            print(f"  {status:12} {count}")
        return

    if args.stat_type == "depth":
        print("Depth Distribution")
        print("==================")
        depths = defaultdict(int)
        for key in idx.files:
            depths[idx.get_depth(key)] += 1
        for d in sorted(depths.keys()):
            print(f"  Depth {d}:  {depths[d]} files")
        return

    if args.stat_type == "blockers":
        print("Blocker Analysis")
        print("================")
        print()
        found = False
        for key, wf in sorted(idx.files.items()):
            if wf.status == "blocked":
                found = True
                print(f"{wf.path.name}:")
                blocked = idx.get_section(key, "blocked")
                for line in blocked.split('\n')[:10]:
                    print(f"  {line}")
                print()
        if not found:
            print("No blocked files found.")
        return

    # Full stats
    total = len(idx.files)
    statuses = defaultdict(int)
    max_depth = 0
    total_words = 0

    for key, wf in idx.files.items():
        statuses[wf.status] += 1
        depth = idx.get_depth(key)
        max_depth = max(max_depth, depth)
        traces = idx.get_section(key, "traces")
        total_words += len(traces.split())

    orphans = len(idx.get_orphans())
    roots = len(idx.get_roots())
    avg_words = total_words // total if total else 0

    print("Workspace Statistics")
    print("====================")
    print()
    print(f"Total files:     {total}")
    print()
    print("By status:")
    for status in ["complete", "active", "blocked"]:
        print(f"  {status:12} {statuses.get(status, 0)}")
    print()
    print("Lineage:")
    print(f"  Max depth:     {max_depth}")
    print(f"  Root files:    {roots}")
    print(f"  Orphans:       {orphans}")
    print()
    print("Content:")
    print(f"  Avg traces:    {avg_words} words")


def cmd_graph(idx: WorkspaceIndex, args):
    """Handle graph commands."""
    if args.format == "dot":
        print("digraph workspace {")
        print("  rankdir=TB;")
        print('  node [shape=box, style="rounded,filled"];')
        print()

        colors = {"complete": "lightgreen", "active": "lightblue", "blocked": "lightyellow"}
        for key, wf in idx.files.items():
            color = colors.get(wf.status, "white")
            label = f"{wf.sequence}\\n{wf.slug}"
            # Use sanitized key for node ID
            node_id = key.replace("-", "_")
            print(f'  "{node_id}" [label="{label}", fillcolor={color}];')

        print()
        for key, wf in idx.files.items():
            if wf.parent:
                parent_key = idx._find_parent_key(wf)
                if parent_key:
                    child_id = key.replace("-", "_")
                    parent_id = parent_key.replace("-", "_")
                    print(f'  "{parent_id}" -> "{child_id}";')

        print("}")
    else:
        # Tree format
        if args.selector:
            key = idx._resolve_key(args.selector)
            if key:
                _print_tree(idx, key, 0)
            else:
                print(f"File not found: {args.selector}")
        else:
            for root in sorted(idx.get_roots()):
                _print_tree(idx, root, 0)
                print()


def main():
    parser = argparse.ArgumentParser(
        prog='wql',
        description='Workspace Query Language - Query Tether workspace knowledge'
    )
    parser.add_argument('-w', '--workspace', type=Path,
                        default=Path('./workspace'),
                        help='Workspace directory')
    parser.add_argument('--json', action='store_true',
                        help='Output as JSON')
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # lineage command
    lin = subparsers.add_parser('lineage', aliases=['lin'],
                                help='Trace ancestry/descendancy chains')
    lin.add_argument('selector', nargs='?', help='File sequence or name')
    lin.add_argument('-u', '--up', dest='direction', action='store_const',
                     const='up', default='up', help='Show ancestors')
    lin.add_argument('-d', '--down', dest='direction', action='store_const',
                     const='down', help='Show descendants')
    lin.add_argument('-b', '--both', dest='direction', action='store_const',
                     const='both', help='Show both')
    lin.add_argument('--min-depth', type=int, help='Minimum chain depth')
    lin.add_argument('--orphans', action='store_true', help='Show orphan files')
    lin.add_argument('--longest', action='store_true', help='Show longest chain')
    lin.add_argument('--roots', action='store_true', help='Show root files')
    lin.add_argument('--leaves', action='store_true', help='Show leaf files')
    
    # grep command
    grep = subparsers.add_parser('grep', aliases=['g'],
                                 help='Search file contents')
    grep.add_argument('pattern', help='Search pattern')
    grep.add_argument('-s', '--section', help='Section to search')
    grep.add_argument('--status', help='Filter by status')
    grep.add_argument('-i', '--ignore-case', action='store_true')
    grep.add_argument('-l', '--names-only', action='store_true')
    
    # find command
    find = subparsers.add_parser('find', aliases=['f'],
                                 help='Find files by criteria')
    find.add_argument('--status', help='Filter by status')
    find.add_argument('--depth', type=int, help='Exact depth')
    find.add_argument('--min-depth', type=int, help='Minimum depth')
    find.add_argument('--slug-contains', help='Slug pattern')
    find.add_argument('-l', '--names-only', action='store_true')
    find.add_argument('--path-no-arrows', action='store_true',
                      help='Paths without arrows')
    
    # stat command
    stat = subparsers.add_parser('stat', aliases=['s'],
                                 help='Workspace statistics')
    stat.add_argument('stat_type', nargs='?',
                      choices=['status', 'depth', 'blockers'],
                      help='Statistic type')
    
    # graph command
    graph = subparsers.add_parser('graph', aliases=['gr'],
                                  help='Visualize relationships')
    graph.add_argument('selector', nargs='?', help='Root file')
    graph.add_argument('--format', choices=['tree', 'dot'], default='tree')
    graph.add_argument('--dot', action='store_const', dest='format',
                       const='dot', help='DOT format output')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    if not args.workspace.exists():
        print(f"Workspace not found: {args.workspace}", file=sys.stderr)
        sys.exit(1)
    
    idx = WorkspaceIndex(args.workspace)
    
    cmd = args.command
    if cmd in ('lineage', 'lin'):
        cmd_lineage(idx, args)
    elif cmd in ('grep', 'g'):
        cmd_grep(idx, args)
    elif cmd in ('find', 'f'):
        cmd_find(idx, args)
    elif cmd in ('stat', 's'):
        cmd_stat(idx, args)
    elif cmd in ('graph', 'gr'):
        cmd_graph(idx, args)


if __name__ == '__main__':
    main()
