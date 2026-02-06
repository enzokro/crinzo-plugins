"""Canonical path resolution for helix state directory."""
import os
from pathlib import Path


def get_helix_dir() -> Path:
    """Get .helix directory: HELIX_PROJECT_DIR env -> ancestor search -> cwd."""
    project_dir = os.environ.get("HELIX_PROJECT_DIR")
    if project_dir:
        helix_dir = Path(project_dir) / ".helix"
        helix_dir.mkdir(exist_ok=True)
        return helix_dir

    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        helix_dir = parent / ".helix"
        if helix_dir.exists() and helix_dir.is_dir():
            return helix_dir

    helix_dir = cwd / ".helix"
    helix_dir.mkdir(exist_ok=True)
    return helix_dir
