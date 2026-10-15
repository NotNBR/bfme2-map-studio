// GPL-3.0-only. The test game's add-on (mapworkshop.native.runtime loads it
// into BFME2 1.06 with a remote LoadLibraryA at the first engine frame):
//  - a free camera (mwCamera): the mouse wheel zooms from close up to the
//    whole map, and dragging with the middle button held tilts the view from
//    the horizon to straight down, while sideways still rotates it as in the
//    game. The game keeps the focus point, scrolling and rotation: the camera
//    W3DView::buildCameraTransform (RVA 0x8A653) builds is turned to the
//    chosen tilt and moved to the chosen distance from the same focus, before
//    setCameraTransform sets it and the terrain picks what to draw from it.
//    View::zoomIn / zoomOut (0x25EA2E / 0x25EA55, the wheel's calls once the
//    GUI has passed it on) set the distance; Win32Mouse's event entry
//    (0x41A10) sees the middle-button drag. Scrolling (W3DView::scrollBy,
//    0x8CE2E) goes as far per step as the game's would at its own distance,
//    so it keeps its pace on screen at any zoom. A middle click (resetCamera,
//    0x8D925), a scripted camera move or the screenshot camera hands the
//    camera back to the game;
//  - places the tactical camera every frame while mwPhoto.enabled is set
//    (W3DView::updateView, RVA 0x85B36): focus on the ground at x, y and
//    the given height, through the view's own lookAt and height setters;
//    with a pitch above 0 the built camera is replaced by one at that angle
//    below the horizon, facing heading (radians from north, clockwise),
//    `distance` from the focus: a cinematic view;
//  - copies the D3D9 render target at the end of a presented frame after
//    mwCapture.request is set (DX8Wrapper::End_Scene, RVA 0x122BE0) into a
//    buffer the launcher reads back, and counts rendered frames.
// The screenshot parts are taken from bfme-workshop's strategic extension
// (photo mode 2 and captureFrame), as is the camera matrix layout.
// Build: python -m mapworkshop.native.msvc ingame (MSVC 7.1).
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <math.h>
#include <string.h>

typedef unsigned char U8;
typedef unsigned int U32;
struct V3 { float x, y, z; };
struct Matrix { float m[3][4]; };     // W3D Matrix3D: columns right, up, back (the camera looks along -back), position

struct Photo { U32 enabled; float x, y, height, pitch, heading, distance; };
struct Capture { U32 request, status, width, height, pitch, pixels, frames, format; };
// enabled: the wheel and middle-button tilt drive the camera (the launcher may clear it);
// active: they have since the last reset, else the game's camera is shown unchanged.
// distance eases to target; pitch is the view's angle below the horizon, radians.
struct Camera { U32 enabled, active; float distance, target, pitch, minDistance, maxDistance; U32 builds; };
extern "C" __declspec(dllexport) Photo mwPhoto = {0};
extern "C" __declspec(dllexport) Capture mwCapture = {0};
extern "C" __declspec(dllexport) Camera mwCamera = {1, 0, 0, 0, 0, 40, 30000, 0};
extern "C" __declspec(dllexport) U32 mwInstalled = 0;

static const float ZOOM_STEP = 1.15f;              // distance factor per wheel notch
static const float TILT_PER_PIXEL = 0.005f;        // radians, as the game's rotation per pixel
static const float MIN_PITCH = 0.05f, MAX_PITCH = 1.5707963f;
static const float EASE_RATE = 14;                 // 1/s: 95% of a zoom step in about 0.2 s
static const float CLEARANCE = 20;                 // the camera stays this high above the ground

static U8 *base;
static void *updateOriginal, *endOriginal, *buildOriginal, *zoomInOriginal, *zoomOutOriginal, *resetOriginal,
            *mouseOriginal, *scrollOriginal;
static U32 capacity;
static float zoomFactor = 1, tiltDelta = 0;        // input since the last build
static float gameReach;                            // the game's camera distance at the last build
static bool wanted, middleDown;
static int lastY;
static LARGE_INTEGER lastBuild, frequency;

template<class T> T &field(void *p, U32 offset) { return *(T*)((U8*)p + offset); }
template<class T> T address(U32 rva) { return (T)(base + rva); }
typedef void (__fastcall *ViewFn)(void*, void*);
typedef void (__fastcall *BuildFn)(void*, void*, Matrix*);
typedef void (__fastcall *ResetFn)(void*, void*, int, int, float, float);
typedef void (__fastcall *MouseFn)(void*, void*, UINT, WPARAM, LPARAM, DWORD);
typedef U32 (__fastcall *ScrollFn)(void*, void*, float*);
typedef float (__fastcall *GroundFn)(void*, void*, float, float, V3*);
typedef void (__cdecl *EndFn)(bool);

