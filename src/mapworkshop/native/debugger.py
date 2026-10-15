"""Run BFME2 1.06 under a Win32 debugger: start it, keep it away from the
owner's profile, and serve breakpoints in it.

Ported from openbfme2's tools/game_smoke.py and boot_smoke.py (GPL-3.0; see
docs/licenses/THIRD_PARTY.md), trimmed to what starting a skirmish
needs. Retail's launcher lotrbfme2.exe hands game.dat its start-up token, so
the launcher is started and the debugger follows it into game.dat. At each
process's WOW64 loader breakpoint (imports bound, no game code run yet):

- version lie: GetVersion/GetVersionExA report Windows XP SP3; without it
  retail crashes in CPUDetectClass formatting an unknown Windows version.
- appdata lie (game.dat): SHGetSpecialFolderPathW(CSIDL_APPDATA) returns the
  sandbox, so options, saves and replays stay in the runtime. The run stops
  if it cannot be installed and read back.
- focus lie (game.dat): at WndProc's WM_ACTIVATEAPP arm a deactivation reads
  as an activation, so loading never freezes when the window loses focus.

The game gets no debug heap (_NO_DEBUG_HEAP=1): a process started under a
debugger otherwise allocates through Windows' checking heap, which is much
slower.

Breakpoints are `handler(game, tid, ctx)` at image RVAs. A handler returns
True to keep its breakpoint, False to drop it, or a remote-call request
({'call': va, 'ecx': this, 'args': [...], 'done': f(game, [eax])}), which
runs the calls on that thread and then resumes it where it stopped.
`game.stop(reason)` ends the run at the next debug event.
"""
import ctypes
import ctypes.wintypes as wt
import os
import re
import struct
import time
from pathlib import Path

from mapworkshop.native.pe import PE

DEBUG_PROCESS = 0x1
DBG_CONTINUE, DBG_NOT_HANDLED = 0x00010002, 0x80010001
EXCEPTION, CREATE_PROCESS, EXIT_PROCESS, LOAD_DLL = 1, 3, 5, 6
INT3 = {0x80000003, 0x4000001F}                 # int3, WOW64 int3
SINGLE_STEP = {0x80000004, 0x4000001E}
LOADER_BREAKPOINT = 0x4000001F                  # the WOW64 one: imports are bound by then
QUIET = {0x406D1388, 0xE06D7363, 0x40010006}    # thread naming, C++ throw, OutputDebugString

# Retail game.dat 1.06 addresses (RVAs), from Open-BFME-2.
THE_GAME_LOGIC = 0x9FE78C                       # GameLogic*: +0x40 logic frame, +0x110 game mode
FRAME_OFF, MODE_OFF = 0x40, 0x110
SKIRMISH = 2                                    # the game mode of a skirmish
DEBUG_EXITS = (0x3AAA3, 0x3B0DC)                # `push 1; call exit` after an assertion / crash report
GAME_ENGINE_UPDATE = 0x225DA9                   # GameEngine::update, once per engine frame, main thread
LOAD_LIBRARY_SLOT = 0x7BA1F4                    # game.dat's import slot of LoadLibraryA

CSIDL_APPDATA, CSIDL_MYPICTURES = 0x1A, 0x27
# WndProc's WM_ACTIVATEAPP arm (retail 0x19A5): `cmp ebx, 1Ch; jne default`,
# then `cmp dword [ebp+10h], 0` (wParam); found by its bytes.
FOCUS_ARM = re.compile(rb'\x83\xFB\x1C\x0F\x85....(\x83\x7D\x10\x00)\x0F\x95\xC0\x3A\x05', re.DOTALL)


