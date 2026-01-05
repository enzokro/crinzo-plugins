"""Lattice library - semantic memory for tether workspaces."""

from pathlib import Path
import sys

# Ensure lib/ is importable when scripts are run directly
_lib_dir = Path(__file__).parent
if str(_lib_dir) not in sys.path:
    sys.path.insert(0, str(_lib_dir))
