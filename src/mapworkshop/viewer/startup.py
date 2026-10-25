"""The viewer's map picker, shown before loading a map on an unnamed launch."""
from pathlib import Path

from mapworkshop import project
from mapworkshop.config import setting


def choose_map():
    """Return a selected project id or .map path, or None when closed."""
    import tkinter as tk
    from tkinter import filedialog, ttk

    window = tk.Tk()
    window.title('Map Workshop')
    window.geometry('760x500')
    window.minsize(580, 360)
    result = None
    projects = project.projects()
    frame = ttk.Frame(window, padding=20)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='Open a map', font=('Segoe UI', 18)).pack(anchor='w')
    ttk.Label(frame, text='Choose a built project, or browse for a .map file.').pack(anchor='w', pady=(4, 14))
    table_frame = ttk.Frame(frame)
    table_frame.pack(fill='both', expand=True)
    table = ttk.Treeview(table_frame, columns=('title', 'status'), show='headings', selectmode='browse')
    table.heading('title', text='Map project')
    table.heading('status', text='Status')
    table.column('title', width=490)
    table.column('status', width=130, stretch=False)
    scroll = ttk.Scrollbar(table_frame, orient='vertical', command=table.yview)
    table.configure(yscrollcommand=scroll.set)
    table.pack(side='left', fill='both', expand=True)
    scroll.pack(side='right', fill='y')
    by_id = {p.id: p for p in projects}
    for p in projects:
        table.insert('', 'end', iid=p.id, values=(p.title, 'Ready' if p.map_file.is_file() else 'Not built'))
    status = tk.StringVar(value='You can also open maps outside the workshop projects.')
    ttk.Label(frame, textvariable=status, wraplength=680).pack(anchor='w', pady=(12, 8))
    buttons = ttk.Frame(frame)
    buttons.pack(fill='x')

    def finish(value=None):
        nonlocal result
        result = value
        window.destroy()

    def selected(event=None):
        selection = table.selection()
        p = by_id.get(selection[0]) if selection else None
        ready = p is not None and p.map_file.is_file()
        open_button.configure(state='normal' if ready else 'disabled')
        if p is not None:
            status.set(str(p.map_file) if ready else f'Build this project first: mw build {p.id}')
        return p if ready else None

    def open_selected(event=None):
        p = selected()
        if p is not None:
            finish(p.id)

    def browse():
        previous = setting('viewer_map_file')
        path = filedialog.askopenfilename(parent=window, title='Open map',
                                         initialdir=str(Path(previous).parent) if previous else None,
                                         filetypes=[('BFME maps', '*.map')])
        if path:
            if Path(path).is_file() and Path(path).suffix.lower() == '.map':
                finish(path)
            else:
                status.set('Choose an existing .map file.')

    ttk.Button(buttons, text='Browse for map...', command=browse).pack(side='left')
    open_button = ttk.Button(buttons, text='Open', command=open_selected, state='disabled')
    open_button.pack(side='right')
    ttk.Button(buttons, text='Cancel', command=finish).pack(side='right', padx=8)
    table.bind('<<TreeviewSelect>>', selected)
    table.bind('<Double-1>', open_selected)
    table.bind('<Return>', open_selected)
    window.bind('<Escape>', lambda event: finish())
    window.protocol('WM_DELETE_WINDOW', finish)
    last = setting('last_map')
    if last in by_id:
        table.selection_set(last)
        table.see(last)
        selected()
    table.focus_set()
    window.mainloop()
    return result
