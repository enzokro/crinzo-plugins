#!/usr/bin/env python3
"""Generate workspace XML files from Planner's JSON output.

This script replaces the Router agent by:
1. Taking Planner's JSON task specs
2. Injecting memory (patterns/failures) by tag
3. Reading code context from Delta files
4. Generating workspace XML files

Usage:
    # From Planner JSON file
    python3 workspace_from_plan.py plan.json

    # From stdin (piped from Planner output)
    cat planner_output.json | python3 workspace_from_plan.py -

    # Generate workspace for specific task only
    python3 workspace_from_plan.py plan.json --task 002
"""

import json
import sys
from pathlib import Path
from typing import Optional

# Ensure sibling modules are importable regardless of working directory
_lib_dir = Path(__file__).resolve().parent
if str(_lib_dir) not in sys.path:
    sys.path.insert(0, str(_lib_dir))

from memory import load_memory, get_context_for_task
from workspace_xml import spec_from_dict, create_workspace

# Session-level file cache for stable files (test files don't change during campaign)
_file_cache: dict[str, str] = {}


def get_cached_file_content(path: Path, max_lines: int = 60) -> Optional[str]:
    """Return cached content or read and cache.

    Caches files at session level to avoid redundant reads when
    multiple tasks reference the same file.
    """
    cache_key = str(path.resolve())
    if cache_key in _file_cache:
        return _file_cache[cache_key]

    if not path.exists():
        return None

    try:
        lines = path.read_text().split('\n')[:max_lines]
        content = '\n'.join(lines)
        _file_cache[cache_key] = content
        return content
    except Exception:
        return None


def read_code_context(delta_files: list[str], project_root: Path) -> Optional[dict]:
    """Read code context from first Delta file (first 60 lines).

    Uses session-level caching to avoid redundant reads when
    multiple tasks reference the same file.
    """
    for delta in delta_files:
        delta_path = project_root / delta

        # Use cached content if available
        content = get_cached_file_content(delta_path, max_lines=60)
        if content is None:
            continue

        lines = content.split('\n')

        # Extract basic info
        exports = []
        imports = []
        for line in lines:
            if line.startswith('def ') or line.startswith('class '):
                name = line.split('(')[0].replace('def ', '').replace('class ', '').strip()
                exports.append(name)
            elif line.startswith('from ') or line.startswith('import '):
                imports.append(line.strip())

        return {
            'path': delta,
            'lines': f'1-{len(lines)}',
            'language': 'python' if delta.endswith('.py') else 'text',
            'content': content,
            'exports': ', '.join(exports[:5]),
            'imports': ', '.join(imports[:5])
        }
    return None


def get_lineage(task: dict, plan: dict) -> Optional[dict]:
    """Get lineage info from parent task."""
    depends = task.get('depends', 'none')
    if depends == 'none' or not depends:
        return None

    # Find parent task
    parent_seq = depends if isinstance(depends, str) else str(depends)
    for t in plan.get('tasks', []):
        if t.get('seq') == parent_seq:
            return {
                'parent': f"{t['seq']}-{t['slug']}",
                'prior_delivery': f"Task {t['seq']} ({t['type']}): {t.get('slug', '')}"
            }
    return None


def filter_failures_by_task_type(failures: list, task_type: str) -> list:
    """Filter failures based on task type (lazy memory injection).

    - VERIFY: No failures needed (just runs tests)
    - SPEC: Only test/fixture-related failures
    - BUILD: All failures (framework issues possible)
    """
    if task_type == 'VERIFY':
        return []  # VERIFY tasks don't need failure patterns

    if task_type == 'SPEC':
        # Only test and fixture-related failures
        return [f for f in failures
                if 'test' in f.get('name', '') or 'fixture' in f.get('name', '')]

    # BUILD and other types get all failures
    return failures


