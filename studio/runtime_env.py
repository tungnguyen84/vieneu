"""Runtime path helpers for the packaged Studio virtual environment."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List


def isolate_active_repo_venv(repo_root: Path) -> List[str]:
    """Remove base-Python site-packages when running from this repo's venv.

    The local venv contains the matched Torch/Transformers stack.  Its
    ``pyvenv.cfg`` historically enabled system packages, which allowed an
    incompatible base-Python torchvision to shadow that stack and made
    Transformers report that ``PreTrainedModel`` could not be imported.
    Standard-library paths are retained; only foreign site-packages are
    removed, and only when the active interpreter is the repo venv.
    """
    venv_dir = (repo_root / ".venv").resolve()
    venv_site = (venv_dir / "Lib" / "site-packages").resolve()
    try:
        active_prefix = Path(sys.prefix).resolve()
        active_executable = Path(sys.executable).resolve()
    except Exception:
        return []
    if active_prefix != venv_dir and venv_dir not in active_executable.parents:
        return []

    removed: List[str] = []
    for entry in list(sys.path):
        if not entry:
            continue
        try:
            resolved = Path(entry).resolve()
        except Exception:
            continue
        if resolved == venv_site:
            continue
        if resolved.name.lower() == "site-packages":
            sys.path.remove(entry)
            removed.append(entry)
    if str(venv_site) not in sys.path:
        sys.path.insert(0, str(venv_site))
    return removed
