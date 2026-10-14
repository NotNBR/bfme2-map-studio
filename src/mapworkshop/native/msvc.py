"""Build the DLLs the launcher loads into the game, with Visual C++ .NET 2003
(MSVC 7.1: 32-bit, linked against msvcr71.dll, which the game ships).

    python -m mapworkshop.native.msvc      rebuild every DLL below

The built DLLs are committed, so only a change to their source needs the
compiler: setting `msvc71`, default openbfme2-untouched's reference
toolchain next to this checkout.
"""
import os
import shutil
import subprocess
from pathlib import Path

from mapworkshop.config import ROOT, setting

NATIVE = Path(__file__).parent
DLLS = {'capture': NATIVE/'capture'/'capture.cpp',     # screenshots (native.capture)
        'loading': NATIVE/'loading'/'loading.cpp'}     # faster map loading (native.runtime)
TOOLCHAIN = ROOT.parent/'openbfme2/openbfme2-untouched/reference/open-bfme-1/inputs/toolchains/vs2003' \
    / 'Program Files/Microsoft Visual Studio .NET 2003'


def dll(name):
    """The committed DLL built from DLLS[name]."""
    return DLLS[name].with_suffix('.dll')


def build(name):
    """Compile DLLS[name] next to its source; returns the DLL."""
    root = Path(setting('msvc71') or TOOLCHAIN)
    vc = root/'Vc7'
    if not (vc/'bin/cl.exe').is_file():
        raise RuntimeError(f'No Visual C++ .NET 2003 in {root}; set its folder with `mw config msvc71 <folder>`')
    # The compiler's own msvcr71.dll and msvcp71.dll sit two folders up.
    env = dict(os.environ, PATH=os.pathsep.join(map(str, [vc/'bin', root/'Common7/IDE', root.parents[1]]))
               + os.pathsep + os.environ['PATH'],
               INCLUDE=os.pathsep.join(map(str, [vc/'include', vc/'PlatformSDK/Include'])),
               LIB=os.pathsep.join(map(str, [vc/'lib', vc/'PlatformSDK/Lib'])))
    work = ROOT/'local/cache/msvc'/name
    work.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(vc/'bin/cl.exe'), '/nologo', '/O2', '/MD', '/LD', str(DLLS[name]),
                    '/Fe' + str(work/f'{name}.dll'), '/Fo' + str(work/f'{name}.obj'),
                    '/link', '/MACHINE:X86', 'kernel32.lib', 'user32.lib'], env=env, cwd=work, check=True)
    shutil.copy2(work/f'{name}.dll', dll(name))
    return dll(name)


if __name__ == '__main__':
    for name in DLLS:
        print(build(name))
