#!/usr/bin/env python3
"""XML workspace utilities for FTL."""

import xml.etree.ElementTree as ET
from xml.dom import minidom
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass, field


@dataclass
class WorkspaceSpec:
    """Specification for creating a workspace."""
    id: str  # "003-routes-crud"
    type: str  # "SPEC" | "BUILD" | "VERIFY"
    mode: str  # "FULL" | "DIRECT"
    status: str  # "active" | "complete" | "blocked"
    delta: list[str]
    verify: str
    framework: Optional[str] = None
    code_context: Optional[dict] = None  # {path, content, exports, imports, lines, language}
    lineage: Optional[dict] = None  # {parent, prior_delivery}
    idioms: Optional[dict] = None  # {required: [], forbidden: []}
    patterns: Optional[list[dict]] = field(default=None)  # [{name, when, insight, saved}]
    failures: Optional[list[dict]] = field(default=None)  # [{name, trigger, fix, cost}]
    preflight: Optional[list[str]] = field(default=None)
    escalation: str = "After 2 failures OR 5 tools: block and document."
    delivered: str = ""


def create_workspace(spec: WorkspaceSpec) -> str:
    """Generate XML workspace from spec."""
    root = ET.Element('workspace', {
        'id': spec.id,
        'type': spec.type,
        'mode': spec.mode,
        'status': spec.status
    })

    # Implementation
    impl = ET.SubElement(root, 'implementation')
    for d in spec.delta:
        ET.SubElement(impl, 'delta').text = d
    ET.SubElement(impl, 'verify').text = spec.verify
    if spec.framework:
        ET.SubElement(impl, 'framework').text = spec.framework

    # Code Context (optional)
    if spec.code_context:
        ctx = ET.SubElement(root, 'code_context')
        file_elem = ET.SubElement(ctx, 'file', {
            'path': spec.code_context.get('path', ''),
            'lines': spec.code_context.get('lines', '')
        })
        content_elem = ET.SubElement(file_elem, 'content')
        content_elem.set('language', spec.code_context.get('language', 'python'))
        content_elem.text = spec.code_context.get('content', '')
        ET.SubElement(file_elem, 'exports').text = spec.code_context.get('exports', '')
        ET.SubElement(file_elem, 'imports').text = spec.code_context.get('imports', '')

        if spec.lineage:
            lineage = ET.SubElement(ctx, 'lineage')
            ET.SubElement(lineage, 'parent').text = spec.lineage.get('parent', 'none')
            ET.SubElement(lineage, 'prior_delivery').text = spec.lineage.get('prior_delivery', '')

    # Framework Idioms (optional)
    if spec.idioms and spec.framework:
        idioms = ET.SubElement(root, 'framework_idioms', {'framework': spec.framework})
        req = ET.SubElement(idioms, 'required')
        for r in spec.idioms.get('required', []):
            ET.SubElement(req, 'idiom').text = r
        forb = ET.SubElement(idioms, 'forbidden')
        for f in spec.idioms.get('forbidden', []):
            ET.SubElement(forb, 'idiom').text = f

    # Prior Knowledge (optional)
    if spec.patterns or spec.failures:
        pk = ET.SubElement(root, 'prior_knowledge')
        for p in (spec.patterns or []):
            pat = ET.SubElement(pk, 'pattern', {'name': p['name'], 'saved': p.get('saved', '0')})
            ET.SubElement(pat, 'when').text = p.get('when', '')
            ET.SubElement(pat, 'insight').text = p.get('insight', '')
        for f in (spec.failures or []):
            fail = ET.SubElement(pk, 'failure', {'name': f['name'], 'cost': f.get('cost', '0')})
            ET.SubElement(fail, 'trigger').text = f.get('trigger', '')
            ET.SubElement(fail, 'fix').text = f.get('fix', '')

    # Preflight
    pf = ET.SubElement(root, 'preflight')
    for cmd in (spec.preflight or ['python -m py_compile <delta>', 'pytest --collect-only -q']):
        ET.SubElement(pf, 'check').text = cmd

    # Escalation
    ET.SubElement(root, 'escalation', {'threshold': '2 failures OR 5 tools'}).text = spec.escalation

    # Delivered
    ET.SubElement(root, 'delivered', {'status': 'pending'}).text = spec.delivered

    # Pretty print
    xml_str = ET.tostring(root, encoding='unicode')
    return minidom.parseString(xml_str).toprettyxml(indent='  ')


