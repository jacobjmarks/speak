"""Overrides the pyinstaller-hooks-contrib hook, which bundles every PortAudio build.

sounddevice only loads the plain 64-bit/macOS library unless SD_ENABLE_ASIO is set, so the ASIO builds
(which contain Steinberg's GPL-3/proprietary ASIO SDK) and other architectures are left out.
On Linux the system libportaudio is used, as in the contrib hook.
"""
import ctypes.util
import pathlib
import sys

from PyInstaller.utils.hooks import get_module_file_attribute

module_dir = pathlib.Path(get_module_file_attribute("sounddevice")).parent
data_dir = module_dir / "_sounddevice_data" / "portaudio-binaries"
binaries = []
datas = []
if data_dir.is_dir():
    dest = str(data_dir.relative_to(module_dir))
    lib = data_dir / ("libportaudio.dylib" if sys.platform == "darwin" else "libportaudio64bit.dll")
    binaries = [(str(lib), dest)] if lib.is_file() else []
    datas = [(str(data_dir / "README.md"), dest)]
elif lib := ctypes.util.find_library("portaudio"):
    from PyInstaller.depend.utils import _resolveCtypesImports

    resolved = _resolveCtypesImports([pathlib.Path(lib).name])
    binaries = [(resolved[0][1], ".")] if resolved else []
