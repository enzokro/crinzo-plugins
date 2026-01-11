#!/usr/bin/env bash
# FTL Router Exploration Capture
# Extracts context from XML workspace file for builder injection

# Find most recent active workspace
WORKSPACE=$(ls -t .ftl/workspace/*_active*.xml 2>/dev/null | head -1)

if [ -z "$WORKSPACE" ]; then
    exit 0  # No active workspace; nothing to capture
fi

mkdir -p .ftl/cache

# Extract context from XML workspace using Python
python3 << EOF > .ftl/cache/exploration_context.md
import xml.etree.ElementTree as ET
from pathlib import Path

workspace = Path("$WORKSPACE")
tree = ET.parse(workspace)
root = tree.getroot()

print("# Exploration Context")
print(f"*From: {workspace.name}*")
print()

# Extract implementation section
print("## Implementation")
for delta in root.findall('.//implementation/delta'):
    if delta.text:
        print(f"Delta: {delta.text}")
verify = root.findtext('.//verify', '')
if verify:
    print(f"Verify: {verify}")
framework = root.findtext('.//framework', '')
if framework:
    print(f"Framework: {framework}")
print()

# Extract code context if present
code_ctx = root.find('.//code_context/file')
if code_ctx is not None:
    print("## Code Context")
    print(f"File: {code_ctx.get('path', 'unknown')}")
    exports = code_ctx.findtext('exports', '')
    if exports:
        print(f"Exports: {exports}")
    imports = code_ctx.findtext('imports', '')
    if imports:
        print(f"Imports: {imports}")
    print()

# Extract framework idioms if present
idioms = root.find('.//framework_idioms')
if idioms is not None:
    print("## Framework Idioms")
    print(f"Framework: {idioms.get('framework', 'unknown')}")
    req = [i.text for i in idioms.findall('.//required/idiom') if i.text]
    if req:
        print("Required:")
        for r in req:
            print(f"  - {r}")
    forb = [i.text for i in idioms.findall('.//forbidden/idiom') if i.text]
    if forb:
        print("Forbidden:")
        for f in forb:
            print(f"  - {f}")
    print()

# Extract prior knowledge if present
patterns = root.findall('.//pattern')
failures = root.findall('.//failure')
if patterns or failures:
    print("## Prior Knowledge")
    for p in patterns:
        name = p.get('name', 'unknown')
        when = p.findtext('when', '')
        insight = p.findtext('insight', '')
        print(f"- Pattern **{name}**: {when} → {insight}")
    for f in failures:
        name = f.get('name', 'unknown')
        trigger = f.findtext('trigger', '')
        fix = f.findtext('fix', '')
        print(f"- Failure **{name}**: {trigger} → {fix}")
EOF

exit 0
