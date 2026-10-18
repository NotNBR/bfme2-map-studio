"""Photo effects: a camera lens and exposure over a rendered view.

The game has neither; the viewer's Photo mode and `mw render` views with
`focal`, `aperture`, `focus` or `ev` use them for pictures.

The lens is a full-frame camera's: a 36 x 24 mm sensor, its width across the
image. A focal length f gives a horizontal field of view of 2 atan(18 / f)
(39 mm is the preview cameras' 50 degrees). Depth of field follows the thin
lens: a point at distance D, focused at S with aperture f/N, blurs to a circle
of (f / N) x f / (S - f) x |D - S| / D on the sensor, scaled to pixels by
image width / 36 mm. Distances need a scale: UNITS_PER_METRE map units to the
metre (a soldier is about 20 units tall), so wide apertures blur as a real lens
would at that size.

Exposure multiplies the linear colour by 2^ev. The renderer's colours are
already display colours, so it brightens or darkens; it cannot bring back
highlights that were white.

Post draws a scene rendered into its multisampled target (target()) to a
framebuffer with both effects (finish()): the colour is resolved into a
texture with its depth, each pixel's blur circle is worked out from its depth,
and the blur gathers the samples whose circles cover the pixel (a sample
behind the pixel blurs no more than the pixel itself, so a sharp foreground
keeps its edge).
"""

import math

import numpy as np

SENSOR_WIDTH = 36.0                 # mm
UNITS_PER_METRE = 10.0
FOCAL_RANGE = 10.0, 600.0           # mm
MAX_BLUR = 0.02                     # the largest blur circle, as a share of the image width


def fov_from_focal(focal):
    """Horizontal field of view (degrees) of a focal length (mm)."""
    return 2*math.degrees(math.atan(SENSOR_WIDTH/2/focal))


def focal_from_fov(fov):
    """Focal length (mm) giving a horizontal field of view (degrees)."""
    return SENSOR_WIDTH/2/math.tan(math.radians(fov)/2)


def blur_pixels(distance, focus, focal, aperture, width):
    """Diameter in pixels of the blur circle of a point `distance` map units
    away, focused at `focus`, for a focal length (mm), an f-number and an
    image `width` pixels wide; not limited to MAX_BLUR."""
    d, s = distance/UNITS_PER_METRE*1000, focus/UNITS_PER_METRE*1000
    s = max(s, focal*1.001)
    circle = (focal/aperture)*focal/(s-focal)*abs(d-s)/max(d, 1e-6)
    return circle/SENSOR_WIDTH*width


def active(settings):
    """Whether photo `settings` (aperture, ev) change the image."""
    return bool(settings.get('aperture')) or abs(settings.get('ev') or 0.0) > 1e-6


VS = """
#version 430
in vec2 in_pos;
void main() { gl_Position = vec4(in_pos*2.0-1.0, 0.0, 1.0); }
"""

FS = """
#version 430
uniform sampler2D color_tex;
uniform sampler2D depth_tex;
uniform vec2 size;
uniform float near_z, far_z;
uniform float exposure;          // 2^ev
uniform int use_dof;
uniform float focus_mm, focal_mm, aperture_mm, px_per_mm, max_blur;
uniform int taps;
out vec4 frag;

float view_z(vec2 uv) {
    float z = texture(depth_tex, uv).r*2.0-1.0;
    return 2.0*near_z*far_z/(far_z+near_z-z*(far_z-near_z));
}
float blur(float units) {
    float d = max(units*100.0, 1e-3);                 // map units to mm (UNITS_PER_METRE 10)
    float s = max(focus_mm, focal_mm*1.001);
    return min(aperture_mm*focal_mm/(s-focal_mm)*abs(d-s)/d*px_per_mm, max_blur);
}
void main() {
    vec2 uv = gl_FragCoord.xy/size;
    vec3 c = texture(color_tex, uv).rgb;
    if (use_dof == 1) {
        float z0 = view_z(uv);
        float b0 = blur(z0);
        float w0 = 1.0/max(b0*b0, 1.0);
        vec3 sum = c*w0;
        float weight = w0;
        float golden = 2.39996323;
        for (int i = 0; i < taps; i++) {
            float r = sqrt((float(i)+0.5)/float(taps))*max_blur*0.5;
            vec2 o = vec2(cos(float(i)*golden), sin(float(i)*golden))*r;
            vec2 suv = uv + o/size;
            float z = view_z(suv);
            float b = blur(z);
            if (z > z0) b = min(b, b0);             // behind the pixel: no more blurred than it
            if (b*0.5 >= r) {
                float w = 1.0/max(b*b, 1.0);
                sum += texture(color_tex, suv).rgb*w;
                weight += w;
            }
        }
        c = sum/weight;
    }
    vec3 linear = pow(max(c, 0.0), vec3(2.2))*exposure;
    frag = vec4(pow(clamp(linear, 0.0, 1.0), vec3(1.0/2.2)), 1.0);
}
"""


