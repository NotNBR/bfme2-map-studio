"""Original score for the map viewer trailer, cut to its timeline.

A calm D-major pad that builds under the viewer reveal, soft clicks and
bells where the cursor acts, a quiet ticking bed under the terminal, a swell
on the before/after wipe and a resolving chord on the end card.
"""
import math
import wave
from pathlib import Path

import numpy as np

RATE = 48000


def score(duration, output, clicks=(), typing=(), cuts=None, accents=()):
    """`clicks`: times of cursor clicks; `typing`: (start, end) spans of typed
    text; `cuts`: dict of section start times (see trailer.TIMELINE);
    `accents`: times of smaller reveals after the main one."""
    cuts = cuts or {}
    mix = np.zeros((round(RATE*duration), 2))
    rng = np.random.default_rng(31415)

    def add(start, note, length, gain, pan=0.0, style='pad'):
        count = int(length*RATE)
        if count <= 0:
            return
        t = np.arange(count)/RATE
        hz = 440*2**((note-69)/12)
        if style == 'pad':
            phase = 2*np.pi*hz*t + .03*np.sin(2*np.pi*3.8*t)
            sig = sum(np.sin(phase*h + d*t)/(h**1.5) for h, d in [(1, -.7), (1, .7), (2, .5), (3, -.4)])*.4
            env = np.minimum(t/1.2, 1)*np.minimum((length-t)/1.5, 1)
        elif style == 'pluck':
            sig = np.sin(2*np.pi*hz*t) + .4*np.sin(2*np.pi*hz*2*t) + .15*np.sin(2*np.pi*hz*3*t)
            env = np.minimum(t/.004, 1)*np.exp(-t*3.2)
        elif style == 'bell':
            sig = np.sin(2*np.pi*hz*t) + .35*np.sin(2*np.pi*hz*2.76*t) + .2*np.sin(2*np.pi*hz*5.4*t)
            env = np.minimum(t/.003, 1)*np.exp(-t*1.6)
        elif style == 'click':
            noise = rng.normal(0, 1, count)
            sig = (noise - np.convolve(noise, np.ones(5)/5, mode='same'))*.6 + np.sin(2*np.pi*1900*t)*.5
            env = np.exp(-t*90)
        elif style == 'tick':
            noise = rng.normal(0, 1, count)
            sig = noise - np.convolve(noise, np.ones(9)/9, mode='same')
            env = np.exp(-t*160)
        elif style == 'boom':
            sig = np.sin(2*np.pi*(48*t + 30*.08*(1-np.exp(-t/.08))))
            env = np.minimum(t/.01, 1)*np.exp(-t*1.8)
        elif style == 'swell':
            noise = rng.normal(0, 1, count)
            sig = np.convolve(noise, np.ones(40)/40, mode='same')*3
            env = (t/length)**2*np.minimum((length-t)/.05, 1)
        else:
            raise ValueError(style)
        sig = sig*env*gain
        offset = int(start*RATE)
        end = min(len(mix), offset+count)
        if end <= offset:
            return
        sig = sig[:end-offset]
        mix[offset:end, 0] += sig*math.sqrt((1-pan)/2)
        mix[offset:end, 1] += sig*math.sqrt((1+pan)/2)

    # D major / B minor / G major / A major, voiced low and open.
    chords = [(50, 57, 62, 66), (47, 54, 59, 62), (43, 50, 55, 59), (45, 52, 57, 61)]
    bar = 3.0
    reveal = cuts.get('edit', duration*0.75)
    end_card = cuts.get('close', duration-6)
    t, i = 0.0, 0
    while t < duration-1:
        chord = chords[i % 4]
        gain = .05 if t < cuts.get('viewer', 6) else (.075 if t < reveal else .09)
        for k, note in enumerate(chord):
            add(t, note, bar+1.6, gain, (k-1.5)/2.5)
        add(t, chord[0]-12, bar+1.2, gain*1.3)
        # A gentle pulse once the viewer is on screen, resting under the terminal.
        if cuts.get('viewer', 6) <= t < duration-6 and not (cuts.get('terminal', 1e9) <= t < reveal):
            for n in range(6):
                add(t+n*bar/6, chord[n % 4]+12, .9, .03 if n % 2 else .045, (-1)**n*.4, 'pluck')
        t += bar
        i += 1
    for c in clicks:
        add(c, 0, .05, .25, .2, 'click')
        add(c+.01, 81, 1.4, .05, .3, 'bell')
    for start, stop in typing:
        k = start
        while k < stop:
            add(k, 0, .03, .12, rng.uniform(-.4, .4), 'tick')
            k += rng.uniform(.045, .09)
    # The before/after wipe: a swell into a low hit and a bright chord.
    add(reveal-1.4, 0, 1.4, .25, 0, 'swell')
    add(reveal, 0, 3.0, .55, 0, 'boom')
    for k, note in enumerate((62, 66, 69, 74)):
        add(reveal, note, 4.5, .06, (k-1.5)/2, 'bell')
    # Later reveals: a shorter swell and a softer, higher chord.
    for at in accents:
        add(at - 0.9, 0, 0.9, .14, 0, 'swell')
        add(at, 0, 2.0, .3, 0, 'boom')
        for k, note in enumerate((66, 69, 74, 78)):
            add(at + k*.06, note, 3.5, .045, (k-1.5)/2, 'bell')
    # End card: resolve on D with a long bell.
    for k, note in enumerate((50, 57, 62, 66, 69)):
        add(end_card, note, duration-end_card, .08, (k-2)/3)
    add(end_card, 74, 5, .07, 0, 'bell')
    # A small stereo room, fade in and out, normalise.
    dry = mix.copy()
    for delay, gain in ((.097, .14), (.211, .09), (.343, .06)):
        offset = int(delay*RATE)
        mix[offset:] += dry[:-offset, ::-1]*gain
    n = np.arange(len(mix))/RATE
    mix *= (np.minimum(n/1.5, 1)*np.minimum((duration-n)/2.5, 1))[:, None]
    mix = np.tanh(mix*1.1)
    mix *= .82/max(float(np.abs(mix).max()), 1e-3)
    path = Path(output)/'score.wav'
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((mix*32767).astype('<i2').tobytes())
    return path
