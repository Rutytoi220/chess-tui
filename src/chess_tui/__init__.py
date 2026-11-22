"""Chess.com TUI with Vimium-style move hints and extreme customizability."""

from pathlib import Path

__version__ = "0.1.0"
__all__ = ["__version__", "get_extension_dir"]


def get_extension_dir() -> Path:
    """Locate the bundled browser extension directory (works in repo or wheel install)."""
    bundled = Path(__file__).resolve().parent / "extension"
    if bundled.exists():
        return bundled
    repo_root_ext = Path(__file__).resolve().parents[2] / "extension"
    return repo_root_ext
