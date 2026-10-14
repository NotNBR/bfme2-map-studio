"""Start a skirmish on a project that you play, say when it is playable, and
let its window close.

    python -m mapworkshop.native.play_game PROJECT LOG [--graphics Medium]

Started by mapworkshop.native.play, which reads its output; it stays running
as the game's debugger until the game closes. Being the debugger, it learns
what the game does from breakpoints, as it happens (no polling):

- loaded: the new-game pass (GameLogic 0x248558, Open-BFME-2
  GameLogicInit.cpp) has loaded the map, placed the players and re-enabled
  the window's close item, in skirmish mode. Its next frame is gameplay.
- closed: the game has exited, by its window, a crash or the menus.

Each is a line `mapworkshop: <event> <seconds since start>`, written both to
the log and to the caller.

Retail BFME2's window procedure ignores WM_CLOSE (WinMain.cpp: the case just
returns 0), so neither the window's X nor Alt+F4 ends the game. A breakpoint
in that procedure sees the message: at WM_CLOSE the game is ended.
"""
import argparse
import json
import sys

# In WndProc (RVA 0x179F), `cmp ebx, 0x10` at 0x198A starts the arm for
# messages 0x10 to 0x1F; ebx holds the message. The others there are rare
# (WM_ERASEBKGND, WM_ACTIVATEAPP, ...), so the breakpoint costs nothing.
CLOSE_ARM = 0x198A
WM_CLOSE = 0x10
# The new-game pass destroying its close-item guard (0x0023C85E), after its
# last load stage. The pass also loads the menu's shell map, so only the
# skirmish's counts.
NEW_GAME_DONE = 0x248767
WEEK = 7*24*3600


class Tee:
    """Output to the log and to the caller. A caller that has stopped reading
    (mw play returns once the game is playable) is dropped, never waited for:
    a blocked write would stall the debugger and freeze the game."""

    def __init__(self, path, pipe):
        self.log, self.pipe = open(path, 'w', encoding='utf-8'), pipe

    def write(self, text):
        self.log.write(text)
        self.log.flush()
        if self.pipe:
            try:
                self.pipe.write(text)
                self.pipe.flush()
            except (OSError, ValueError):
                self.pipe = None
        return len(text)

    def flush(self):
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('project')
    parser.add_argument('log')
    parser.add_argument('--graphics', default='Medium')
    args = parser.parse_args(argv)
    sys.stdout = sys.stderr = Tee(args.log, sys.__stdout__)
    from mapworkshop import project
    from mapworkshop.native import debugger, runtime

    def event(game, name):
        print(f'mapworkshop: {name} {game.seconds()}', flush=True)

    def close(game, tid, ctx):
        if ctx.ebx == WM_CLOSE:
            print('mapworkshop: the window was closed; ending the game', flush=True)
            game.stop('closed')
        return True

    def loaded(game, tid, ctx):
        if game.logic()[1] != debugger.SKIRMISH:
            return True
        event(game, 'loaded')
        return False

    game = runtime.start(project.find(args.project), args.graphics)
    game.on(CLOSE_ARM, close)
    game.on(NEW_GAME_DONE, loaded)
    print(f'mapworkshop: starting {game.args}', flush=True)
    try:
        result = game.run(WEEK)
    finally:
        if game.t0 is not None:
            event(game, 'closed')
    print(json.dumps(result, default=str), flush=True)
    return 0 if result['stopped'] in ('closed', 'exit') else 1


if __name__ == '__main__':
    raise SystemExit(main())