static bool inMatch() {
    void *logic = field<void*>(base, 0x9FE78C);          // TheGameLogic; +0x110 game mode, 2 in a skirmish
    return logic && field<int>(logic, 0x110) == 2;
}

static void *tactical() { return field<void*>(base, 0x9FEA3C); }   // TheTacticalView

static float ground(float x, float y) {
    void *terrain = field<void*>(base, 0x9FEC50);
    return terrain ? ((GroundFn)field<U32*>(terrain, 0)[6])(terrain, 0, x, y, 0) : 0;
}

static float clamp(float v, float lo, float hi) { return v < lo ? lo : v > hi ? hi : v; }

// A scripted camera move or cinematic is under way: the flags
// W3DView::setHeightAboveGround (0x8D2B8) checks before taking the player's zoom.
static bool scripted(void *view) {
    void *client = field<void*>(base, 0x9FE77C);         // TheGameClient
    return (client && field<U8>(client, 0xC0) && field<U8>(view, 0x44)) || field<U8>(view, 0x2503)
        || field<int>(view, 0x2354) || field<U8>(view, 0x1DC) || field<U8>(view, 0x204) || field<U8>(view, 0x228)
        || field<U8>(view, 0x27D) || field<U8>(view, 0x27C);
}

static bool controls(void *view) {
    return mwCamera.enabled && !mwPhoto.enabled && view == tactical() && inMatch() && !scripted(view);
}

static void release() {
    mwCamera.active = 0;
    zoomFactor = 1; tiltDelta = 0; wanted = false;
}

// After the game built the camera: the same focus and heading, at the chosen
// tilt and distance. The game's camera looks at its focus, View +0x0C, which
// is at the ground height View +0x14 (as bfme-workshop's strategic camera).
// The screenshot camera's own view: focus on the ground at x, y, seen from
// `distance` away at `pitch` below the horizon, facing `heading`.
static void photoCamera(void *view, Matrix &m) {
    float s = (float)sin(mwPhoto.pitch), c = (float)cos(mwPhoto.pitch), d = mwPhoto.distance;
    float rightX = (float)cos(mwPhoto.heading), rightY = -(float)sin(mwPhoto.heading);
    V3 focus = {mwPhoto.x, mwPhoto.y, ground(mwPhoto.x, mwPhoto.y)};
    m.m[0][0] = rightX;    m.m[1][0] = rightY;    m.m[2][0] = 0;
    m.m[0][1] = -rightY*s; m.m[1][1] = rightX*s;  m.m[2][1] = c;
    m.m[0][2] = rightY*c;  m.m[1][2] = -rightX*c; m.m[2][2] = s;
    m.m[0][3] = focus.x + m.m[0][2]*d;
    m.m[1][3] = focus.y + m.m[1][2]*d;
    m.m[2][3] = focus.z + s*d;
    void *camera = field<void*>(view, 0x104);
    if (camera) {
        float nearZ = clamp(d*0.02f, 10, 1000), farZ = d*2 + 20000;
        if (field<float>(camera, 0xF0) < farZ) field<float>(camera, 0xF0) = farZ;
        if (field<float>(camera, 0xEC) < nearZ) field<float>(camera, 0xEC) = nearZ;
        field<U8>(camera, 0xFC) = 0;
    }
}

