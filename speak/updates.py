"""Checks GitHub for a newer release build (issue #3).

Release tags are "main-<run number>" (.github/workflows/release.yml); CI writes that number to speak/_build.py.
Running from source has no build number, so no check happens. Only the public releases API is contacted.
"""
import json
import re
import urllib.request
from typing import Optional

API = "https://api.github.com/repos/jacobjmarks/speak/releases?per_page=20"  # /latest skips pre-releases
RELEASES_PAGE = "https://github.com/jacobjmarks/speak/releases"

try:
    from ._build import BUILD
except ImportError:
    BUILD = None


def version() -> str:
    return f"Build {BUILD}" if BUILD is not None else "Development"


def newer_release() -> Optional[str]:
    """URL of a newer release, or None (up to date, running from source, or offline)."""
    if BUILD is None:
        return None
    try:
        request = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json", "User-Agent": "Speak"})
        with urllib.request.urlopen(request, timeout=10) as response:
            releases = json.load(response)
    except Exception:
        return None
    best, url = BUILD, None
    for release in releases:
        match = re.fullmatch(r"main-(\d+)", release.get("tag_name", ""))
        if match and not release.get("draft") and int(match.group(1)) > best:
            best, url = int(match.group(1)), release.get("html_url") or RELEASES_PAGE
    return url
