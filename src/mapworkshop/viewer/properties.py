"""The viewer's Properties dialog: view and edit a map's map-wide settings.

A native window (tkinter) on its own thread, so the 3D view keeps drawing
while it is open. It shows every property of mapkit.properties with the
map's current value, or the game's default where the map leaves a map.ini
field out. For a project it also edits map.toml's title, description and
weather preset; Save writes the changes into map.toml (the edited fields
become [properties] overrides) and asks the viewer to rebuild. A game map
or a loose .map file is shown read-only.
"""

import threading

from mapworkshop.formats.map import Map
from mapworkshop.mapkit import properties
from mapworkshop.mapkit.weather import PRESETS

FONT = ('Segoe UI', 10)
SMALL = ('Segoe UI', 9)
MUTED = '#6e727c'
ACCENT = '#2f6fc8'
# Set from map.toml's title and description by the project's build.
DERIVED = {('world', 'mapName'): 'title', ('world', 'mapDescription'): 'description'}


def ini_texts(assets):
    """The game's INI texts the dialog takes its defaults from (properties.defaults)."""
    return dict(Weather=assets.ini_text('weather.ini'), WaterTransparency=assets.ini_text('water.ini'))


def choose_map_file(folder):
    """A .map file chosen in the system's file dialog, starting in `folder` (Browse...); None if none was. It
    blocks the calling thread while the dialog is open."""
    from pathlib import Path
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    path = filedialog.askopenfilename(title='Open a BFME2 map', initialdir=str(folder),
                                      filetypes=[('BFME2 maps', '*.map'), ('All files', '*.*')])
    root.destroy()
    return Path(path) if path else None


