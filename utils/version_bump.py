#!/usr/bin/env python3
"""
Bumps the version in all plugin.json files, including the main marketplace.json file.
We are inside the folder crinzo-plugins/utils.

Usage: python3 utils/version_bump.py
"""
import os
import json
import copy
import re
import shutil
from pathlib import Path

# plugin path is one directory up from the utils/ folder
plugin_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# home dir where claude plugins live
ftl_plugin_cache_home = Path('/Users/cck/.claude/plugins/cache/crinzo-plugins/ftl')

new_version = None
old_version_str = None

# change the versions in crinzo-plugins/.claude-plugin/marketplace.json
print("[version_bump] Updating marketplace.json...")
with open(os.path.join(plugin_path, '.claude-plugin/marketplace.json'), 'r') as f:
    marketplace = json.load(f)
    new_marketplace = copy.deepcopy(marketplace)
    for plugin in new_marketplace['plugins']:
        old_version_str = plugin['version']
        new_version = old_version_str.split('.')
        new_version[-1] = str(int(new_version[-1]) + 1)
        plugin['version'] = '.'.join(new_version)
        print(f"  {plugin.get('name', 'plugin')}: {old_version_str} -> {'.'.join(new_version)}")
    with open(os.path.join(plugin_path, '.claude-plugin/marketplace.json'), 'w') as f:
        json.dump(new_marketplace, f, indent=2)

# change the versions in plugin.json files
print("[version_bump] Updating plugin.json files...")
for plugin in ['ftl']:
    plugin_json_path = os.path.join(plugin_path, plugin, '.claude-plugin/plugin.json')
    with open(plugin_json_path, 'r') as f:
        plugin_json = json.load(f)
        new_plugin_json = copy.deepcopy(plugin_json)
        old_version_str = plugin_json['version']
        new_version = old_version_str.split('.')
        new_version[-1] = str(int(new_version[-1]) + 1)
        new_plugin_json['version'] = '.'.join(new_version)
        print(f"  {plugin}/plugin.json: {old_version_str} -> {'.'.join(new_version)}")
        with open(plugin_json_path, 'w') as f:
            json.dump(new_plugin_json, f, indent=2)

# update version in SKILL.md frontmatter
skill_md_path = os.path.join(plugin_path, 'ftl/skills/ftl/SKILL.md')
if os.path.exists(skill_md_path):
    print("[version_bump] Updating SKILL.md frontmatter...")
    with open(skill_md_path, 'r') as f:
        content = f.read()
    # Match version line in YAML frontmatter: version: X.Y.Z
    version_pattern = r'^(version:\s*)(\d+\.\d+\.\d+)(.*)$'
    new_version_str = '.'.join(new_version)
    new_content, count = re.subn(version_pattern, rf'\g<1>{new_version_str}\3', content, flags=re.MULTILINE)
    if count > 0:
        with open(skill_md_path, 'w') as f:
            f.write(new_content)
        print(f"  SKILL.md: updated to {new_version_str}")
    else:
        print(f"  SKILL.md: version pattern not found (skipped)")

# force copy the entire ftl plugin to the ftl cache folder to ensure the new version is used next time
print("[version_bump] Clearing plugin cache...")
if ftl_plugin_cache_home.exists():
    shutil.rmtree(ftl_plugin_cache_home)
    print(f"  Removed: {ftl_plugin_cache_home}")

new_version_str = '.'.join(new_version)
new_cache_dir = os.path.join(ftl_plugin_cache_home, new_version_str)
os.makedirs(new_cache_dir, exist_ok=True)

print(f"[version_bump] Copying ftl to cache: {new_cache_dir}")
shutil.copytree(
    os.path.join(plugin_path, 'ftl'),
    new_cache_dir,
    dirs_exist_ok=True,
    ignore=shutil.ignore_patterns('venv', '.venv', '__pycache__', '*.pyc', '.git')
)

print(f"[version_bump] Done. New version: {new_version_str}")
    