def parse_workspace(path: Path) -> dict:
    """Parse XML workspace to dict."""
    tree = ET.parse(path)
    root = tree.getroot()

    result = {
        'id': root.get('id'),
        'type': root.get('type'),
        'mode': root.get('mode'),
        'status': root.get('status'),
        'delta': [d.text for d in root.findall('.//implementation/delta') if d.text],
        'verify': root.findtext('.//verify', ''),
        'framework': root.findtext('.//framework'),
    }

    # Framework Idioms
    idioms_elem = root.find('.//framework_idioms')
    if idioms_elem is not None:
        result['idioms'] = {
            'framework': idioms_elem.get('framework'),
            'required': [i.text for i in idioms_elem.findall('.//required/idiom') if i.text],
            'forbidden': [i.text for i in idioms_elem.findall('.//forbidden/idiom') if i.text]
        }

    # Patterns
    result['patterns'] = [{
        'name': p.get('name'),
        'saved': p.get('saved'),
        'when': p.findtext('when', ''),
        'insight': p.findtext('insight', '')
    } for p in root.findall('.//pattern')]

    # Failures
    result['failures'] = [{
        'name': f.get('name'),
        'cost': f.get('cost'),
        'trigger': f.findtext('trigger', ''),
        'fix': f.findtext('fix', '')
    } for f in root.findall('.//failure')]

    # Code Context
    file_elem = root.find('.//code_context/file')
    if file_elem is not None:
        result['code_context'] = {
            'path': file_elem.get('path'),
            'lines': file_elem.get('lines'),
            'content': file_elem.findtext('content', ''),
            'exports': file_elem.findtext('exports', ''),
            'imports': file_elem.findtext('imports', '')
        }

    # Lineage
    lineage = root.find('.//lineage')
    if lineage is not None:
        result['lineage'] = {
            'parent': lineage.findtext('parent', 'none'),
            'prior_delivery': lineage.findtext('prior_delivery', '')
        }

    # Delivered
    delivered = root.find('.//delivered')
    result['delivered'] = {
        'status': delivered.get('status') if delivered is not None else 'pending',
        'content': delivered.text if delivered is not None else ''
    }

    # Preflight
    result['preflight'] = [c.text for c in root.findall('.//preflight/check') if c.text]

    # Escalation
    esc = root.find('.//escalation')
    result['escalation'] = {
        'threshold': esc.get('threshold') if esc is not None else '2 failures OR 5 tools',
        'action': esc.text if esc is not None else ''
    }

    return result


def update_delivered(path: Path, content: str, status: str = 'complete') -> None:
    """Update delivered element in workspace."""
    tree = ET.parse(path)
    root = tree.getroot()

    delivered = root.find('.//delivered')
    if delivered is not None:
        delivered.text = content
        delivered.set('status', status)

    # Update root status attribute too
    root.set('status', status)

    tree.write(path, encoding='unicode', xml_declaration=True)


def get_status(path: Path) -> str:
    """Quick status check from workspace."""
    tree = ET.parse(path)
    return tree.getroot().get('status', 'unknown')


def rename_workspace(path: Path, new_status: str) -> Path:
    """Rename workspace file with new status."""
    # Parse current filename: NNN_slug_status.xml
    stem = path.stem  # "003_routes-crud_active"
    parts = stem.rsplit('_', 1)  # ["003_routes-crud", "active"]
    new_stem = f"{parts[0]}_{new_status}"
    new_path = path.parent / f"{new_stem}.xml"
    path.rename(new_path)
    return new_path


def list_workspaces(workspace_dir: Path, status_filter: Optional[str] = None) -> list[dict]:
    """List all workspaces with optional status filter."""
    workspaces = []
    for ws_file in sorted(workspace_dir.glob("*.xml")):
        try:
            parsed = parse_workspace(ws_file)
            parsed['path'] = ws_file
            if status_filter is None or parsed['status'] == status_filter:
                workspaces.append(parsed)
        except Exception:
            continue
    return workspaces