def get_memory_for_task(memory_path: Path, task: dict, plan: dict) -> tuple[list, list]:
    """Get patterns and failures relevant to this task.

    Uses lazy memory injection to reduce context size:
    - VERIFY tasks: 0 failures (just run tests)
    - SPEC tasks: ~6 failures (test/fixture only)
    - BUILD tasks: all failures (framework issues possible)
    """
    memory = load_memory(memory_path)
    task_type = task.get('type', '').upper()

    # Build tags from: framework, type, delta file extensions
    tags = []
    framework = plan.get('framework', '').lower()
    if framework and framework != 'none':
        tags.append(framework)

    # Add python tag if any delta is .py
    if any(d.endswith('.py') for d in task.get('delta', [])):
        tags.append('python')

    # Add task type
    if task_type:
        tags.append(task_type.lower())

    # Add testing tag for test files
    if any('test' in d for d in task.get('delta', [])):
        tags.append('testing')

    context = get_context_for_task(memory, tags if tags else None)

    # Also filter by failure names specified in task
    task_failures = task.get('failures', [])

    patterns = [
        {'name': d['name'], 'saved': str(d.get('tokens_saved', 0)),
         'when': d.get('trigger', ''), 'insight': d.get('insight', '')}
        for d in context.get('discoveries', [])[:3]  # Top 3 discoveries
    ]

    # Get all failures from context, then apply task-type filter
    all_failures = [
        {'name': f['name'], 'cost': str(f.get('cost', 0)),
         'trigger': f.get('trigger', ''), 'fix': f.get('fix', '')}
        for f in context.get('failures', [])
    ]

    # Apply lazy memory injection filter
    failures = filter_failures_by_task_type(all_failures, task_type)

    # Limit to top 5 after filtering
    failures = failures[:5]

    # Prioritize failures named in task spec
    if task_failures:
        named_failures = [f for f in failures if f['name'] in task_failures]
        other_failures = [f for f in failures if f['name'] not in task_failures]
        failures = named_failures + other_failures[:max(0, 5-len(named_failures))]

    return patterns, failures


def task_to_workspace_spec(task: dict, plan: dict, project_root: Path, memory_path: Path) -> dict:
    """Convert a Planner task to a workspace spec dict."""
    patterns, failures = get_memory_for_task(memory_path, task, plan)
    code_context = read_code_context(task.get('delta', []), project_root)
    lineage = get_lineage(task, plan)

    spec = {
        'id': f"{task['seq']}-{task['slug']}",
        'type': task['type'],
        'mode': task.get('mode', 'FULL'),
        'status': 'active',
        'delta': task.get('delta', []),
        'verify': task.get('verify', ''),
        'preflight': task.get('preflight', []),
        'escalation': 'After 2 failures OR 5 tools: block and document.'
    }

    # Optional fields
    framework = plan.get('framework')
    if framework and framework != 'none':
        spec['framework'] = framework
        idioms = plan.get('idioms')
        if idioms:
            spec['idioms'] = idioms

    if code_context:
        spec['code_context'] = code_context

    if lineage:
        spec['lineage'] = lineage

    if patterns:
        spec['patterns'] = patterns

    if failures:
        spec['failures'] = failures

    return spec


def generate_workspace(task: dict, plan: dict, project_root: Path,
                       memory_path: Path, workspace_dir: Path) -> Path:
    """Generate workspace XML file for a task."""
    spec_dict = task_to_workspace_spec(task, plan, project_root, memory_path)
    spec = spec_from_dict(spec_dict)
    xml_content = create_workspace(spec)

    # Write to workspace directory
    filename = f"{task['seq']}_{task['slug']}_active.xml"
    output_path = workspace_dir / filename
    workspace_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text(xml_content)

    return output_path


def generate_all_workspaces(plan: dict, project_root: Path,
                            memory_path: Path, workspace_dir: Path,
                            task_filter: Optional[str] = None) -> list[Path]:
    """Generate workspace files for all tasks (or filtered task)."""
    generated = []

    for task in plan.get('tasks', []):
        # Skip if filter specified and doesn't match
        if task_filter and task.get('seq') != task_filter:
            continue

        # Skip DIRECT mode tasks (no workspace needed)
        if task.get('mode') == 'DIRECT':
            print(f"Skipping {task['seq']}-{task['slug']}: DIRECT mode (no workspace)")
            continue

        output_path = generate_workspace(task, plan, project_root, memory_path, workspace_dir)
        generated.append(output_path)
        print(f"Created: {output_path}")

    return generated


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Generate workspace XML from Planner JSON',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('input', help='Plan JSON file (or - for stdin)')
    parser.add_argument('--task', help='Generate only this task (by seq number)')
    parser.add_argument('--project', type=Path, default=Path('.'),
                        help='Project root directory (default: current dir)')
    parser.add_argument('--memory', type=Path, default=Path('.ftl/memory.json'),
                        help='Memory file path (default: .ftl/memory.json)')
    parser.add_argument('--output', type=Path, default=Path('.ftl/workspace'),
                        help='Workspace output directory (default: .ftl/workspace)')

    args = parser.parse_args()

    # Read plan JSON
    if args.input == '-':
        plan = json.load(sys.stdin)
    else:
        plan = json.loads(Path(args.input).read_text())

    # Resolve paths relative to project root
    project_root = args.project.resolve()
    memory_path = project_root / args.memory if not args.memory.is_absolute() else args.memory
    workspace_dir = project_root / args.output if not args.output.is_absolute() else args.output

    # Generate workspaces
    generated = generate_all_workspaces(
        plan, project_root, memory_path, workspace_dir, args.task
    )

    print(f"\nGenerated {len(generated)} workspace(s)")
    return 0 if generated else 1


if __name__ == '__main__':
    sys.exit(main())
