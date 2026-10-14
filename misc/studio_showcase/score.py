"""Original score for the Brightwater Fold showcase, cut to its timeline.

An open, slowly building D-dorian pad (a horn-call over the downs), soft
clicks and bells where the cursor acts, ticks under typing, a tape-stop
sweep on the rewind, a swell and low hit on every reveal and a resolving
chord on the end card.
"""
import math
import wave
from pathlib import Path

import numpy as np

RATE = 48000


def score(duration, output, clicks=(), typing=(), cuts=None, reveals=(), rewind=None):
    """`clicks`: cursor click times; `typing`: (start, end) spans of typing;
    `cuts`: section start times (showcase.TIMELINE); `reveals`: times the
    map changes on screen; `rewind`: (start, end) of the rewind."""
    cuts = cuts or {}
    mix = np.zeros((round(RATE*duration), 2))
    rng = np.random.default_rng(1913)

    def add(start, note, length, gain, pan=0.0, style='pad'):
        count = int(length*RATE)
        if count <= 0:
            return
        t = np.arange(count)/RATE
        hz = 440*2**((note-69)/12)
        if style == 'pad':
            phase = 2*np.pi*hz*t+.025*np.sin(2*np.pi*4.1*t)
            sig = sum(np.sin(phase*h+d*t)/(h**1.6) for h, d in [(1, -.6), (1, .6), (2, .4), (3, -.3), (4, .2)])*.38
            env = np.minimum(t/1.4, 1)*np.minimum((length-t)/1.6, 1)
        elif style == 'horn':
            vib = .004*np.sin(2*np.pi*5*t)*np.minimum(t/.6, 1)
            phase = 2*np.pi*hz*t*(1+vib)
            sig = np.sin(phase)+.5*np.sin(2*phase)+.28*np.sin(3*phase)+.12*np.sin(4*phase)
            env = np.minimum(t/.25, 1)*np.minimum((length-t)/.8, 1)
        elif style == 'pluck':
            sig = np.sin(2*np.pi*hz*t)+.4*np.sin(2*np.pi*hz*2*t)+.15*np.sin(2*np.pi*hz*3*t)
            env = np.minimum(t/.004, 1)*np.exp(-t*3.0)
        elif style == 'bell':
            sig = np.sin(2*np.pi*hz*t)+.35*np.sin(2*np.pi*hz*2.76*t)+.2*np.sin(2*np.pi*hz*5.4*t)
            env = np.minimum(t/.003, 1)*np.exp(-t*1.5)
        elif style == 'click':
            noise = rng.normal(0, 1, count)
            sig = (noise-np.convolve(noise, np.ones(5)/5, mode='same'))*.6+np.sin(2*np.pi*1900*t)*.5
            env = np.exp(-t*90)
        elif style == 'tick':
            noise = rng.normal(0, 1, count)
            sig = noise-np.convolve(noise, np.ones(9)/9, mode='same')
            env = np.exp(-t*160)
        elif style == 'boom':
            sig = np.sin(2*np.pi*(46*t+30*.08*(1-np.exp(-t/.08))))
            env = np.minimum(t/.01, 1)*np.exp(-t*1.7)
        elif style == 'swell':
            noise = rng.normal(0, 1, count)
            sig = np.convolve(noise, np.ones(40)/40, mode='same')*3
            env = (t/length)**2*np.minimum((length-t)/.05, 1)
        elif style == 'tapestop':
            # A chord falling in pitch and speed, like a tape brought to a stop.
            f = hz*np.maximum(1-t/length, .05)**1.6
            phase = 2*np.pi*np.cumsum(f)/RATE
            sig = np.sin(phase)+.5*np.sin(2*phase)+.3*np.sin(3*phase)
            env = np.minimum(t/.02, 1)*(1-t/length)**.5
        elif style == 'whoosh':
            noise = rng.normal(0, 1, count)
            k = np.convolve(noise, np.ones(12)/12, mode='same')
            sig = k*np.sin(np.pi*t/length)**2*2.5
            env = np.ones(count)
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

    # D dorian: Dm9 / C / G / Am7, voiced low and open; the pulse joins as the map grows.
    chords = [(50, 57, 62, 64, 65), (48, 55, 60, 64, 67), (43, 50, 55, 59, 62), (45, 52, 57, 60, 64)]
    bar = 3.2
    first = cuts.get('new', 9.0)
    end_card = cuts.get('end', duration-7)
    t, i = 0.0, 0
    while t < duration-1:
        chord = chords[i % 4]
        quiet = rewind and rewind[0] <= t < rewind[1]+.4
        gain = 0 if quiet else (.05 if t < first else .065 if t < cuts.get('populate', 40) else .08)
        for k, note in enumerate(chord):
            add(t, note, bar+1.8, gain, (k-2)/3)
        add(t, chord[0]-12, bar+1.4, gain*1.3)
        if first+3 <= t < end_card and not quiet:
            for n in range(8):
                add(t+n*bar/8, chord[n % 5]+12, .8, .028 if n % 2 else .04, (-1)**n*.4, 'pluck')
        t += bar
        i += 1
    # The horn-call: over the opening shot, and again over the final flight.
    for at, gain in ((.6, .05), (cuts.get('finale', duration-14), .06)):
        for k, (note, length) in enumerate([(62, 1.2), (69, .9), (67, .6), (69, 2.4)]):
            add(at+sum(l for _, l in [(62, 1.2), (69, .9), (67, .6), (69, 2.4)][:k]), note, length+.3, gain, -.2, 'horn')
    for c in clicks:
        add(c, 0, .05, .25, .2, 'click')
        add(c+.01, 81, 1.2, .045, .3, 'bell')
    for start, stop in typing:
        k = start
        while k < stop:
            add(k, 0, .03, .11, rng.uniform(-.4, .4), 'tick')
            k += rng.uniform(.045, .09)
    if rewind:
        a, b = rewind
        add(a, 62, b-a+.2, .12, 0, 'tapestop')
        add(a, 69, b-a+.2, .08, .3, 'tapestop')
        add(a-.3, 0, b-a+.6, .16, 0, 'whoosh')
    # Each reveal: a swell into a low hit and a bright chord, larger later on.
    for n, at in enumerate(reveals):
        weight = .6+.4*n/max(len(reveals)-1, 1)
        add(at-1.2, 0, 1.2, .2*weight, 0, 'swell')
        add(at, 0, 2.6, .45*weight, 0, 'boom')
        for k, note in enumerate((62, 69, 74, 77)):
            add(at+k*.05, note, 4.0, .045*weight, (k-1.5)/2, 'bell')
    # End card: resolve on D with a long bell.
    for k, note in enumerate((50, 57, 62, 66, 69)):
        add(end_card, note, duration-end_card, .085, (k-2)/3)
    add(end_card, 74, 5, .07, 0, 'bell')
    # A small stereo room, fade in and out, normalise.
    dry = mix.copy()
    for delay, gain in ((.097, .14), (.211, .09), (.343, .06)):
        offset = int(delay*RATE)
        mix[offset:] += dry[:-offset, ::-1]*gain
    n = np.arange(len(mix))/RATE
    mix *= (np.minimum(n/1.2, 1)*np.minimum((duration-n)/2.5, 1))[:, None]
    mix = np.tanh(mix*1.1)
    mix *= .82/max(float(np.abs(mix).max()), 1e-3)
    path = Path(output)/'score.wav'
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((mix*32767).astype('<i2').tobytes())
    return path