static void __fastcall buildHook(void *view, void *, Matrix *out) {
    ((BuildFn)buildOriginal)(view, 0, out);
    if (mwPhoto.enabled && mwPhoto.pitch > 0 && mwPhoto.distance > 0 && view == tactical() && inMatch()) {
        photoCamera(view, *out);
        return;
    }
    if (!controls(view)) {
        if (view == tactical()) release();
        return;
    }
    Matrix &m = *out;
    float rightX = m.m[0][0], rightY = m.m[1][0], length = (float)sqrt(rightX*rightX + rightY*rightY);
    float backZ = m.m[2][2], height = m.m[2][3] - field<float>(view, 0x14);
    if (!(length > 0.1f) || !(backZ > 0.05f) || !(height > 0)) return;
    rightX /= length; rightY /= length;
    float reach = height/backZ;
    gameReach = reach;
    V3 focus = {m.m[0][3] - m.m[0][2]*reach, m.m[1][3] - m.m[1][2]*reach, field<float>(view, 0x14)};
    LARGE_INTEGER now;
    QueryPerformanceCounter(&now);
    float dt = clamp((float)((double)(now.QuadPart - lastBuild.QuadPart)/frequency.QuadPart), 0, 0.1f);
    lastBuild = now;
    if (!mwCamera.active) {
        if (!wanted) return;
        mwCamera.active = 1;
        mwCamera.distance = mwCamera.target = reach;
        mwCamera.pitch = (float)asin(backZ > 1 ? 1 : backZ);
        dt = 0;
    }
    mwCamera.target = clamp(mwCamera.target*zoomFactor, mwCamera.minDistance, mwCamera.maxDistance);
    mwCamera.pitch = clamp(mwCamera.pitch + tiltDelta, MIN_PITCH, MAX_PITCH);
    zoomFactor = 1; tiltDelta = 0; wanted = false;
    float d = mwCamera.distance;
    d = mwCamera.target + (d - mwCamera.target)*(float)exp(-EASE_RATE*dt);
    if (fabs(d - mwCamera.target) < mwCamera.target*0.001f) d = mwCamera.target;
    mwCamera.distance = d;
    // Over a hill behind the focus, look down more steeply instead of from inside it.
    float s = (float)sin(mwCamera.pitch), c = (float)cos(mwCamera.pitch);
    float floor = ground(focus.x + rightY*c*d, focus.y - rightX*c*d) + CLEARANCE;
    if (focus.z + s*d < floor) {
        s = clamp((floor - focus.z)/d, s, 1);
        c = (float)sqrt(1 - s*s);
    }
    m.m[0][0] = rightX;    m.m[1][0] = rightY;    m.m[2][0] = 0;
    m.m[0][1] = -rightY*s; m.m[1][1] = rightX*s;  m.m[2][1] = c;
    m.m[0][2] = rightY*c;  m.m[1][2] = -rightX*c; m.m[2][2] = s;
    m.m[0][3] = focus.x + m.m[0][2]*d;
    m.m[1][3] = focus.y + m.m[1][2]*d;
    m.m[2][3] = focus.z + s*d;
    // Clip planes (CameraClass +0xEC near, +0xF0 far; +0xFC frustum valid):
    // the game's 10 to 1800 would cut the map off at a distance.
    void *camera = field<void*>(view, 0x104);
    if (camera) {
        float nearZ = clamp(d*0.02f, 10, 1000), farZ = d*2 + 20000;
        if (field<float>(camera, 0xF0) < farZ) field<float>(camera, 0xF0) = farZ;
        if (field<float>(camera, 0xEC) < nearZ) field<float>(camera, 0xEC) = nearZ;
        field<U8>(camera, 0xFC) = 0;
    }
    mwCamera.builds++;
}

static void __fastcall zoomInHook(void *view, void *) {
    if (!controls(view)) { ((ViewFn)zoomInOriginal)(view, 0); return; }
    zoomFactor /= ZOOM_STEP; wanted = true;
}

static void __fastcall zoomOutHook(void *view, void *) {
    if (!controls(view)) { ((ViewFn)zoomOutOriginal)(view, 0); return; }
    zoomFactor *= ZOOM_STEP; wanted = true;
}

static U32 __fastcall scrollHook(void *view, void *, float *delta) {
    if (!delta || !mwCamera.active || !controls(view) || !(gameReach > 0))
        return ((ScrollFn)scrollOriginal)(view, 0, delta);
    float scale = mwCamera.distance/gameReach, scaled[2] = {delta[0]*scale, delta[1]*scale};
    return ((ScrollFn)scrollOriginal)(view, 0, scaled);
}

// A middle click: the game's camera again, at its default heading and height.
static void __fastcall resetHook(void *view, void *, int a, int b, float c, float d) {
    if (view == tactical()) release();
    ((ResetFn)resetOriginal)(view, 0, a, b, c, d);
}

