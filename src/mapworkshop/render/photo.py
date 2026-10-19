"""Photo effects: a camera lens and exposure over a rendered view.

The game has neither; the viewer's Photo mode and `mw render` views with
`focal`, `aperture`, `focus` or `ev` use them for pictures.

The lens is a full-frame camera's: a 36 x 24 mm sensor. A picture of aspect
3:2 or wider is 36 mm wide on it, a narrower one 24 mm tall, as a camera's
crop modes take the largest frame of their aspect (sensor()). A focal length
f gives a frame w mm wide a horizontal field of view of 2 atan(w / 2f): at 3:2
and wider, 39 mm is the preview cameras' 50 degrees. Where the viewer shows a
frame inside a wider window, the window shows more around it at the frame's
scale (image_size()).

Depth of field follows the thin lens: a point at distance D, focused at S with
aperture f/N, blurs to a circle of (f / N) x f / (S - f) x |D - S| / D on the
sensor, scaled to pixels by the frame's pixels per mm. D and S are along the
view axis (the depth buffer's distance), so what is in focus is a plane, as
with a real lens. Distances need a scale: UNITS_PER_METRE map units to the
metre (a soldier is about 20 units tall), so wide apertures blur as a real lens
would at that size. Light mixes in linear colour, so a bright point spreads
into a bright disc. The aperture changes only the depth of field, as under
aperture-priority auto exposure; `ev` is the exposure compensation.

Exposure multiplies the linear colour by 2^ev. The renderer's colours are
already display colours (gamma 2.2), so it brightens or darkens; it cannot
bring back highlights that were white.

Post draws a scene rendered into its multisampled target (target()) to a
framebuffer with both effects (finish()): the colour is resolved into a
texture with its depth, and each pixel's blur circle is worked out from its
depth. Two small passes find how far blur reaches around each pixel: the
largest blur in each TILE x TILE tile, then the largest of the tiles it can
reach (MAX_BLUR, 6% of the width, is the most). The blur is Dennis
Gustafsson's single pass ("Bokeh depth of field in a single pass", 2018):
over a disc as large as that reach, every sample
whose own circle reaches the pixel joins a running average with equal weight,
and one that does not adds the average so far. So a blurred foreground spreads
over a sharp background, its outline soft, while a sample behind the pixel
counts with at most twice the pixel's own circle, so a sharp foreground keeps
its edge. The disc's sample pattern turns per pixel, which trades the repeated
copies a fixed pattern gives in large blur for fine grain. distance_at() reads
the depth back, to focus on whatever is under a pixel.
"""

import math

import numpy as np

SENSOR = 36.0, 24.0                 # mm, full frame
SENSOR_WIDTH = SENSOR[0]
UNITS_PER_METRE = 10.0
FOCAL_RANGE = 10.0, 600.0           # mm
MAX_BLUR = 0.06                     # the largest blur circle's diameter, as a share of the image width
SHARP = 1/1500                      # the blur counted as sharp, as a share of the frame's diagonal (0.029 mm on full frame)


def sensor(aspect):
    """(width, height) in mm of the largest frame of `aspect` (width / height)
    on the sensor: 36 mm wide at 3:2 and wider, 24 mm tall when narrower."""
    w, h = SENSOR
    return (w, w/aspect) if aspect >= w/h else (h*aspect, h)


def image_size(aspect, frame=None):
    """(width, height) in mm on the sensor's scale of an image of `aspect`
    holding a centred frame of aspect `frame` (None: the image is the frame),
    as viewer.camerabar.frame_rect fits a frame in the window."""
    if not frame:
        return sensor(aspect)
    fw, fh = sensor(frame)
    return (fw, fw/aspect) if aspect <= frame else (fh*aspect, fh)


def fov_from_focal(focal, width=SENSOR_WIDTH):
    """Horizontal field of view (degrees) of a focal length (mm) over an image
    `width` mm wide."""
    return 2*math.degrees(math.atan(width/2/focal))


def focal_from_fov(fov, width=SENSOR_WIDTH):
    """Focal length (mm) giving an image `width` mm wide a horizontal field of
    view (degrees)."""
    return width/2/math.tan(math.radians(fov)/2)


def _mm(units):
    return units/UNITS_PER_METRE*1000


def blur_pixels(distance, focus, focal, aperture, width, sensor_width=SENSOR_WIDTH):
    """Diameter in pixels of the blur circle of a point `distance` map units
    away, focused at `focus`, for a focal length (mm), an f-number and an
    image `width` pixels and `sensor_width` mm wide; not limited to MAX_BLUR."""
    d, s = _mm(distance), max(_mm(focus), focal*1.001)
    circle = (focal/aperture)*focal/(s-focal)*abs(d-s)/max(d, 1e-6)
    return circle/sensor_width*width


