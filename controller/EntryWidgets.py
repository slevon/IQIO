from tkinter import ttk
from tkinter.ttk import Label, Button
import tkinter as tk

class EntryMixin:
    """Add label, widget and callback function."""

    def add_widget(self, root, label, widget, kwargs):
        """Add widget with optional label."""
        if label == '':
            super(widget, self).__init__(root, **kwargs)
            self.grid()
        else:
            frame = ttk.Frame(root, relief='solid', borderwidth=d)
            frame.grid(sticky='e')
            ttk.Label(frame, text=label).grid()
            super(widget, self).__init__(frame, **kwargs)
            self.grid(row=0, column=1)

    def add_cmd(self, cmd):
        # if cmd is a string store it, and replace it 'cb' callback function
        if isinstance(cmd, str):
            self.cmd = cmd
            cmd = self.cb
        self.bind('<Return>', lambda event: cmd(self, event))

    def cb(self, item=None, event=None):
        """Execute the cmd string in the widget context."""
        exec(self.cmd)


class Entry(ttk.Entry, EntryMixin):
    """Create an Entry object with label and callback."""

    def __init__(self,  label='', cmd='', val='',  **kwargs):
        self.var = tk.StringVar()
        self.var.set(val)
        self.add_widget(label, Entry, kwargs)
        self['textvariable'] = self.var
        self.add_cmd(cmd)

class Combobox(ttk.Combobox, EntryMixin):
    """Create a Combobox with label and callback."""

    def __init__(self, label='', values='', cmd='', val=0, **kwargs):
        if isinstance(values, str):
            values = values.split(';')

        self.var = tk.StringVar()
        self.var.set(values[val])

        self.add_widget(label, Combobox, kwargs)
        self['textvariable'] = self.var
        self['values'] = values

        self.add_cmd(cmd)
        self.bind('<<ComboboxSelected>>', self.cb)

class Spinbox(ttk.Spinbox, EntryMixin):
    """Create a Spinbox with label and callback."""

    def __init__(self, label='', cmd='', values='', val=0, **kwargs):
        if isinstance(values, str):
            values = values.split(';')
            if len(values) > 1:
                val = values[val]

        self.var = tk.StringVar(value=val)

        self.add_widget(label, Spinbox, kwargs)
        self['textvariable'] = self.var

        if len(values) > 1:
            self['values'] = values
        self.add_cmd(cmd)

class Scale(ttk.Scale):
    """Create a Spinbox with label and callback."""

    def __init__(self, root,label='', **kwargs):
        if not 'length' in kwargs:
            kwargs.update({'length': 200})

        super().__init__(root, **kwargs)
        frame = ttk.Frame(root, relief='solid', borderwidth=0)
        frame.grid(sticky='e')
        ttk.Label(frame, text=label).grid()
        self.grid(row=0, column=1)


class EntryScale(ttk.Scale):
    """ ttk.Scale sublass that limits the precision of values. """

    def __init__(self,root,text, *args, **kwargs):
        super(EntryScale, self).__init__(*args, **kwargs)
        frame = ttk.Frame( relief='solid', borderwidth=0)
        frame.grid(sticky='e')
        ttk.Label(frame, text=text).grid()
        self.grid(row=0, column=1)
        #super(EntryScale, self).__init__(*args, command=self._value_changed, **kwargs)

    #def _value_changed(self, newvalue):
    #    newvalue = round(float(newvalue), self.precision)
    #    self.winfo_toplevel().globalsetvar(self.cget('variable'), (newvalue))
    #    self.chain(newvalue)  # Call user specified function.


