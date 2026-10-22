"""Checks GitHub for a newer release and, on Windows builds, installs it (issue #3).

Releases are tagged v<semver> (e.g. v1.0.0, v1.0.0-rc.1) by the manual Release workflow, which also writes VERSION
to speak/_build.py. Builds without a version (source runs, CI artifacts) never update. Stable builds only move to
stable releases unless the user opts in to pre-releases; pre-release builds also move to newer pre-releases
(alpha.1 -> rc.1 -> 1.0.0). Each OS only considers releases that carry its own package (`asset_name`); a release
without one is not an update for that OS. Only the public GitHub API is contacted.

Install: the new exe downloads beside the running one as "<exe>.new" (sha256 checked against GitHub's
asset digest); `install` renames the running exe to ".old" (Windows allows renaming a running exe) and moves
the new one into place. The ".old" file is deleted on the next start.
"""
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .platform_utils import IS_MAC, IS_WINDOWS

API = "https://api.github.com/repos/jacobjmarks/speak/releases?per_page=30"
RELEASES_PAGE = "https://github.com/jacobjmarks/speak/releases"


def asset_name() -> Optional[str]:
    """File name of this OS's package in a release, or None where no package is published."""
    if IS_WINDOWS:
        return "Speak.exe"
    if IS_MAC:
        return "Speak-macos-arm64.zip" if platform.machine() == "arm64" else "Speak-macos-x64.zip"
    return None

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


SEMVER = re.compile(r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
                    r"(?:-((?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?"
                    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?")


def parse(tag: str) -> Optional[tuple]:
    """Sortable semver precedence key, or None. 1.0.0-alpha.1 < 1.0.0-rc.1 < 1.0.0; build metadata is ignored."""
    match = SEMVER.fullmatch(tag or "")
    if not match:
        return None
    major, minor, patch, pre = match.groups()
    if pre is None:
        return int(major), int(minor), int(patch), (1,)
    ids = tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in pre.split("."))
    return int(major), int(minor), int(patch), (0, ids)


def is_prerelease(key: tuple) -> bool:
    return key[3][0] == 0


def version() -> str:
    return VERSION or "Development"


def _get(url: str, timeout: float = 10):
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "Speak"})
    return urllib.request.urlopen(request, timeout=timeout)


def pick(releases: list, current: tuple, allow_prerelease: bool = False,
         asset_file: Optional[str] = None) -> Optional[Release]:
    """Newest release newer than `current` that has this OS's package.

    Pre-releases only if `allow_prerelease` or `current` is one.
    """
    if not asset_file:
        return None
    best, found = current, None
    allow_pre = allow_prerelease or is_prerelease(current)
    for release in releases:
        tag = release.get("tag_name", "")
        number = parse(tag)
        if not number or release.get("draft") or number <= best:
            continue
        if (is_prerelease(number) or release.get("prerelease")) and not allow_pre:
            continue
        asset = next((a for a in release.get("assets", []) if a.get("name") == asset_file), None)
        if not asset:
            continue
        best = number
        found = Release(tag.removeprefix("v"), release.get("html_url") or RELEASES_PAGE,
                        asset.get("browser_download_url", ""), asset.get("digest") or "")
    return found


def newer_release(allow_prerelease: bool = False) -> Optional[Release]:
    """A newer release for this OS, or None (up to date, unversioned build, no package for this OS, or offline)."""
    current = parse(VERSION)
    if not current:
        return None
    try:
        with _get(API) as response:
            return pick(json.load(response), current, allow_prerelease, asset_name())
    except Exception:
        return None


def exe_path() -> Optional[Path]:
    return Path(sys.executable) if getattr(sys, "frozen", False) else None


def can_install(release: Release) -> bool:
    exe = exe_path()
    return bool(IS_WINDOWS and exe and release.asset_url and os.access(exe.parent, os.W_OK))


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