def sharp_range(focus, focal, aperture, aspect=1.5):
    """(near, far) map units between which the blur stays below SHARP of a
    frame of `aspect`'s diagonal; far is inf at and beyond the hyperfocal
    distance."""
    c = math.hypot(*sensor(aspect))*SHARP
    s = max(_mm(focus), focal*1.001)
    hyperfocal = focal*focal/(aperture*c) + focal
    near = s*(hyperfocal-focal)/(hyperfocal+s-2*focal)
    far = s*(hyperfocal-focal)/(hyperfocal-s) if s < hyperfocal else math.inf
    return near/1000*UNITS_PER_METRE, far/1000*UNITS_PER_METRE


def active(settings):
    """Whether photo `settings` (aperture, ev) change the image."""
    return bool(settings.get('aperture')) or abs(settings.get('ev') or 0.0) > 1e-6


TILE = 16                           # pixels per side of a tile of the blur's reach

VS = """
#version 430
in vec2 in_pos;
void main() { gl_Position = vec4(in_pos*2.0-1.0, 0.0, 1.0); }
"""

# The depth and the blur circle, for all three passes.
COMMON = """
#version 430
uniform sampler2D depth_tex;
uniform vec2 size;
uniform float near_z, far_z;
uniform float mm_per_unit, focus_mm, focal_mm, aperture_mm, px_per_mm, max_blur;

float view_z(float depth) {
    float z = depth*2.0-1.0;
    return 2.0*near_z*far_z/(far_z+near_z-z*(far_z-near_z));
}
// The blur circle's radius in pixels of a point `units` map units away.
float radius(float units) {
    float d = max(units*mm_per_unit, 1e-3);
    float s = max(focus_mm, focal_mm*1.001);
    return min(aperture_mm*focal_mm/(s-focal_mm)*abs(d-s)/d*px_per_mm, max_blur)*0.5;
}
"""

# Pass 1: each tile's largest blur radius.
TILE_FS = COMMON + """
uniform int tile;
out float reach;
void main() {
    ivec2 base = ivec2(gl_FragCoord.xy)*tile;
    ivec2 last = ivec2(size)-1;
    float m = 0.0;
    for (int y = 0; y < tile; y++)
        for (int x = 0; x < tile; x++)
            m = max(m, radius(view_z(texelFetch(depth_tex, min(base+ivec2(x, y), last), 0).r)));
    reach = m;
}
"""

# Pass 2: the largest of the tiles around, as far as the largest blur reaches.
SPREAD_FS = """
#version 430
uniform sampler2D tile_tex;
uniform int spread;
out float reach;
void main() {
    ivec2 t = ivec2(gl_FragCoord.xy);
    ivec2 last = textureSize(tile_tex, 0)-1;
    float m = 0.0;
    for (int y = -spread; y <= spread; y++)
        for (int x = -spread; x <= spread; x++)
            m = max(m, texelFetch(tile_tex, clamp(t+ivec2(x, y), ivec2(0), last), 0).r);
    reach = m;
}
"""

# Pass 3: the blur over the reach around each pixel, in linear colour, then the exposure.
FS = COMMON + """
uniform sampler2D color_tex;
uniform sampler2D reach_tex;
uniform float exposure;          // 2^ev
uniform int use_dof;
uniform int taps;
uniform int tile;
out vec4 frag;

vec3 linear(vec2 uv) { return pow(texture(color_tex, uv).rgb, vec3(2.2)); }

void main() {
    vec2 uv = gl_FragCoord.xy/size;
    vec3 c = linear(uv);
    float reach = use_dof == 1 ? texelFetch(reach_tex, ivec2(gl_FragCoord.xy)/tile, 0).r : 0.0;
    if (reach >= 0.5) {
        float z0 = view_z(texture(depth_tex, uv).r);
        float s0 = radius(z0);
        float golden = 2.39996323;
        // Interleaved gradient noise: the pattern's turn for this pixel.
        float turn = 6.2831853*fract(52.9829189*fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715))));
        float total = 1.0;
        for (int i = 0; i < taps; i++) {
            float r = sqrt((float(i)+0.5)/float(taps))*reach;
            float a = float(i)*golden + turn;
            vec2 suv = uv + vec2(cos(a), sin(a))*r/size;
            float z = view_z(texture(depth_tex, suv).r);
            float s = radius(z);
            if (z > z0) s = min(s, s0*2.0);         // behind the pixel: it cannot spread over a sharper pixel
            float m = smoothstep(r-0.5, r+0.5, s);  // does its circle reach this pixel?
            c += mix(c/total, linear(suv), m);
            total += 1.0;
        }
        c /= total;
    }
    frag = vec4(pow(clamp(c*exposure, 0.0, 1.0), vec3(1.0/2.2)), 1.0);
}
"""


