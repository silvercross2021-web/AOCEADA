"""Tests natifs sous Windows : met le compilateur MinGW installe par PlatformIO dans le PATH.

Utilise par [env:native] de platformio.ini (extra_scripts). Sans effet ailleurs que sous Windows.
Le programme de test est lie STATIQUEMENT : lance ensuite par `pio test`, il n'a besoin d'aucune
DLL de MinGW (libgcc, libstdc++).
"""
import os
import sys

Import("env")  # noqa: F821 (fourni par SCons / PlatformIO)

if sys.platform.startswith("win"):
    dossier = env.PioPlatform().get_package_dir("toolchain-gccmingw32")  # noqa: F821
    if dossier:
        bin_mingw = os.path.join(dossier, "bin")
        env.PrependENVPath("PATH", bin_mingw)  # noqa: F821
        env.Append(LINKFLAGS=["-static", "-static-libgcc", "-static-libstdc++"])  # noqa: F821
