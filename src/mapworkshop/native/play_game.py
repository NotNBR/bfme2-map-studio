"""Start a skirmish on a map that you play, say when it is playable, and let
its window close.

Run by mapworkshop.native.play under bfme-workshop's Python; it imports
bfme-workshop's packages, never mapworkshop's:

  play_game.py MAP_ID LOG               e.g. 'maps\\map mp bridge lab.map'

Runs host.launch on the map (--window --strategic): you against an easy AI.
The launcher debugs the game, so breakpoints in it report what the game does,
as it does it (no polling):

- loaded: the new-game pass (GameLogic 0x248558, Open-BFME-2
  GameLogicInit.cpp) has loaded the map, placed the players and re-enabled
  the window's close item, in skirmish mode. Its next frame is gameplay.
- closed: the game has exited, by its window, a crash or the menus.

Each is a line `mapworkshop: <event> <seconds since start>` on the output,
which goes both to the log and to the caller (mapworkshop.native reads it).

Retail BFME2's window procedure ignores WM_CLOSE (WinMain.cpp: the case just
returns 0), so neither the window's X nor Alt+F4, which the system turns into
WM_CLOSE, ends the game. A breakpoint in that procedure sees the message: at
WM_CLOSE the game is terminated, which the launcher takes as its normal exit.
"""
import sys

# In WndProc (RVA 0x179F), `cmp ebx, 0x10` at 0x198A starts the arm for
# messages 0x10 to 0x1F; ebx holds the message. The others there are rare
# (WM_ERASEBKGND, WM_ACTIVATEAPP, ...), so the breakpoint costs nothing.
CLOSE_ARM = 0x198A
WM_CLOSE = 0x10
# The new-game pass destroying its close-item guard (0x0023C85E), after its
# last load stage: the map is loaded. The pass also loads the menu's shell
# map, so only the skirmish's counts.
NEW_GAME_DONE = 0x248767
SKIRMISH = 2                    # GameLogic's mode (+0x110) in a skirmish

map_id, log = sys.argv[1], sys.argv[2]


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


sys.stdout = sys.stderr = Tee(log, sys.__stdout__)


def event(game, name):
    print(f'mapworkshop: {name} {game.seconds()}', flush=True)


def hooked(smoke):
    original = smoke.Game
    smoke.RVA['mapworkshopWindowClose'] = CLOSE_ARM
    smoke.RVA['mapworkshopNewGameDone'] = NEW_GAME_DONE

    class PlayGame(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.on('mapworkshopWindowClose', self.close)
            self.on('mapworkshopNewGameDone', self.loaded)

        def run(self, *args, **kwargs):
            result = super().run(*args, **kwargs)
            if self.t0 is not None:
                event(self, 'closed')
            return result

        @staticmethod
        def close(game, tid, ctx):
            if ctx.ebx == WM_CLOSE:
                print('mapworkshop: the window was closed; ending the game', flush=True)
                game.k.TerminateProcess(game.hproc, 0)
            return True

        @staticmethod
        def loaded(game, tid, ctx):
            if game.logic()[1] != SKIRMISH:
                return True
            event(game, 'loaded')
            return False

    smoke.Game = PlayGame


# host.launch registers the camera on every launch, after the scenario hooks
# and before it creates the game: wrap that registration to add ours.
import strategic.camera as camera
register = camera.register


def register_hooked(smoke, *args, **kwargs):
    register(smoke, *args, **kwargs)
    hooked(smoke)


camera.register = register_hooked
import host.launch
sys.argv = ['host.launch', '--map', map_id, '--window', '--strategic']
raise SystemExit(host.launch.main())