class Post:
    """Exposure and depth of field for one GL context."""

    def __init__(self, ctx, samples=4):
        import moderngl
        self.ctx, self.mgl, self.samples = ctx, moderngl, samples
        self.program = ctx.program(vertex_shader=VS, fragment_shader=FS)
        quad = ctx.buffer(np.array([0, 0, 1, 0, 0, 1, 1, 1], 'f4').tobytes())
        self.vao = ctx.vertex_array(self.program, [(quad, '2f', 'in_pos')])
        self.size = None
        self.items = []

    def target(self, size):
        """The multisampled framebuffer to draw the scene into, `size` pixels."""
        if size != self.size:
            for item in self.items:
                item.release()
            ctx = self.ctx
            self.color = ctx.renderbuffer(size, 4, samples=self.samples)
            self.depth = ctx.depth_renderbuffer(size, samples=self.samples)
            self.fbo = ctx.framebuffer([self.color], self.depth)
            self.color_tex = ctx.texture(size, 4)
            self.depth_tex = ctx.depth_texture(size)
            for texture in (self.color_tex, self.depth_tex):
                texture.filter = (self.mgl.NEAREST, self.mgl.NEAREST)
                texture.repeat_x = texture.repeat_y = False
            self.resolved = ctx.framebuffer([self.color_tex], self.depth_tex)
            self.items = [self.fbo, self.resolved, self.color, self.depth, self.color_tex, self.depth_tex]
            self.size = size
        return self.fbo

    def finish(self, camera, settings, framebuffer, taps=48):
        """Draw the scene in target() to `framebuffer` with the photo
        `settings` (focal, aperture, focus, ev); `camera` is the resolved
        camera it was drawn with (its near and far)."""
        ctx, p = self.ctx, self.program
        ctx.copy_framebuffer(self.resolved, self.fbo)
        width, height = self.size
        framebuffer.use()
        ctx.viewport = (0, 0, width, height)
        ctx.disable(self.mgl.DEPTH_TEST)
        ctx.disable(self.mgl.BLEND)
        self.color_tex.use(0)
        self.depth_tex.use(1)
        p['color_tex'].value, p['depth_tex'].value = 0, 1
        p['size'].value = (float(width), float(height))
        p['near_z'].value, p['far_z'].value = float(camera['near']), float(camera['far'])
        p['exposure'].value = 2.0**float(settings.get('ev') or 0.0)
        aperture = settings.get('aperture')
        focal = float(settings.get('focal') or 39.0)
        p['use_dof'].value = int(bool(aperture))
        p['focus_mm'].value = float(settings.get('focus') or 1500.0)/UNITS_PER_METRE*1000
        p['focal_mm'].value = focal
        p['aperture_mm'].value = focal/float(aperture or 1.0)
        p['px_per_mm'].value = width/SENSOR_WIDTH
        p['max_blur'].value = max(2.0, MAX_BLUR*width)
        p['taps'].value = int(taps)
        self.vao.render(self.mgl.TRIANGLE_STRIP)

    def release(self):
        for item in self.items:
            item.release()
        self.items, self.size = [], None