class STARTUPINFO(ctypes.Structure):
    _fields_ = [('cb', wt.DWORD), ('r', wt.LPWSTR), ('d', wt.LPWSTR), ('t', wt.LPWSTR)] + \
               [(n, wt.DWORD) for n in ('x', 'y', 'w', 'h', 'cx', 'cy', 'fill', 'flags')] + \
               [('show', wt.WORD), ('cb2', wt.WORD), ('r2', ctypes.c_void_p),
                ('hin', wt.HANDLE), ('hout', wt.HANDLE), ('herr', wt.HANDLE)]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [('hProcess', wt.HANDLE), ('hThread', wt.HANDLE), ('pid', wt.DWORD), ('tid', wt.DWORD)]


class WOW64_CONTEXT(ctypes.Structure):
    _fields_ = [('flags', wt.DWORD), ('dr', wt.DWORD * 6), ('fpu', ctypes.c_byte * 112), ('seg', wt.DWORD * 4),
                ('edi', wt.DWORD), ('esi', wt.DWORD), ('ebx', wt.DWORD), ('edx', wt.DWORD), ('ecx', wt.DWORD),
                ('eax', wt.DWORD), ('ebp', wt.DWORD), ('eip', wt.DWORD), ('cs', wt.DWORD), ('eflags', wt.DWORD),
                ('esp', wt.DWORD), ('ss', wt.DWORD), ('ext', ctypes.c_byte * 512)]


CONTEXT_CONTROL_INTEGER, CONTEXT_ALL = 0x10003, 0x1003F


def kernel32():
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.WaitForDebugEvent.argtypes = [ctypes.c_void_p, wt.DWORD]
    k.ContinueDebugEvent.argtypes = [wt.DWORD, wt.DWORD, wt.DWORD]
    k.CloseHandle.argtypes = [wt.HANDLE]
    k.TerminateProcess.argtypes = [wt.HANDLE, wt.UINT]
    k.CreateProcessW.argtypes = [wt.LPCWSTR, wt.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, wt.BOOL, wt.DWORD,
                                 ctypes.c_void_p, wt.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p]
    k.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
    k.GetFinalPathNameByHandleW.argtypes = [wt.HANDLE, wt.LPWSTR, wt.DWORD, wt.DWORD]
    k.OpenThread.restype = wt.HANDLE
    k.OpenProcess.restype = wt.HANDLE
    k.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                    ctypes.POINTER(ctypes.c_size_t)]
    k.WriteProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    k.VirtualProtectEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD, ctypes.POINTER(wt.DWORD)]
    k.FlushInstructionCache.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t]
    k.VirtualAllocEx.restype = ctypes.c_void_p
    k.VirtualAllocEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD, wt.DWORD]
    k.Wow64GetThreadContext.argtypes = k.Wow64SetThreadContext.argtypes = [wt.HANDLE, ctypes.c_void_p]
    return k


def running_games():
    """[(pid, image path)] of running game.dat processes, of any install."""
    k = kernel32()
    pids, got = (wt.DWORD * 4096)(), wt.DWORD()
    ctypes.WinDLL('psapi').EnumProcesses(pids, ctypes.sizeof(pids), ctypes.byref(got))
    out = []
    for pid in pids[:got.value // 4]:
        h = k.OpenProcess(0x1000, False, pid)            # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            continue
        buf, n, code = ctypes.create_unicode_buffer(1024), wt.DWORD(1024), wt.DWORD()
        # An ended game stays listed while handles to it are open: only running ones count.
        if k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) and buf.value.lower().endswith('\\game.dat') \
                and k.GetExitCodeProcess(h, ctypes.byref(code)) and code.value == 259:    # STILL_ACTIVE
            out.append((pid, buf.value))
        k.CloseHandle(h)
    return out


