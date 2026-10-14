// GPL-3.0-only. Screenshots for mapworkshop.native.capture: BFME2 1.06 loads
// this DLL (a remote LoadLibraryA from the launcher), which then
//  - places the tactical camera every frame while mwPhoto.enabled is set
//    (W3DView::updateView, RVA 0x85B36): focus on the ground at x, y and
//    the given height, through the view's own lookAt and height setters;
//  - copies the D3D9 render target at the end of a presented frame after
//    mwCapture.request is set (DX8Wrapper::End_Scene, RVA 0x122BE0) into a
//    buffer the launcher reads back, and counts rendered frames.
// Taken from bfme-workshop's strategic extension (photo mode 2 and
// captureFrame); its camera tilt, symbols and other hooks are left out.
// Build: python -m mapworkshop.native.capture build (MSVC 7.1).
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <string.h>

typedef unsigned char U8;
typedef unsigned int U32;
struct V3 { float x, y, z; };

struct Photo { U32 enabled; float x, y, height; };
struct Capture { U32 request, status, width, height, pitch, pixels, frames, format; };
extern "C" __declspec(dllexport) Photo mwPhoto = {0};
extern "C" __declspec(dllexport) Capture mwCapture = {0};
extern "C" __declspec(dllexport) U32 mwInstalled = 0;

static U8 *base;
static void *updateOriginal, *endOriginal;
static U32 capacity;

template<class T> T &field(void *p, U32 offset) { return *(T*)((U8*)p + offset); }
template<class T> T address(U32 rva) { return (T)(base + rva); }
typedef void (__fastcall *ViewFn)(void*, void*);
typedef void (__cdecl *EndFn)(bool);

static bool inMatch() {
    void *logic = field<void*>(base, 0x9FE78C);          // TheGameLogic; +0x110 game mode, 2 in a skirmish
    return logic && field<int>(logic, 0x110) == 2;
}

static void __fastcall updateHook(void *view, void *) {
    if (mwPhoto.enabled && view == field<void*>(base, 0x9FEA3C) && inMatch()) {   // TheTacticalView
        typedef float (__fastcall *GroundFn)(void*, void*, float, float, V3*);
        typedef void (__fastcall *LookAtFn)(void*, void*, const V3*);
        typedef void (__fastcall *HeightFn)(void*, void*, float);
        V3 focus = {mwPhoto.x, mwPhoto.y, 0};
        void *terrain = field<void*>(base, 0x9FEC50);
        if (terrain) focus.z = ((GroundFn)field<U32*>(terrain, 0)[6])(terrain, 0, focus.x, focus.y, 0);
        address<LookAtFn>(0x8D55D)(view, 0, &focus);
        address<HeightFn>(0x8D2B8)(view, 0, mwPhoto.height);
    }
    ((ViewFn)updateOriginal)(view, 0);
}