class Post:
    """Exposure and depth of field for one GL context."""

    def __init__(self, ctx, samples=4):
        import moderngl
        self.ctx, self.mgl, self.samples = ctx, moderngl, samples
        self.quad = ctx.buffer(np.array([0, 0, 1, 0, 0, 1, 1, 1], 'f4').tobytes())
        self.programs, self.vaos = {}, {}
        for name, fs in (('tile', TILE_FS), ('spread', SPREAD_FS), ('blur', FS)):
            program = ctx.program(vertex_shader=VS, fragment_shader=fs)
            self.programs[name] = program
            self.vaos[name] = ctx.vertex_array(program, [(self.quad, '2f', 'in_pos')])
        self.size = None
        self.items = []

    def target(self, size):
        """The multisampled framebuffer to draw the scene into, `size` pixels."""
        if size != self.size:
            self._release_targets()
            ctx = self.ctx
            self.color = ctx.renderbuffer(size, 4, samples=self.samples)
            self.depth = ctx.depth_renderbuffer(size, samples=self.samples)
            self.fbo = ctx.framebuffer([self.color], self.depth)
            self.color_tex = ctx.texture(size, 4)
            self.depth_tex = ctx.depth_texture(size)
            tiles = (-(-size[0]//TILE), -(-size[1]//TILE))
            self.tile_tex = ctx.texture(tiles, 1, dtype='f4')
            self.reach_tex = ctx.texture(tiles, 1, dtype='f4')
            for texture in (self.color_tex, self.depth_tex, self.tile_tex, self.reach_tex):
                texture.filter = (self.mgl.NEAREST, self.mgl.NEAREST)
                texture.repeat_x = texture.repeat_y = False
            self.resolved = ctx.framebuffer([self.color_tex], self.depth_tex)
            self.tile_fbo = ctx.framebuffer([self.tile_tex])
            self.reach_fbo = ctx.framebuffer([self.reach_tex])
            self.items = [self.fbo, self.resolved, self.tile_fbo, self.reach_fbo, self.color, self.depth,
                          self.color_tex, self.depth_tex, self.tile_tex, self.reach_tex]
            self.size, self.tiles = size, tiles
        return self.fbo

    def finish(self, camera, settings, framebuffer, taps=128):
        """Draw the scene in target() to `framebuffer` with the photo
        `settings` (focal, aperture, focus, ev); `camera` is the resolved
        camera it was drawn with (its near and far, and `sensor`: the image's
        width in mm, SENSOR_WIDTH when missing)."""
        ctx, mgl = self.ctx, self.mgl
        ctx.copy_framebuffer(self.resolved, self.fbo)
        width, height = self.size
        aperture = settings.get('aperture')
        focal = float(settings.get('focal') or focal_from_fov(50.0))
        max_blur = max(2.0, MAX_BLUR*width)
        values = dict(size=(float(width), float(height)), near_z=float(camera['near']), far_z=float(camera['far']),
                      mm_per_unit=_mm(1.0), focus_mm=_mm(float(settings.get('focus') or 1500.0)), focal_mm=focal,
                      aperture_mm=focal/float(aperture or 1.0),
                      px_per_mm=width/float(camera.get('sensor') or SENSOR_WIDTH), max_blur=max_blur,
                      tile=TILE, spread=int(math.ceil(max_blur/2/TILE)), exposure=2.0**float(settings.get('ev') or 0.0),
                      use_dof=int(bool(aperture)), taps=int(taps), color_tex=0, depth_tex=1, tile_tex=2, reach_tex=3)
        for program in self.programs.values():
            for name, value in values.items():
                if name in program:
                    program[name].value = value
        ctx.disable(mgl.DEPTH_TEST)
        ctx.disable(mgl.BLEND)
        self.color_tex.use(0)
        self.depth_tex.use(1)
        if aperture:
            # Each tile's largest blur, then spread to the tiles it reaches.
            self.tile_fbo.use()
            ctx.viewport = (0, 0, *self.tiles)
            self.vaos['tile'].render(mgl.TRIANGLE_STRIP)
            self.tile_tex.use(2)
            self.reach_fbo.use()
            self.vaos['spread'].render(mgl.TRIANGLE_STRIP)
        self.reach_tex.use(3)
        framebuffer.use()
        ctx.viewport = (0, 0, width, height)
        self.vaos['blur'].render(mgl.TRIANGLE_STRIP)

    def distance_at(self, camera, x, y):
        """The distance along the view axis (map units) of what the last
        finish() drew at pixel (x, y) from the bottom left (the sky's dome
        too), or None where nothing was drawn."""
        depth = np.frombuffer(self.resolved.read(viewport=(int(x), int(y), 1, 1), components=1, attachment=-1,
                                                 dtype='f4'), 'f4')[0]
        if depth >= 1.0:
            return None
        near, far = float(camera['near']), float(camera['far'])
        z = depth*2.0-1.0
        return float(2.0*near*far/(far+near-z*(far-near)))

    def _release_targets(self):
        for item in self.items:
            item.release()
        self.items, self.size = [], None

    def release(self):
        """Free everything it holds on the GPU; it cannot be used after."""
        self._release_targets()
        for item in (*self.vaos.values(), *self.programs.values(), self.quad):
            item.release()
        self.vaos, self.programs = {}, {}