def hidden_desktop():
    """(handle, 'station\\desktop') of a new desktop in this session's window
    station that is never switched to: a game started on it is invisible and
    never takes your focus. Direct3D 9 does not render on a desktop that is
    not the active one (its device stays lost), so headless runs use DXVK's
    d3d9.dll (runtime.HEADLESS_GAME), which renders through Vulkan."""
    u = ctypes.WinDLL('user32', use_last_error=True)
    u.CreateDesktopW.restype = u.GetProcessWindowStation.restype = wt.HANDLE
    u.CreateDesktopW.argtypes = [wt.LPCWSTR, wt.LPCWSTR, ctypes.c_void_p, wt.DWORD, wt.DWORD, ctypes.c_void_p]
    u.GetUserObjectInformationW.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD)]
    station = ctypes.create_unicode_buffer(256)
    u.GetUserObjectInformationW(u.GetProcessWindowStation(), 2, station, ctypes.sizeof(station), None)  # UOI_NAME
    name = f'mapworkshop-{os.getpid()}'
    handle = u.CreateDesktopW(name, None, None, 0, 0x10000000, None)           # GENERIC_ALL
    if not handle:
        raise RuntimeError(f'Cannot create a hidden desktop (Windows error {ctypes.get_last_error()})')
    return handle, (station.value or 'WinSta0') + '\\' + name


def combine(handlers):
    """One breakpoint handler that runs several: each keeps running while it
    returns True (or a remote call with 'keep'); their remote calls run as
    one stub, each 'done' getting its own calls' results."""
    if len(handlers) == 1:
        return handlers[0]
    live = list(handlers)

    def handler(game, tid, ctx):
        kept, requests = [], []
        for each in list(live):
            result = each(game, tid, ctx)
            if isinstance(result, dict):
                requests.append(result)
                if result.get('keep'):
                    kept.append(each)
            elif result:
                kept.append(each)
        live[:] = kept
        if not requests:
            return bool(live)
        parts = [request.get('calls') or [request] for request in requests]

        def done(game, results):
            at = 0
            for request, part in zip(requests, parts):
                if request.get('done'):
                    request['done'](game, results[at:at + len(part)])
                at += len(part)
        return {'calls': [call for part in parts for call in part], 'keep': bool(live), 'done': done}
    return handler


def describe(result):
    """A run's end in a few words: how it stopped, and where it faulted."""
    words = [str(result.get('stopped'))]
    if result.get('exit_code') is not None:
        words.append(f'exit code {result["exit_code"]:#x}')
    if result.get('fault'):
        words.append(f'first fault at {result["fault"]}')
    if result.get('debug_exit'):
        words.append(f'game report: {result["debug_exit"]["report"][:200]}')
    return ', '.join(words)


def call_stub(calls, results):
    """x86 for a run of thiscalls: each pushes its args (right to left),
    `mov ecx, this; mov eax, fn; call eax`, stores eax at results + 4*i;
    then int3, where the debugger restores the thread."""
    code = b''
    for i, c in enumerate(calls):
        for arg in reversed(c.get('args', [])):
            code += b'\x68' + struct.pack('<I', arg & 0xFFFFFFFF)
        code += b'\xB9' + struct.pack('<I', c.get('ecx', 0)) + b'\xB8' + struct.pack('<I', c['call']) + b'\xFF\xD0'
        code += b'\xA3' + struct.pack('<I', results + 4*i)
    return code + b'\xCC'


def appdata_stub(mem, original, appdata):
    """SHGetSpecialFolderPathW's replacement, written at `mem`: CSIDL_APPDATA and
    CSIDL_MYPICTURES (the low byte of csidl, so the CREATE flag is ignored)
    copy `appdata` into pszPath and return TRUE; other folders jump to the
    real function, kept at mem+0x80."""
    path = (str(appdata).rstrip('\\') + '\0').encode('utf-16-le')
    if len(path) > 2*260:
        raise RuntimeError(f'sandbox appdata path longer than MAX_PATH: {appdata}')
    code = (bytes.fromhex('8B44240C 25FF000000')                       # mov eax, [esp+0Ch] (csidl); and eax, 0FFh
            + b'\x83\xF8' + bytes([CSIDL_APPDATA]) + b'\x74\x0B'        # cmp eax, 1Ah; je redirect
            + b'\x83\xF8' + bytes([CSIDL_MYPICTURES]) + b'\x74\x06'     # cmp eax, 27h; je redirect
            + b'\xFF\x25' + struct.pack('<I', mem + 0x80)               # jmp [original]
            + bytes.fromhex('56 57 8B7C2410 BE') + struct.pack('<I', mem + 0x100)   # edi = pszPath; esi = path
            + b'\xB9' + struct.pack('<I', len(path))                    # ecx = bytes
            + bytes.fromhex('F3A4 5F 5E B801000000 C21000'))            # rep movsb; return TRUE (stdcall, 16)
    return code.ljust(0x80, b'\xCC') + struct.pack('<I', original).ljust(0x80, b'\0') + path


