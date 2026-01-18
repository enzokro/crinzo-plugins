#!/usr/bin/env python3
"""
Bumps the version in all plugin.json files, including the main marketplace.json file.
We are inside the folder crinzo-plugins/utils.
"""
import os 
import json 
import copy
import shutil
from pathlib import Path

# plugin path is one directory up from the utils/ folder
plugin_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# home dir when claude plugins live 
ftl_plugin_cache_home = Path('/Users/cck/.claude/plugins/cache/crinzo-plugins/ftl')

new_version = None

# change the versions in crinzo-plugins/.claude-plugin/marketplace.json
with open(os.path.join(plugin_path, '.claude-plugin/marketplace.json'), 'r') as f:
    marketplace = json.load(f)
    new_marketplace = copy.deepcopy(marketplace)
    for plugin in new_marketplace['plugins']:
        old_version = plugin['version']
        new_version = old_version.split('.')
        new_version[-1] = str(int(new_version[-1]) + 1)
        plugin['version'] = '.'.join(new_version)
    with open(os.path.join(plugin_path, '.claude-plugin/marketplace.json'), 'w') as f:
        json.dump(new_marketplace, f, indent=2)

# change the versions in forge, tether, and lattice 
for plugin in ['ftl']:
    with open(os.path.join(plugin_path, plugin, '.claude-plugin/plugin.json'), 'r') as f:
        plugin_json = json.load(f)
        new_plugin_json = copy.deepcopy(plugin_json)
        old_version = plugin_json['version']
        new_version = old_version.split('.')
        new_version[-1] = str(int(new_version[-1]) + 1)
        new_plugin_json['version'] = '.'.join(new_version)
        with open(os.path.join(plugin_path, plugin, '.claude-plugin/plugin.json'), 'w') as f:
            json.dump(new_plugin_json, f, indent=2)

# force copy the entire ftl plugin to the ftl cache folder to ensure the new version is used next time
if ftl_plugin_cache_home.exists():
    shutil.rmtree(ftl_plugin_cache_home)

new_version = '.'.join(new_version)
new_cache_dir = os.path.join(ftl_plugin_cache_home, f'{new_version}')
os.makedirs(new_cache_dir, exist_ok=True)

shutil.copytree(os.path.join(plugin_path, 'ftl'), new_cache_dir, dirs_exist_ok=True,
                ignore=shutil.ignore_patterns('venv', '__pycache__', '*.pyc'))
    