static void captureFrame() {
    if (!mwCapture.request) return;
    mwCapture.request = 0;
    mwCapture.status = 0x80004005;
    void *device = field<void*>(base, 0x9EDA34);          // the IDirect3DDevice9
    if (!device) return;
    U32 *vt = field<U32*>(device, 0);
    void *target = 0, *copy = 0;
    typedef HRESULT (__stdcall *GetTarget)(void*, U32, void**);
    typedef HRESULT (__stdcall *CreateSurface)(void*, U32, U32, U32, U32, void**, void*);
    typedef HRESULT (__stdcall *CopySurface)(void*, void*, void*);
    typedef HRESULT (__stdcall *DescFn)(void*, void*);
    typedef HRESULT (__stdcall *LockFn)(void*, void*, void*, U32);
    typedef HRESULT (__stdcall *SimpleFn)(void*);
    U32 desc[8] = {0};
    struct Lock { int pitch; void *bits; } locked;
    // GetRenderTarget, then GetDesc / CreateOffscreenPlainSurface (system memory) /
    // GetRenderTargetData / LockRect: X8R8G8B8 or A8R8G8B8 only.
    HRESULT result = ((GetTarget)vt[38])(device, 0, &target);
    if (SUCCEEDED(result) && target) {
        U32 *tv = field<U32*>(target, 0);
        result = ((DescFn)tv[12])(target, desc);
        mwCapture.format = desc[0];
        if (SUCCEEDED(result) && (desc[0] == 21 || desc[0] == 22) && desc[6] && desc[7] && desc[6] <= 4096 && desc[7] <= 4096) {
            result = ((CreateSurface)vt[36])(device, desc[6], desc[7], desc[0], 2, &copy, 0);
            if (SUCCEEDED(result) && copy) {
                result = ((CopySurface)vt[32])(device, target, copy);
                U32 *cv = field<U32*>(copy, 0);
                if (SUCCEEDED(result)) result = ((LockFn)cv[13])(copy, &locked, 0, 0x10);
                if (SUCCEEDED(result)) {
                    U32 size = desc[6] * desc[7] * 4;
                    if (size > capacity) {
                        if (mwCapture.pixels) VirtualFree((void*)mwCapture.pixels, 0, MEM_RELEASE);
                        mwCapture.pixels = (U32)VirtualAlloc(0, size, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
                        capacity = mwCapture.pixels ? size : 0;
                    }
                    if (mwCapture.pixels) {
                        for (U32 y = 0; y < desc[7]; y++)
                            memcpy((U8*)mwCapture.pixels + y * desc[6] * 4, (U8*)locked.bits + y * locked.pitch, desc[6] * 4);
                        mwCapture.width = desc[6]; mwCapture.height = desc[7]; mwCapture.pitch = desc[6] * 4;
                    } else result = 0x8007000E;
                    ((SimpleFn)cv[14])(copy);
                }
                ((SimpleFn)cv[2])(copy);
            }
        } else if (SUCCEEDED(result)) result = 0x80004001;
        ((SimpleFn)tv[2])(target);
    }
    mwCapture.status = result;
}

// Only frames that are presented (flip): render-to-texture passes, such as
// the water reflection at High, end scenes of their own without flipping.
static void __cdecl endHook(bool flip) {
    __try { if (flip) { mwCapture.frames++; captureFrame(); } }
    __except (EXCEPTION_EXECUTE_HANDLER) { mwCapture.status = GetExceptionCode(); }
    ((EndFn)endOriginal)(flip);
}

// Replace `length` bytes at rva (checked against `expected`) with a jump to
// `replacement`; returns a trampoline running those bytes, then the rest.
static void *hook(U32 rva, void *replacement, const U8 *expected, int length) {
    U8 *src = base + rva;
    if (memcmp(src, expected, length)) return 0;
    U8 *stub = (U8*)VirtualAlloc(0, length + 5, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!stub) return 0;
    memcpy(stub, src, length);
    stub[length] = 0xe9;
    *(U32*)(stub + length + 1) = (U32)(src + length) - (U32)(stub + length + 5);
    DWORD old;
    if (!VirtualProtect(src, length, PAGE_EXECUTE_READWRITE, &old)) return 0;
    src[0] = 0xe9;
    *(U32*)(src + 1) = (U32)replacement - (U32)(src + 5);
    for (int i = 5; i < length; i++) src[i] = 0x90;
    VirtualProtect(src, length, old, &old);
    FlushInstructionCache(GetCurrentProcess(), src, length);
    return stub;
}

static void undoHook(U32 rva, void *trampoline, int length) {
    DWORD old;
    if (trampoline && VirtualProtect(base + rva, length, PAGE_EXECUTE_READWRITE, &old)) {
        memcpy(base + rva, trampoline, length);
        VirtualProtect(base + rva, length, old, &old);
        FlushInstructionCache(GetCurrentProcess(), base + rva, length);
    }
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID) {
    if (reason != DLL_PROCESS_ATTACH) return TRUE;
    DisableThreadLibraryCalls(instance);
    base = (U8*)GetModuleHandleA(0);
    const U8 endBytes[] = {0x64, 0xa1, 0, 0, 0, 0};           // mov eax, fs:[0]
    const U8 updateBytes[] = {0x81, 0xc1, 0xb4, 0, 0, 0};     // add ecx, 0B4h
    if (base != (U8*)0x400000 || memcmp(base + 0x122BE0, endBytes, 6) || memcmp(base + 0x85B36, updateBytes, 6))
        return FALSE;
    endOriginal = hook(0x122BE0, endHook, endBytes, 6);
    updateOriginal = hook(0x85B36, updateHook, updateBytes, 6);
    if (!endOriginal || !updateOriginal) {
        undoHook(0x122BE0, endOriginal, 6);
        undoHook(0x85B36, updateOriginal, 6);
        return FALSE;
    }
    mwInstalled = 1;
    return TRUE;
}