def version_stubs(mem):
    """GetVersion and GetVersionExA reporting Windows XP SP3 (5.1.2600), at mem
    and mem+0x40."""
    info = struct.pack('<IIIII', 156, 5, 1, 2600, 2) + b'Service Pack 3'.ljust(128, bytes(1)) \
        + struct.pack('<HHHBB', 3, 0, 0x100, 1, 0)
    get_version = bytes.fromhex('B8 05 01 28 0A C3')                      # mov eax, 0x0A280105; ret
    get_version_ex = (bytes.fromhex('56 57 8B7C240C 8B0F 81F99C000000 7605 B99C000000 83E904 83C704 BE')
                      + struct.pack('<I', mem + 0x104)                     # esi = template + 4
                      + bytes.fromhex('F3A4 5F 5E B801000000 C20400'))     # rep movsb; return TRUE
    return get_version.ljust(0x40, b'\xCC') + get_version_ex.ljust(0xC0, b'\xCC') + info


class Game:
    """One debugged run of the game in `game_dir` with command-line `args`,
    its profile under `appdata`."""

    def __init__(self, game_dir, args, appdata):
        self.game_dir, self.args, self.appdata = Path(game_dir), args, Path(appdata)
        self.k = kernel32()
        self.handlers = {}            # rva -> [handlers], armed at the loader breakpoint
        self.injections = []          # (DLL path, done) for inject()
        self.bps = {}                 # va -> (original byte, handler)
        self.stepping = {}            # tid -> va to re-arm after its single step
        self.calls = {}               # stub int3 va -> (saved context, breakpoint va, keep, done, results, n)
        self.dlls = []                # (base, name) of the game's DLLs
        self.procs = {}               # pid -> [process handle, image path, image base, loader breakpoint seen]
        self.pid = self.hproc = self.base = None
        self.size = 0
        self.stub = None
        self.focus_va = None
        self.stopped = None
        self.headless = False         # run on a hidden desktop of its own (see hidden_desktop)
        self.t0 = None
        self.res = {'first_chance': [], 'lies': {}}

    # memory -----------------------------------------------------------------
    def read(self, va, n):
        buf, got = ctypes.create_string_buffer(n), ctypes.c_size_t()
        if not self.k.ReadProcessMemory(self.hproc, va, buf, n, ctypes.byref(got)):
            return None
        return buf.raw[:got.value]

    def u32(self, va):
        b = self.read(va, 4)
        return struct.unpack('<I', b)[0] if b and len(b) == 4 else None

    def write(self, va, data, code=False):
        old = wt.DWORD()
        self.k.VirtualProtectEx(self.hproc, va, len(data), 0x40, ctypes.byref(old))
        ok = self.k.WriteProcessMemory(self.hproc, va, data, len(data), None)
        self.k.VirtualProtectEx(self.hproc, va, len(data), old.value, ctypes.byref(old))
        if code:
            self.k.FlushInstructionCache(self.hproc, va, len(data))
        return bool(ok)

    def alloc(self, size):
        """RWX memory in the game, below 4 GiB so its stubs can address it."""
        mem = self.k.VirtualAllocEx(self.hproc, None, size, 0x3000, 0x40)
        if not mem or mem + size > 1 << 32:
            raise RuntimeError('cannot allocate memory in the game')
        return mem

    def logic(self):
        """(logic frame, game mode), or (None, None) before GameLogic exists."""
        gl = self.u32(self.base + THE_GAME_LOGIC) if self.base else None
        if not gl:
            return None, None
        return self.u32(gl + FRAME_OFF), self.u32(gl + MODE_OFF)

    def seconds(self):
        return round(time.time() - self.t0, 1)

    def stop(self, reason):
        self.stopped = self.stopped or reason

    # breakpoints ------------------------------------------------------------
    def on(self, rva, handler):
        """Break at image RVA `rva` from the start (armed at the loader
        breakpoint). Several handlers at one address all run (combine)."""
        self.handlers.setdefault(rva, []).append(handler)

    def arm(self, rva, handler):
        """Break at image RVA `rva` from now on (from a tick or a handler)."""
        self._arm(self.base + rva, handler)

    def _arm(self, va, handler):
        if va in self.bps:                       # already armed: keep its original byte, run both
            orig, existing = self.bps[va]
            self.bps[va] = (orig, combine([existing, handler]))
            return
        orig = self.read(va, 1)
        if orig and self.write(va, b'\xCC', code=True):
            self.bps[va] = (orig, handler)

    def inject(self, path, done=None):
        """Load a DLL into the game, on its main thread at the first engine
        frame (LoadLibraryA from a remote call); then done(game, {export:
        address}). Whether each DLL loaded is in res['injected']."""
        if not self.injections:
            self.on(GAME_ENGINE_UPDATE, Game._inject)
        self.injections.append((Path(path), done))

    def _inject(self, tid, ctx):
        calls = []
        for path, _ in self.injections:
            name = str(path.resolve()).encode('mbcs') + b'\0'
            memory = self.alloc(len(name))
            self.write(memory, name)
            calls.append({'call': self.u32(self.base + LOAD_LIBRARY_SLOT), 'args': [memory]})

        def loaded(game, modules):
            for (path, done), module in zip(game.injections, modules):
                game.res.setdefault('injected', {})[path.name] = bool(module)
                if module and done:
                    done(game, {name: module + rva for name, rva in PE(path).exports().items()})
        return {'calls': calls, 'done': loaded}

    def _context(self, tid, flags=CONTEXT_CONTROL_INTEGER):
        h = self.k.OpenThread(0x1FFFFF, False, tid)
        ctx = WOW64_CONTEXT()
        ctx.flags = flags
        if not h or not self.k.Wow64GetThreadContext(h, ctypes.byref(ctx)):
            if h:
                self.k.CloseHandle(h)
            return None, None
        return h, ctx

    def _hit(self, tid, va):
        orig, handler = self.bps[va]
        h, ctx = self._context(tid)
        if ctx is None:
            return
        eip = ctx.eip
        keep = handler(self, tid, ctx)
        self.write(va, orig, code=True)
        if isinstance(keep, dict):
            self._call(h, tid, va, keep)
            return
        if ctx.eip == eip:                       # resume at the breakpoint (unless the handler moved eip)
            ctx.eip = va
        if keep:
            ctx.eflags |= 0x100                  # step over the original instruction, then re-arm
            self.stepping[tid] = va
        else:
            del self.bps[va]
        self.k.Wow64SetThreadContext(h, ctypes.byref(ctx))
        self.k.CloseHandle(h)

    def _call(self, h, tid, va, req):
        """Run req['calls'] (or req itself as one call) on this thread from the
        breakpoint at `va`; the full context is restored at the stub's int3,
        where req['done'](game, [eax of each call]) runs."""
        full = WOW64_CONTEXT()
        full.flags = CONTEXT_ALL
        self.k.Wow64GetThreadContext(h, ctypes.byref(full))
        if self.stub is None:
            self.stub = self.alloc(0x4000)
        calls = req.get('calls') or [req]
        results = self.stub + 0x3000
        code = call_stub(calls, results)
        if len(code) > 0x3000:
            raise RuntimeError(f'remote-call stub of {len(code)} bytes does not fit')
        self.write(self.stub, code, code=True)
        self.calls[self.stub + len(code) - 1] = (full, va, req.get('keep', False), req.get('done'), results, len(calls))
        ctx = WOW64_CONTEXT()
        ctx.flags = CONTEXT_CONTROL_INTEGER
        self.k.Wow64GetThreadContext(h, ctypes.byref(ctx))
        ctx.eip, ctx.esp = self.stub, (ctx.esp - 0x200) & ~0xF
        self.k.Wow64SetThreadContext(h, ctypes.byref(ctx))
        self.k.CloseHandle(h)

    def _returned(self, tid, at):
        full, va, keep, done, results, n = self.calls.pop(at)
        h, ctx = self._context(tid)
        if done and ctx is not None:
            done(self, list(struct.unpack(f'<{n}I', self.read(results, 4*n))))
        full.eip = va
        if keep and va in self.bps:
            full.eflags |= 0x100
            self.stepping[tid] = va
        elif va in self.bps:
            del self.bps[va]
        self.k.Wow64SetThreadContext(h, ctypes.byref(full))
        self.k.CloseHandle(h)

    # the lies -----------------------------------------------------------------
    def _patch_imports(self, hproc, base, slots):
        """Point import slots {va: new pointer} of a process at our stubs."""
        for va, pointer in slots.items():
            old = wt.DWORD()
            self.k.VirtualProtectEx(hproc, va, 4, 0x04, ctypes.byref(old))
            self.k.WriteProcessMemory(hproc, va, struct.pack('<I', pointer), 4, None)
            self.k.VirtualProtectEx(hproc, va, 4, old.value, ctypes.byref(old))

    def _version_lie(self, hproc, base, pe):
        imports = pe.imports()
        mem = self.k.VirtualAllocEx(hproc, None, 0x1000, 0x3000, 0x40)
        blob = version_stubs(mem)
        self.k.WriteProcessMemory(hproc, mem, blob, len(blob), None)
        slots = {}
        for name, at in (('GetVersion', 0), ('GetVersionExA', 0x40)):
            slot = imports.get(('kernel32.dll', name))
            if slot is not None:
                slots[base + slot] = mem + at
        self._patch_imports(hproc, base, slots)
        return len(slots)

    def _appdata_lie(self, pe):
        slot = pe.imports().get(('shell32.dll', 'SHGetSpecialFolderPathW'))
        if slot is None:
            raise RuntimeError('game.dat imports no SHGetSpecialFolderPathW')
        slot += self.base
        original = self.u32(slot)
        mem = self.alloc(0x1000)
        blob = appdata_stub(mem, original, self.appdata.resolve())
        self.write(mem, blob)
        self._patch_imports(self.hproc, self.base, {slot: mem})
        if self.read(mem, len(blob)) != blob or self.u32(slot) != mem:
            raise RuntimeError(f'the profile redirect did not stick (slot {slot:#x})')

    def _focus_lie(self, tid):
        """A deactivation (wParam 0) at the WM_ACTIVATEAPP arm becomes an
        activation; the original instruction then runs under the trap flag."""
        h, ctx = self._context(tid, 0x10001)
        if ctx is None:
            return
        slot = ctx.ebp + 0x10
        if self.read(slot, 4) == bytes(4):
            self.write(slot, struct.pack('<I', 1))
        self.write(self.focus_va, self.bps[self.focus_va][0], code=True)
        ctx.eip, ctx.eflags = self.focus_va, ctx.eflags | 0x100
        self.k.Wow64SetThreadContext(h, ctypes.byref(ctx))
        self.k.CloseHandle(h)
        self.stepping[tid] = self.focus_va

    def _loaded(self, pe):
        """game.dat's loader breakpoint: the lies, then the breakpoints."""
        self._appdata_lie(pe)
        self.res['lies']['version'] = self._version_lie(self.hproc, self.base, pe)
        hits = [rva + m.start(1) for rva, data in pe.code() for m in FOCUS_ARM.finditer(data)]
        if len(hits) == 1:
            self.focus_va = self.base + hits[0]
            self._arm(self.focus_va, None)
        self.res['lies']['focus'] = bool(self.focus_va)
        for rva in DEBUG_EXITS:
            self._arm(self.base + rva, Game._debug_exit)
        for rva, handlers in self.handlers.items():
            self._arm(self.base + rva, combine(handlers))

    def _debug_exit(self, tid, ctx):
        """The game's own assertion or crash report is about to exit(1): keep
        its text and the return addresses on the stack."""
        blob = self.read(ctx.ebx, 0xA000) or b''
        texts = sorted({m.group().decode('latin1') for m in re.finditer(rb'[\x20-\x7E\r\n\t]{12,}', blob)},
                       key=len, reverse=True)[:8]
        report = self.read(self.u32(ctx.ebp - 8) or 0, 0x800) or b''
        self.res['debug_exit'] = {'at': hex(ctx.eip - self.base), 'texts': texts,
                                  'report': report.split(b'\0')[0].decode('latin1'),
                                  'stack': self.stack(tid)}
        return False

    def where(self, va):
        """'image+rva' or 'dll+offset' of an address."""
        if self.base and self.base <= va < self.base + self.size:
            return f'image+{va - self.base:#x}'
        below = [(b, n) for b, n in self.dlls if b <= va]
        if below:
            b, n = max(below)
            return f'{n}+{va - b:#x}'
        return hex(va)

    def stack(self, tid, n=24):
        """Return-address candidates in the image on tid's stack."""
        h, ctx = self._context(tid)
        if ctx is None:
            return []
        self.k.CloseHandle(h)
        data = self.read(ctx.esp, 0x1000) or b''
        words = struct.unpack(f'<{len(data) // 4}I', data[:len(data) // 4 * 4])
        return [self.where(w) for w in words if self.base <= w < self.base + self.size][:n]

    def terminate(self, wait=10.0):
        """End the game and its launcher, and serve their last debug events
        until they have exited, so the next run finds no game running."""
        for h, *_ in self.procs.values():
            self.k.TerminateProcess(h, 1)
        alive, ev, end = set(self.procs), ctypes.create_string_buffer(256), time.time() + wait
        while alive and time.time() < end:
            if not self.k.WaitForDebugEvent(ev, 100):
                continue
            code, pid, tid = (int.from_bytes(ev.raw[o:o + 4], 'little') for o in (0, 4, 8))
            if code == EXIT_PROCESS:
                alive.discard(pid)
            elif code in (CREATE_PROCESS, LOAD_DLL) and int.from_bytes(ev.raw[16:24], 'little'):
                self.k.CloseHandle(int.from_bytes(ev.raw[16:24], 'little'))
            self.k.ContinueDebugEvent(pid, tid, DBG_CONTINUE)

    # run --------------------------------------------------------------------
    def run(self, timeout, tick=None, tick_every=0.25):
        """Debug until the game exits or crashes, `stop()` is called, `tick(game)`
        returns a reason to stop, or `timeout` seconds pass. Returns self.res,
        with 'stopped' saying why. The game is ended when this returns."""
        k = self.k
        si, pi = STARTUPINFO(), PROCESS_INFORMATION()
        si.cb = ctypes.sizeof(si)
        desktop = hidden_desktop() if self.headless else None
        if desktop:
            si.d = desktop[1]
        os.environ['_NO_DEBUG_HEAP'] = '1'            # inherited by the launcher and game.dat
        cmd = ctypes.create_unicode_buffer(f'"{self.game_dir.resolve()/"lotrbfme2.exe"}" {self.args}')
        if not k.CreateProcessW(None, cmd, None, None, False, DEBUG_PROCESS, None, str(self.game_dir.resolve()),
                                ctypes.byref(si), ctypes.byref(pi)):
            raise RuntimeError(f'Starting the game failed (Windows error {ctypes.get_last_error()})')
        ev = ctypes.create_string_buffer(256)
        self.t0 = time.time()
        next_tick = self.t0 + tick_every
        res = self.res
        try:
            while not self.stopped:
                now = time.time()
                if now - self.t0 >= timeout:
                    self.stop('timeout')
                    break
                if tick and self.pid and now >= next_tick:
                    next_tick = now + tick_every
                    why = tick(self)
                    if why:
                        self.stop(why)
                        break
                if not k.WaitForDebugEvent(ev, 50):
                    continue
                code, pid, tid = (int.from_bytes(ev.raw[o:o + 4], 'little') for o in (0, 4, 8))
                status = DBG_CONTINUE
                game = pid == self.pid
                if code == CREATE_PROCESS:
                    k.CloseHandle(int.from_bytes(ev.raw[16:24], 'little'))
                    h = int.from_bytes(ev.raw[24:32], 'little')
                    buf, n = ctypes.create_unicode_buffer(1024), wt.DWORD(1024)
                    k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n))
                    base = int.from_bytes(ev.raw[40:48], 'little')
                    self.procs[pid] = [h, buf.value, base, False]
                    if Path(buf.value).name.lower() == 'game.dat':
                        self.pid, self.hproc, self.base = pid, h, base
                        res['started'] = self.seconds()
                elif code == LOAD_DLL:
                    h = int.from_bytes(ev.raw[16:24], 'little')
                    if h:
                        if game:
                            buf = ctypes.create_unicode_buffer(1024)
                            if k.GetFinalPathNameByHandleW(h, buf, 1024, 0):
                                self.dlls.append((int.from_bytes(ev.raw[24:32], 'little'), buf.value.split('\\')[-1]))
                        k.CloseHandle(h)
                elif code == EXIT_PROCESS:
                    self.procs.pop(pid, None)
                    if game:
                        res.update(exit_code=int.from_bytes(ev.raw[16:20], 'little'), seconds=self.seconds())
                        self.stop('exit')
                elif code == EXCEPTION:
                    exc = int.from_bytes(ev.raw[16:20], 'little')
                    addr = int.from_bytes(ev.raw[32:40], 'little')
                    first = int.from_bytes(ev.raw[168:172], 'little')
                    if exc == LOADER_BREAKPOINT and pid in self.procs and not self.procs[pid][3]:
                        self.procs[pid][3] = True
                        h, path, base, _ = self.procs[pid]
                        pe = PE(path)
                        if game:
                            self.size = pe.image_size
                            try:
                                self._loaded(pe)
                            except RuntimeError as error:   # killed before any game code runs
                                res['redirect_error'] = str(error)
                                self.stop('profile-redirect-failed')
                        else:                               # the launcher gets the version lie too
                            self._version_lie(h, base, pe)
                    elif game and exc in INT3 and (addr in self.calls or addr - 1 in self.calls):
                        self._returned(tid, addr if addr in self.calls else addr - 1)
                    elif game and exc in INT3 and self.focus_va in (addr, addr - 1):
                        self._focus_lie(tid)
                    elif game and exc in INT3 and (addr in self.bps or addr - 1 in self.bps):
                        self._hit(tid, addr if addr in self.bps else addr - 1)
                    elif game and exc in SINGLE_STEP and tid in self.stepping:
                        va = self.stepping.pop(tid)
                        if va in self.bps:
                            self.write(va, b'\xCC', code=True)
                    elif exc not in INT3:
                        status = DBG_NOT_HANDLED
                        if first and game and exc not in QUIET and len(res['first_chance']) < 10:
                            res['first_chance'].append([hex(exc), self.where(addr)])
                            if exc == 0xC0000005 and 'fault' not in res:
                                res.update(fault=self.where(addr), fault_stack=self.stack(tid))
                        elif not first and game:
                            res.update(crash=hex(exc), address=self.where(addr), seconds=self.seconds())
                            self.stop('crash')
                k.ContinueDebugEvent(pid, tid, status)
        finally:
            res['stopped'] = self.stopped
            self.terminate()
            if desktop:
                ctypes.WinDLL('user32').CloseDesktop(wt.HANDLE(desktop[0]))
            k.CloseHandle(pi.hThread)
            k.CloseHandle(pi.hProcess)
        return res