def spec_from_dict(d: dict) -> WorkspaceSpec:
    """Create WorkspaceSpec from dictionary (for CLI/JSON input)."""
    return WorkspaceSpec(
        id=d['id'],
        type=d['type'],
        mode=d['mode'],
        status=d.get('status', 'active'),
        delta=d.get('delta', []),
        verify=d.get('verify', ''),
        framework=d.get('framework'),
        code_context=d.get('code_context'),
        lineage=d.get('lineage'),
        idioms=d.get('idioms'),
        patterns=d.get('patterns'),
        failures=d.get('failures'),
        preflight=d.get('preflight'),
        escalation=d.get('escalation', 'After 2 failures OR 5 tools: block and document.'),
        delivered=d.get('delivered', '')
    )


def main():
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(prog='workspace_xml', description='FTL workspace XML utilities')
    sub = parser.add_subparsers(dest='cmd')

    # create: JSON stdin → XML stdout
    create_p = sub.add_parser('create', help='Create workspace XML from JSON spec')
    create_p.add_argument('-o', '--output', type=Path, help='Output file (default: stdout)')

    # parse: XML file → JSON stdout
    parse_p = sub.add_parser('parse', help='Parse workspace XML to JSON')
    parse_p.add_argument('path', type=Path, help='Workspace XML file')

    # update: Update delivered section
    update_p = sub.add_parser('update', help='Update delivered section')
    update_p.add_argument('path', type=Path, help='Workspace XML file')
    update_p.add_argument('--content', required=True, help='Delivered content')
    update_p.add_argument('--status', default='complete', help='Status (default: complete)')

    # rename: Rename workspace with new status
    rename_p = sub.add_parser('rename', help='Rename workspace with new status')
    rename_p.add_argument('path', type=Path, help='Workspace XML file')
    rename_p.add_argument('status', help='New status (active|complete|blocked)')

    # list: List workspaces in directory
    list_p = sub.add_parser('list', help='List workspaces')
    list_p.add_argument('dir', type=Path, nargs='?', default=Path('.ftl/workspace'))
    list_p.add_argument('--status', help='Filter by status')

    # status: Quick status check
    status_p = sub.add_parser('status', help='Get workspace status')
    status_p.add_argument('path', type=Path, help='Workspace XML file')

    args = parser.parse_args()

    if not args.cmd:
        parser.print_help()
        return

    if args.cmd == 'create':
        spec_dict = json.load(sys.stdin)
        spec = spec_from_dict(spec_dict)
        xml_content = create_workspace(spec)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(xml_content)
            print(f"Created: {args.output}")
        else:
            print(xml_content)

    elif args.cmd == 'parse':
        if not args.path.exists():
            print(f"Not found: {args.path}", file=sys.stderr)
            sys.exit(1)
        result = parse_workspace(args.path)
        # Convert Path to string for JSON serialization
        if 'path' in result:
            result['path'] = str(result['path'])
        print(json.dumps(result, indent=2))

    elif args.cmd == 'update':
        if not args.path.exists():
            print(f"Not found: {args.path}", file=sys.stderr)
            sys.exit(1)
        update_delivered(args.path, args.content, args.status)
        print(f"Updated: {args.path}")

    elif args.cmd == 'rename':
        if not args.path.exists():
            print(f"Not found: {args.path}", file=sys.stderr)
            sys.exit(1)
        new_path = rename_workspace(args.path, args.status)
        print(f"Renamed: {args.path} → {new_path}")

    elif args.cmd == 'list':
        if not args.dir.exists():
            print(f"Not found: {args.dir}", file=sys.stderr)
            sys.exit(1)
        workspaces = list_workspaces(args.dir, args.status)
        for ws in workspaces:
            print(f"[{ws['status']:8}] {ws['path'].name}: {ws['id']}")

    elif args.cmd == 'status':
        if not args.path.exists():
            print(f"Not found: {args.path}", file=sys.stderr)
            sys.exit(1)
        print(get_status(args.path))


if __name__ == '__main__':
    main()
