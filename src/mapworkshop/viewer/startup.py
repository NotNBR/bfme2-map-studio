"""The viewer's map picker, shown before loading a map on an unnamed launch."""
from pathlib import Path

from mapworkshop import project
from mapworkshop.config import setting


def choose_map():
    """Return a selected project id or .map path, or None when closed."""
    import queue
    import threading
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    window = tk.Tk()
    window.title('Map Workshop')
    window.geometry('760x500')
    window.minsize(580, 360)
    result = None
    projects = project.projects()
    frame = ttk.Frame(window, padding=20)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='Open a map', font=('Segoe UI', 18)).pack(anchor='w')
    ttk.Label(frame, text='Choose a project, or browse for a .map file.').pack(anchor='w', pady=(4, 14))
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
    building = False
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
        open_button.configure(state='normal' if p is not None and not building else 'disabled')
        if p is not None and not building:
            status.set(str(p.map_file) if p.map_file.is_file() else
                       f'{p.title} needs a build before opening. Select Open to build it.')
        return p

    def open_selected(event=None):
        nonlocal building
        if building:
            return
        p = selected()
        if p is None:
            return
        if p.map_file.is_file():
            finish(p.id)
            return
        if not messagebox.askokcancel('Build map before opening',
                                     f'{p.title} needs to be built before it can open.\n\nBuild it now and open it?',
                                     parent=window):
            return
        building = True
        open_button.configure(state='disabled')
        cancel_button.configure(state='disabled')
        status.set(f'Building {p.title}...')
        updates = queue.SimpleQueue()
        last_line = ''

        def work():
            try:
                code = project.run(p, on_line=lambda line: updates.put(('line', line)))
                updates.put(('done', code))
            except Exception as error:
                updates.put(('error', str(error)))

        def poll():
            nonlocal building, last_line
            while not updates.empty():
                kind, value = updates.get_nowait()
                if kind == 'line':
                    if value.strip():
                        last_line = value.strip()
                        status.set(last_line[:160])
                else:
                    if kind == 'done' and value == 0 and p.map_file.is_file():
                        finish(p.id)
                        return
                    building = False
                    cancel_button.configure(state='normal')
                    selected()
                    detail = value if kind == 'error' else last_line or f'Build exited with code {value}.'
                    status.set(f'{p.title}: build failed. {detail}')
                    messagebox.showerror('Map build failed',
                                         f'{p.title} could not be built.\n\n{detail}', parent=window)
                    return
            window.after(100, poll)

        threading.Thread(target=work, daemon=True).start()
        window.after(100, poll)

    def browse():
        if building:
            return
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
    ttk.Button(buttons, text='Grass Lab', command=lambda: finish('@grass-lab') if not building else None).pack(side='left', padx=8)
    open_button = ttk.Button(buttons, text='Open', command=open_selected, state='disabled')
    open_button.pack(side='right')
    cancel_button = ttk.Button(buttons, text='Cancel', command=finish)
    cancel_button.pack(side='right', padx=8)
    table.bind('<<TreeviewSelect>>', selected)
    table.bind('<Double-1>', open_selected)
    table.bind('<Return>', open_selected)
    window.bind('<Escape>', lambda event: finish() if not building else None)
    window.protocol('WM_DELETE_WINDOW', lambda: finish() if not building else None)
    last = setting('last_map')
    if last in by_id:
        table.selection_set(last)
        table.see(last)
        selected()
    table.focus_set()
    window.mainloop()
    return result
