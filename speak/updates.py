"""Checks GitHub for a newer release and, on Windows builds, installs it (issue #3).

Releases are tagged vX.Y.Z by the manual Release workflow, which also writes VERSION to speak/_build.py.
Builds without a version (source runs, CI artifacts) never update. Only the public GitHub API is contacted.

Install: the new exe downloads beside the running one as "<exe>.new" (sha256 checked against GitHub's
asset digest); `install` renames the running exe to ".old" (Windows allows renaming a running exe) and moves
the new one into place. The ".old" file is deleted on the next start.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

API = "https://api.github.com/repos/jacobjmarks/speak/releases?per_page=30"
RELEASES_PAGE = "https://github.com/jacobjmarks/speak/releases"
ASSET = "Speak.exe"

try:
    from ._build import VERSION
except ImportError:
    VERSION = None


@dataclass
class Release:
    version: str
    page: str
    asset_url: str = ""
    digest: str = ""  # "sha256:<hex>" or ""


def parse(tag: str) -> Optional[tuple]:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", tag or "")
    return tuple(int(n) for n in match.groups()) if match else None


def version() -> str:
    return VERSION or "Development"


def _get(url: str, timeout: float = 10):
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "Speak"})
    return urllib.request.urlopen(request, timeout=timeout)


def pick(releases: list, current: tuple) -> Optional[Release]:
    """Newest stable release newer than `current`."""
    best, found = current, None
    for release in releases:
        number = parse(release.get("tag_name", ""))
        if not number or release.get("draft") or release.get("prerelease") or number <= best:
            continue
        asset = next((a for a in release.get("assets", []) if a.get("name") == ASSET), {})
        best = number
        found = Release(".".join(map(str, number)), release.get("html_url") or RELEASES_PAGE,
                        asset.get("browser_download_url", ""), asset.get("digest") or "")
    return found


def newer_release() -> Optional[Release]:
    """A newer release, or None (up to date, unversioned build, or offline)."""
    current = parse(VERSION)
    if not current:
        return None
    try:
        with _get(API) as response:
            return pick(json.load(response), current)
    except Exception:
        return None


def exe_path() -> Optional[Path]:
    return Path(sys.executable) if getattr(sys, "frozen", False) else None


def can_install(release: Release) -> bool:
    exe = exe_path()
    return bool(sys.platform == "win32" and exe and release.asset_url and os.access(exe.parent, os.W_OK))


def download(release: Release, progress: Callable[[int], None] = lambda percent: None) -> Path:
    target = exe_path().with_name(exe_path().name + ".new")
    partial = target.with_name(target.name + ".part")
    digest = hashlib.sha256()
    with _get(release.asset_url, timeout=30) as response, open(partial, "wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while chunk := response.read(1 << 20):
            out.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            if total:
                progress(done * 100 // total)
    expected = release.digest.removeprefix("sha256:")
    if expected and digest.hexdigest() != expected.lower():
        partial.unlink(missing_ok=True)
        raise ValueError("Downloaded update is corrupt")
    os.replace(partial, target)
    return target


def install(new: Path, exe: Path) -> None:
    """Swap `new` into place of `exe` (which may be running)."""
    old = exe.with_name(exe.name + ".old")
    old.unlink(missing_ok=True)
    os.replace(exe, old)
    try:
        os.replace(new, exe)
    except OSError:
        os.replace(old, exe)
        raise


def restart(exe: Path) -> None:
    env = {**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"}  # new onefile process unpacks its own copy
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    # --restarted: wait for this instance's single-instance lock instead of deferring to it
    subprocess.Popen([str(exe), "--restarted"], env=env, creationflags=flags, close_fds=True)


def cleanup() -> None:
    exe = exe_path()
    if exe:
        for leftover in (exe.name + ".old", exe.name + ".new.part"):
            try:
                exe.with_name(leftover).unlink(missing_ok=True)
            except OSError:
                pass