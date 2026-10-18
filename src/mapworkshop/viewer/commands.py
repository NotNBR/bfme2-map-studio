"""The viewer's commands, each defined once: what it does, its label, its
keys and its check mark. Keys, toolbar buttons and the View menu all run
commands from one Commands registry.

Keys are written as in the docs: 'G', '7', 'F5', 'Space', 'Esc', 'Del',
'Ctrl+B', 'Ctrl+Shift+1'. A key without Ctrl also answers with Ctrl held,
unless a Ctrl binding takes that key (Ctrl+B builds, B toggles the border);
Shift counts only for a binding that names it.
"""

from dataclasses import dataclass
from typing import Callable, Optional

# Key names that differ from GLFW's (KEY_ESCAPE for 'Esc').
GLFW_NAMES = {'Esc': 'ESCAPE', 'Del': 'DELETE', 'Space': 'SPACE', 'Home': 'HOME', 'Backspace': 'BACKSPACE'}


@dataclass
class Command:
    id: str
    run: Callable[[], None]
    label: str = ''
    keys: tuple = ()
    checked: Optional[Callable[[], bool]] = None   # a check mark in a menu
    needs_scene: bool = True                       # does nothing until a map is loaded
    when: Optional[Callable[[], bool]] = None      # and only while this holds


def parse_key(name):
    """'Ctrl+B' -> ('B', True, False): the key's GLFW name and whether Ctrl
    and Shift are part of it."""
    *mods, key = name.split('+')
    if any(m not in ('Ctrl', 'Shift') for m in mods) or not key or (mods and mods[0] != 'Ctrl'):
        raise ValueError(f'unknown key {name!r}: only Ctrl+ and Ctrl+Shift+ are supported')
    return GLFW_NAMES.get(key, key.upper()), 'Ctrl' in mods, 'Shift' in mods


class Commands:
    """`keycode(name)`: the GLFW key code for a GLFW key name ('B' for KEY_B)."""

    def __init__(self, keycode):
        self.keycode = keycode
        self.by_id = {}
        self.by_key = {}          # (key code, ctrl, shift) -> Command

    def add(self, *commands):
        for command in commands:
            if command.id in self.by_id:
                raise ValueError(f'two commands are called {command.id!r}')
            self.by_id[command.id] = command
            for name in command.keys:
                key, ctrl, shift = parse_key(name)
                binding = (self.keycode(key), ctrl, shift)
                if binding in self.by_key:
                    raise ValueError(f'{name} is bound to both {self.by_key[binding].id!r} and {command.id!r}')
                self.by_key[binding] = command

    def __getitem__(self, command_id):
        return self.by_id[command_id]

    def for_key(self, key, ctrl, shift=False):
        """The command a key press runs, or None."""
        command = self.by_key.get((key, ctrl, shift))
        if command is None and shift:
            command = self.by_key.get((key, ctrl, False))
        if command is None and ctrl:
            command = self.by_key.get((key, False, False))
        return command

    def run(self, command, scene):
        """Run a command (or its id) if it can run now; `scene`: a map is
        loaded. True when it ran."""
        if isinstance(command, str):
            command = self.by_id[command]
        if (command.needs_scene and not scene) or (command.when and not command.when()):
            return False
        command.run()
        return True

    def menu(self, layout, scene):
        """Menu entries (value, text, checked) for a layout of command ids,
        None for a separator."""
        entries = []
        for command_id in layout:
            if command_id is None:
                entries.append((None, '', None))
                continue
            command = self.by_id[command_id]
            checked = bool(scene and command.checked and command.checked())
            entries.append((command_id, command.label, checked))
        return entries