class PropertiesDialog:
    """Open with open(); `on_saved(project)` runs on the dialog's thread after
    a project's map.toml was written."""

    def __init__(self, map_path, project, ini_texts, on_saved):
        self.map_path, self.project, self.on_saved = map_path, project, on_saved
        ini_path = map_path.parent/'map.ini'
        ini = ini_path.read_text(encoding='ascii', errors='replace') if ini_path.exists() else ''
        self.current = properties.read(Map(map_path.read_bytes()), ini)
        self.defaults = properties.defaults(ini_texts)
        self.overrides = properties.flatten(project.config.get('properties')) if project else {}
        self.thread = None

    @property
    def is_open(self):
        return self.thread is not None and self.thread.is_alive()

    def open(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def lift(self):
        """Bring the open window to the front (from any thread)."""
        root = getattr(self, 'root', None)
        if root is not None and self.is_open:
            root.after(0, lambda: (root.deiconify(), root.lift(), root.focus_force()))

    # The window -------------------------------------------------------------
    def _run(self):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk = tk, ttk
        root = self.root = tk.Tk()
        editable = self.project is not None
        title = self.project.title if self.project else self.map_path.stem
        root.title(f'Map properties - {title}')
        root.configure(padx=14, pady=12)
        root.option_add('*Font', FONT)
        style = ttk.Style(root)
        if 'vista' in style.theme_names():
            style.theme_use('vista')
        style.configure('Muted.TLabel', foreground=MUTED, font=SMALL)
        style.configure('Override.TLabel', foreground=ACCENT, font=SMALL)
        style.configure('Head.TLabel', font=(FONT[0], 11, 'bold'))
        style.configure('Default.TEntry', foreground=MUTED)

        where = (f'Project {self.project.folder.name}: edits are saved to map.toml and the map is rebuilt.'
                 if editable else 'A game map or a loose .map file: shown read-only. '
                                  'Projects keep their properties in map.toml.')
        ttk.Label(root, text=title, style='Head.TLabel').grid(row=0, column=0, sticky='w')
        ttk.Label(root, text=where, style='Muted.TLabel').grid(row=1, column=0, sticky='w', pady=(0, 8))
        notebook = self.notebook = ttk.Notebook(root)
        notebook.grid(row=2, column=0, sticky='nsew')
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        self.fields = {}     # (where, key) -> dict(var, initial, prop, status)
        self.settings = {}   # map.toml key -> (var, initial)
        self.reset = set()   # overrides to drop
        if editable:
            self._project_tab(notebook)
        for group in properties.GROUPS:
            self._group_tab(notebook, group, editable)

        bar = ttk.Frame(root)
        bar.grid(row=3, column=0, sticky='ew', pady=(10, 0))
        bar.columnconfigure(0, weight=1)
        legend = 'Grey values: the game default, left out by the map.'
        ttk.Label(bar, text=('Blue: set by map.toml.  ' if editable else '') + legend,
                  style='Muted.TLabel').grid(row=0, column=0, sticky='w')
        if editable:
            ttk.Button(bar, text='Cancel', command=root.destroy).grid(row=0, column=1, padx=(8, 0))
            save = ttk.Button(bar, text='Save and build', command=self._save, default='active')
            save.grid(row=0, column=2, padx=(8, 0))
        else:
            ttk.Button(bar, text='Close', command=root.destroy).grid(row=0, column=1, padx=(8, 0))
        root.bind('<Escape>', lambda _: root.destroy())
        root.update_idletasks()
        root.minsize(root.winfo_reqwidth(), min(root.winfo_reqheight(), 760))
        # Come up in front of the viewer, then behave like any window.
        root.attributes('-topmost', True)
        root.after(300, lambda: root.attributes('-topmost', False))
        root.focus_force()
        root.mainloop()
        # Tk variables call into Tcl when they are freed, which only works on
        # this thread: drop every reference before it ends.
        self.fields, self.settings, self.notebook, self.root = {}, {}, None, None
        del root, style, notebook
        import gc
        gc.collect()

    def _tab(self, notebook, name):
        frame = self.ttk.Frame(notebook, padding=(12, 10))
        frame.columnconfigure(1, weight=1)
        notebook.add(frame, text=name)
        return frame

    def _row_label(self, frame, row, label, help_text):
        ttk = self.ttk
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky='nw', padx=(0, 12), pady=(6, 0))
        if help_text:
            ttk.Label(frame, text=help_text, style='Muted.TLabel', wraplength=520, justify='left').grid(
                row=row+1, column=0, columnspan=4, sticky='w', pady=(0, 2))

    def _project_tab(self, notebook):
        tk, ttk = self.tk, self.ttk
        frame = self._tab(notebook, 'Project')
        config = self.project.config
        rows = [('title', 'Title', 'The map\'s name in the game\'s lists and in WorldInfo.'),
                ('description', 'Description', 'Shown under the map in the game\'s map list.'),
                ('weather', 'Weather preset', 'The project\'s weather (mapkit.weather): fog, rain or snow, '
                                              'sun and sky. Fields on the Weather tab override it.')]
        for i, (key, label, help_text) in enumerate(rows):
            self._row_label(frame, 2*i, label, help_text)
            value = str(config.get(key, 'clear' if key == 'weather' else ''))
            var = tk.StringVar(value=value)
            if key == 'weather':
                widget = ttk.Combobox(frame, textvariable=var, values=list(PRESETS), state='readonly', width=18)
                widget.grid(row=2*i, column=1, sticky='w', pady=(6, 0))
            else:
                ttk.Entry(frame, textvariable=var, width=60).grid(row=2*i, column=1, columnspan=2, sticky='ew', pady=(6, 0))
            self.settings[key] = (var, value)
        n = 2*len(rows)
        for label, value in (('Native name', self.project.native_name), ('Players', self.project.players),
                             ('Folder', f'maps/{self.project.folder.name}')):
            ttk.Label(frame, text=label).grid(row=n, column=0, sticky='w', pady=(8, 0))
            ttk.Label(frame, text=str(value), style='Muted.TLabel').grid(row=n, column=1, sticky='w', pady=(8, 0))
            n += 1

    def _group_tab(self, notebook, group, editable):
        tk, ttk = self.tk, self.ttk
        frame = self._tab(notebook, group)
        row = 0
        for prop in [p for p in properties.PROPERTIES if p['group'] == group]:
            key = (prop['where'], prop['key'])
            value = self.current.get(key)
            unset = value is None
            if unset:
                value = self.defaults.get(key)
            derived = editable and key in DERIVED
            help_text = prop.get('help', '')
            if derived:
                help_text = (help_text + ' ' if help_text else '') + f'Set from the project\'s {DERIVED[key]} (Project tab).'
            self._row_label(frame, row, prop['label'], help_text)
            state = 'normal' if editable and not derived else 'disabled'
            initial = properties.display(prop, value)
            # The input, with an RGB entry's colour button beside it.
            cell = ttk.Frame(frame)
            cell.grid(row=row, column=1, sticky='w', pady=(6, 0))
            if prop['kind'] == 'bool':
                var = tk.BooleanVar(value=bool(value))
                initial = bool(value)
                widget = ttk.Checkbutton(cell, variable=var, state=state)
            elif prop['kind'] == 'choice':
                labels = dict(prop['choices'])
                var = tk.StringVar(value=labels.get(value, '' if value is None else str(value)))
                initial = var.get()
                widget = ttk.Combobox(cell, textvariable=var, values=list(labels.values()), width=18,
                                      state='readonly' if state == 'normal' else 'disabled')
            else:
                var = tk.StringVar(value=initial)
                widget = ttk.Entry(cell, textvariable=var, width=34 if prop['kind'] == 'text' else 18,
                                   state=state, style='Default.TEntry' if unset else 'TEntry')
            widget.grid(row=0, column=0, sticky='w')
            if prop['kind'] == 'rgb':
                self._swatch(cell, var, state)
            status = ttk.Label(frame, style='Muted.TLabel')
            status.grid(row=row, column=3, sticky='e', pady=(6, 0), padx=(8, 0))
            entry = dict(var=var, initial=initial, prop=prop, status=status, unset=unset)
            self.fields[key] = entry
            if editable and key in self.overrides:
                self._mark_override(frame, row, key)
            elif unset:
                status.configure(text='game default' if self.defaults.get(key) is not None else 'not set')
            row += 2

    def _swatch(self, cell, var, state):
        """A colour button next to an R G B entry, opening the colour picker."""
        tk = self.tk
        from tkinter import colorchooser

        def colour():
            try:
                r, g, b = (max(0, min(255, int(round(float(v))))) for v in var.get().split())
                return f'#{r:02x}{g:02x}{b:02x}'
            except ValueError:
                return '#808080'
        button = tk.Button(cell, width=2, relief='groove', bg=colour(), activebackground=colour(),
                           state=state)

        def pick():
            chosen = colorchooser.askcolor(color=colour(), parent=self.root)[0]
            if chosen:
                var.set('{} {} {}'.format(*(int(round(c)) for c in chosen)))
        button.configure(command=pick)
        var.trace_add('write', lambda *_: button.configure(bg=colour(), activebackground=colour()))
        button.grid(row=0, column=1, sticky='w', padx=(6, 0))

    def _mark_override(self, frame, row, key):
        ttk = self.ttk
        entry = self.fields[key]
        entry['status'].configure(text='map.toml', style='Override.TLabel')

        def reset():
            self.reset.add(key)
            entry['status'].configure(text='reset on save', style='Muted.TLabel')
            button.state(['disabled'])
        button = ttk.Button(frame, text='Reset', width=6, command=reset)
        button.grid(row=row, column=2, sticky='e', padx=(6, 0), pady=(6, 0))

    # Saving -----------------------------------------------------------------
    def _value(self, entry):
        prop, raw = entry['prop'], entry['var'].get()
        if prop['kind'] == 'choice':
            labels = {label: value for value, label in prop['choices']}
            return labels[raw]
        return properties.coerce(prop, raw)

    def _save(self):
        from tkinter import messagebox
        from mapworkshop import project as projects
        overrides = {k: v for k, v in self.overrides.items() if k not in self.reset}
        try:
            for key, entry in self.fields.items():
                if entry['var'].get() == entry['initial'] or key in DERIVED:
                    continue
                prop = entry['prop']
                if prop['kind'] not in ('bool', 'choice', 'text') and not str(entry['var'].get()).strip():
                    overrides.pop(key, None)      # emptied: back to the map's own value
                    continue
                overrides[key] = self._value(entry)
                self.reset.discard(key)
            settings = {k: var.get() for k, (var, initial) in self.settings.items() if var.get() != initial}
            if 'title' in settings and not settings['title'].strip():
                raise ValueError('the title cannot be empty')
            if overrides == self.overrides and not settings:
                self.root.destroy()       # nothing changed: no save, no build
                return
            saved = projects.save_properties(self.project, overrides, settings)
        except Exception as error:
            messagebox.showerror('Map properties', f'Not saved: {error}', parent=self.root)
            return
        self.root.destroy()
        self.on_saved(saved)
