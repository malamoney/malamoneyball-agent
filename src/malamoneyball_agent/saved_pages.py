"""Downloaded web pages saved in the data folder, to reuse across restarts.

Each page is saved as JSON holding the page and when it was downloaded, so
a site's module can tell how old its saved copy is and read it again.
"""

import json
from datetime import datetime
from pathlib import Path

from malamoneyball_agent.conversations import data_dir


def save(folder: str, name: str, html: str, downloaded_at: datetime) -> None:
    """Save a page as data_dir()/folder/name.json; failing to is ignored."""
    path = _path(folder, name)
    saved = {"downloaded_at": downloaded_at.isoformat(), "html": html}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Written aside and then moved, so a crash never leaves half a file.
        partial = path.with_suffix(".partial")
        partial.write_text(json.dumps(saved), encoding="utf-8")
        partial.replace(path)
    except OSError:
        pass  # Not being able to save only means downloading again next time.


def load(folder: str, name: str) -> tuple[str, datetime] | None:
    """Return a saved page and when it was downloaded, if there's one."""
    # A missing, unreadable or damaged file is the same as none.
    try:
        saved = json.loads(_path(folder, name).read_text(encoding="utf-8"))
        html = saved["html"]
        downloaded_at = datetime.fromisoformat(saved["downloaded_at"])
    except OSError, ValueError, KeyError, TypeError:
        return None
    if not isinstance(html, str) or downloaded_at.tzinfo is None:
        return None
    return html, downloaded_at


def _path(folder: str, name: str) -> Path:
    return data_dir() / folder / f"{name}.json"
