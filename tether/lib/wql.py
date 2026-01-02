#!/usr/bin/env python3
"""WQL - Workspace Query Language. Minimal query tool for tether workspaces."""

import re
import sys
import argparse
from pathlib import Path
from collections import defaultdict


def parse_workspace(ws: Path) -> dict:
    """Parse workspace files into index."""
    files = {}
    children = defaultdict(list)

    # First pass: collect all files
    for p in sorted(ws.glob("*.md")):
        m = re.match(r'^(\d{3})_(.+?)_([^_]+?)(?:_from-(\d{3}))?$', p.stem)
        if m:
            seq, slug, status, parent = m.groups()
            files[seq] = {"path": p.name, "slug": slug, "status": status, "parent": parent}

    # Second pass: build children map
    for seq, f in files.items():
        if f["parent"] and f["parent"] in files:
            children[f["parent"]].append(seq)

    return files, children


def cmd_stat(files: dict, args):
    """Status counts and depth stats."""
    if not files:
        print("Empty workspace")
        return

    counts = defaultdict(int)
    depths = defaultdict(int)

    for seq, f in files.items():
        counts[f["status"]] += 1
        # Calculate depth
        depth, cur = 1, seq
        while files.get(cur, {}).get("parent"):
            cur = files[cur]["parent"]
            depth += 1
        depths[depth] += 1

    print(f"Total: {len(files)}")
    print(f"  complete: {counts.get('complete', 0)}")
    print(f"  active:   {counts.get('active', 0)}")
    print(f"  blocked:  {counts.get('blocked', 0)}")
    print(f"\nDepth distribution:")
    for d in sorted(depths):
        print(f"  {d}: {depths[d]}")


def cmd_lineage(files: dict, args):
    """Show ancestors/descendants for a task."""
    if not args.selector:
        print("Usage: wql lineage NNN")
        return

    seq = args.selector.zfill(3)
    if seq not in files:
        print(f"Not found: {seq}")
        return

    # Ancestors
    chain = []
    cur = seq
    while cur and cur in files:
        chain.append(cur)
        cur = files[cur]["parent"]
    chain.reverse()

    print(f"Ancestors: {' → '.join(chain)}")
    for s in chain:
        print(f"  {files[s]['path']}")

    # Descendants
    print(f"\nDescendants of {seq}:")
    for s, f in sorted(files.items()):
        if f["parent"] == seq:
            print(f"  {f['path']}")


def cmd_graph(files: dict, children: dict, args):
    """Tree view of workspace."""
    def print_tree(seq, level=0):
        f = files[seq]
        marker = {"complete": "+", "active": "~", "blocked": "!"}.get(f["status"], " ")
        print("  " * level + f"[{marker}] {f['path']}")
        for child in sorted(children.get(seq, [])):
            print_tree(child, level + 1)

    roots = [s for s, f in files.items() if not f["parent"]]
    for root in sorted(roots):
        print_tree(root)
        print()


def main():
    parser = argparse.ArgumentParser(prog='wql', description='Workspace Query Language')
    parser.add_argument('-w', '--workspace', type=Path, default=Path('./workspace'))

    sub = parser.add_subparsers(dest='cmd')
    sub.add_parser('stat', aliases=['s'], help='Status counts')
    lin = sub.add_parser('lineage', aliases=['l'], help='Show lineage')
    lin.add_argument('selector', nargs='?', help='Task number')
    sub.add_parser('graph', aliases=['g'], help='Tree view')

    args = parser.parse_args()

    if not args.cmd:
        parser.print_help()
        return

    if not args.workspace.exists():
        print(f"No workspace: {args.workspace}", file=sys.stderr)
        sys.exit(1)

    files, children = parse_workspace(args.workspace)

    if args.cmd in ('stat', 's'):
        cmd_stat(files, args)
    elif args.cmd in ('lineage', 'l'):
        cmd_lineage(files, args)
    elif args.cmd in ('graph', 'g'):
        cmd_graph(files, children, args)


if __name__ == '__main__':
    main()
