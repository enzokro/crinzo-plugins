---
description: Complete a workspace task.
allowed-tools: Bash, Edit, Read, Glob
---

# Close

## Protocol

Find active XML workspace:
```bash
ls .ftl/workspace/*$ARGUMENTS*_active*.xml 2>/dev/null
```

Read XML workspace. Update `<delivered>` element with what was implemented.

Update delivered section and link to git:
```bash
WORKSPACE=$(ls .ftl/workspace/*$ARGUMENTS*_active*.xml 2>/dev/null | head -1)
python3 -c "
import xml.etree.ElementTree as ET
import subprocess
tree = ET.parse('$WORKSPACE')
root = tree.getroot()
delivered = root.find('.//delivered')
commit = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True).stdout.strip() or 'none'
delivered.text = '''Closed manually.
Commit: ''' + commit
delivered.set('status', 'complete')
root.set('status', 'complete')
tree.write('$WORKSPACE', encoding='unicode', xml_declaration=True)
"
```

Rename:
```bash
mv .ftl/workspace/NNN_slug_active.xml .ftl/workspace/NNN_slug_complete.xml
# or _blocked if stuck
```

Report: summary of delivered, final file location.