// Every Win32 mouse message the game takes in, passed on unchanged. With the
// middle button held, vertical motion tilts (the game turns sideways motion).
static void __fastcall mouseHook(void *mouse, void *, UINT message, WPARAM w, LPARAM l, DWORD time) {
    int y = (short)HIWORD(l);
    if (message == WM_MBUTTONDOWN) { middleDown = true; lastY = y; }
    else if (message == WM_MBUTTONUP) middleDown = false;
    else if (message == WM_MOUSEMOVE && middleDown) {
        if (!(w & MK_MBUTTON)) middleDown = false;
        else if (y != lastY) {
            void *view = tactical();
            if (view && controls(view)) { tiltDelta += (y - lastY)*TILT_PER_PIXEL; wanted = true; }
            lastY = y;
        }
    }
    ((MouseFn)mouseOriginal)(mouse, 0, message, w, l, time);
}

static void __fastcall updateHook(void *view, void *) {
    if (mwPhoto.enabled && view == tactical() && inMatch()) {
        typedef void (__fastcall *LookAtFn)(void*, void*, const V3*);
        typedef void (__fastcall *HeightFn)(void*, void*, float);
        V3 focus = {mwPhoto.x, mwPhoto.y, ground(mwPhoto.x, mwPhoto.y)};
        address<LookAtFn>(0x8D55D)(view, 0, &focus);
        address<HeightFn>(0x8D2B8)(view, 0, mwPhoto.height);
    }
    U32 builds = mwCamera.builds;
    ((ViewFn)updateOriginal)(view, 0);
    // A cinematic photo: rebuild every frame, so the game cannot keep its own.
    if (mwPhoto.enabled && mwPhoto.pitch > 0 && view == tactical() && inMatch())
        address<ViewFn>(0x8BE6B)(view, 0);
    // The game rebuilds its camera only when something moved it: rebuild for
    // new input and while the zoom eases (setCameraTransform, 0x8BE6B).
    if (view == tactical() && builds == mwCamera.builds && controls(view)
        && (wanted || (mwCamera.active && mwCamera.distance != mwCamera.target)))
        address<ViewFn>(0x8BE6B)(view, 0);
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

// Each hook site: its RVA, the whole instructions it moves, its replacement.
struct Site { U32 rva; U8 bytes[6]; int length; void *replacement; void **original; };

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID) {
    if (reason != DLL_PROCESS_ATTACH) return TRUE;
    DisableThreadLibraryCalls(instance);
    base = (U8*)GetModuleHandleA(0);
    QueryPerformanceFrequency(&frequency);
    QueryPerformanceCounter(&lastBuild);
    Site sites[] = {
        {0x122BE0, {0x64, 0xa1, 0, 0, 0, 0}, 6, endHook, &endOriginal},             // mov eax, fs:[0]
        {0x85B36, {0x81, 0xc1, 0xb4, 0, 0, 0}, 6, updateHook, &updateOriginal},     // add ecx, 0B4h
        {0x8A653, {0xb8, 0xbb, 0xfb, 0xb5, 0}, 5, buildHook, &buildOriginal},       // mov eax, 0B5FBBBh
        {0x25EA2E, {0x56, 0x57, 0x8b, 0xf9, 0x8b, 0x37}, 6, zoomInHook, &zoomInOriginal},    // push esi; push edi;
        {0x25EA55, {0x56, 0x57, 0x8b, 0xf9, 0x8b, 0x37}, 6, zoomOutHook, &zoomOutOriginal},  // mov edi, ecx; mov esi, [edi]
        {0x8D925, {0x55, 0x8b, 0xec, 0x53, 0x56}, 5, resetHook, &resetOriginal},    // push ebp; mov ebp, esp; push ebx; push esi
        {0x41A10, {0x8b, 0x81, 0x10, 0x60, 0, 0}, 6, mouseHook, &mouseOriginal},    // mov eax, [ecx+6010h]
        {0x8CE2E, {0x55, 0x8b, 0xec, 0x83, 0xec, 0x64}, 6, scrollHook, &scrollOriginal},     // push ebp; mov ebp, esp; sub esp, 64h
    };
    const int count = sizeof(sites)/sizeof(sites[0]);
    if (base != (U8*)0x400000) return FALSE;
    for (int i = 0; i < count; i++)
        if (memcmp(base + sites[i].rva, sites[i].bytes, sites[i].length)) return FALSE;
    for (int i = 0; i < count; i++) {
        *sites[i].original = hook(sites[i].rva, sites[i].replacement, sites[i].bytes, sites[i].length);
        if (!*sites[i].original) {
            for (int j = 0; j < i; j++) undoHook(sites[j].rva, *sites[j].original, sites[j].length);
            return FALSE;
        }
    }
    mwInstalled = 1;
    return TRUE;
}
