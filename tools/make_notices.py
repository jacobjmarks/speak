"""Write THIRD_PARTY_NOTICES.txt for the bundled app's third-party components.

Usage: python tools/make_notices.py OUTPUT  (run by build.ps1 from the build venv, after vendor/ is fetched)
"""
import importlib.metadata as metadata
import re
import sys
from pathlib import Path

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parent.parent
RULE = "=" * 78
LICENSE_FILE = re.compile(r"licen[cs]e|copying|notice|authors", re.I)

MODELS = [
    ("NVIDIA Nemotron 3.5 ASR Streaming 0.6B", "nvidia/nemotron-3.5-asr-streaming-0.6b",
     "OpenMDW License 1.1, https://openmdw.ai/license/1-1/"),
    ("Qwen2.5 0.5B Instruct (GGUF)", "Qwen/Qwen2.5-0.5B-Instruct-GGUF", "Apache License 2.0"),
    ("Qwen3 4B Instruct 2507 (GGUF by bartowski)", "Qwen/Qwen3-4B-Instruct-2507", "Apache License 2.0"),
]


def section(title: str, *parts: str) -> str:
    return "\n".join([RULE, title, RULE, "", *[p.strip() + "\n" for p in parts if p.strip()]])


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def runtime_distributions() -> dict:
    """Installed distributions required by requirements.txt (build-only tools excluded), keyed by name."""
    found = {}

    def walk(name: str):
        dist = metadata.distribution(name)
        key = re.sub(r"[-_.]+", "-", dist.metadata["Name"]).lower()
        if key in found:
            return
        found[key] = dist
        for spec in dist.requires or []:
            req = Requirement(spec)
            if req.marker and not req.marker.evaluate({"extra": ""}):
                continue
            try:
                walk(req.name)
            except metadata.PackageNotFoundError:
                pass

    for line in (ROOT / "requirements.txt").read_text().splitlines():
        name = re.split(r"[<>=!~;\s\[]", line.strip(), maxsplit=1)[0]
        if name and not line.startswith("#") and name.lower() != "pyinstaller":
            walk(name)
    return dict(sorted(found.items()))


def package_section(dist) -> str:
    meta = dist.metadata
    licence = meta.get("License-Expression") or (meta.get("License") or "").splitlines()[0:1]
    licence = licence if isinstance(licence, str) else (licence[0] if licence else "see below")
    texts = [f"--- {Path(str(f)).name} ---\n{read(Path(dist.locate_file(f)))}"
             for f in dist.files or [] if LICENSE_FILE.search(Path(str(f)).name) and ".dist-info" in str(f)
             and "Commercial" not in str(f)]
    home = meta.get("Home-page") or next((u.split(", ", 1)[-1] for u in meta.get_all("Project-URL") or []), "")
    return section(f"{meta['Name']} {dist.version}", f"Licence: {licence}\n{home}", *texts)


def main(output: Path):
    out = [
        "Speak third-party notices",
        "",
        "Speak contains the third-party components below, each under its own licence.",
        "The speech and tidy-up models are not",
        "included; they are downloaded on first use and are listed at the end for attribution.",
        "",
        section(f"Python {sys.version.split()[0]}", read(Path(sys.base_prefix) / "LICENSE.txt")),
        section("Qt for Python (PySide6, Shiboken6) and Qt",
                "Licence: GNU LGPL v3 (full text under 'GNU Lesser General Public License' below).\n"
                "Copyright (C) The Qt Company Ltd. and other contributors.\n"
                "Source: https://code.qt.io/cgit/pyside/pyside-setup.git and https://download.qt.io/official_releases/qt/\n"
                "Licences of components inside Qt: https://doc.qt.io/qt-6/licenses-used-in-qt.html\n"
                "Qt is loaded as separate libraries. To use a modified Qt/PySide6, rebuild Speak from its\n"
                "public source (https://github.com/jacobjmarks/speak, see docs/DEVELOPMENT.md) against your copy."),
    ]
    for key, dist in runtime_distributions().items():
        if key not in ("pyside6-essentials", "shiboken6"):
            out.append(package_section(dist))
    out.append(section("PortAudio (bundled with sounddevice)",
                       "Copyright (c) 1999-2011 Ross Bencina and Phil Burk. MIT licence.\nhttp://www.portaudio.com/"))

    pyinstaller = metadata.distribution("pyinstaller")
    copying = next((f for f in pyinstaller.files or [] if Path(str(f)).name.upper().startswith("COPYING")), None)
    out.append(section(f"PyInstaller {pyinstaller.version} bootloader",
                       "Licence: GPL v2 or later with the bootloader exception, which allows it in any program.",
                       read(Path(pyinstaller.locate_file(copying))) if copying else ""))

    nemo = ROOT / "vendor" / "nemo-speech" / "share" / "licenses" / "nemo-speech"
    out.append(section("NeMo-Speech.cpp (speech recognition runtime)",
                       "https://github.com/NVIDIA/NeMo-Speech.cpp",
                       *[f"--- {p.relative_to(nemo).as_posix()} ---\n{read(p)}"
                         for p in sorted(nemo.rglob("*")) if p.is_file()]))

    llama = ROOT / "vendor" / "llama-cpp"
    out.append(section("llama.cpp (tidy-up runtime)", "https://github.com/ggml-org/llama.cpp",
                       read(nemo / "third_party" / "llama.cpp" / "LICENSE"),
                       *[f"--- {p.name} ---\n{read(p)}" for p in sorted(llama.glob("LICENSE*"))]))

    out.append(section("Models (downloaded on first use, not included in Speak.exe)",
                       "\n".join(f"{name}\n  https://huggingface.co/{repo}\n  Licence: {licence}"
                                 for name, repo, licence in MODELS)))
    out.append(section("GNU Lesser General Public License v3", read(ROOT / "licenses" / "LGPL-3.0.txt")))
    out.append(section("GNU General Public License v3", read(ROOT / "licenses" / "GPL-3.0.txt")))

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(out), encoding="utf-8", newline="\r\n")
    print(f"Wrote {output} ({output.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
