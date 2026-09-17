"""Imports"""
import tkinter as tk
from classes.table_column_class import TableColumn
from enums.finances.is_essential_enum import IsEssential


class TkTable(tk.Frame):
    def __init__(self, parent: tk.Misc,
                 columns:list[TableColumn],
                 **kwargs):
        super().__init__(parent,
                         **kwargs)
        self._columns = columns
        self._head_components = []
        self._components = []
        self._wheel_remainder = 0
        self._windowing_system = self.tk.call("tk", "windowingsystem")
        self.columnconfigure(0, weight = 1)
        self.rowconfigure(1, weight = 1)

        """Creates the head"""
        head_component = self._head = tk.Frame(self)
        head_component.grid(row=0, column=0, sticky="ew")

        for i, column in enumerate(columns):
            #Creates the component
            component = tk.Label(head_component, text = column.text,
                                 borderwidth = 2,
                                 relief = "solid")

            #Adds the component to the list
            self._head_components.append(component)

            #Packs the component
            component.grid(row = 0,
                           column = i, sticky="nsew")

        self._column_widths = [label.winfo_reqwidth()
                               for label in self._head_components]

        """Creates the body"""
        # Request a taller viewport so more rows are visible initially.
        self._canvas = tk.Canvas(self, bg = "green", highlightthickness=0,
                                 height=600)
        self._canvas.grid(row = 1,
                        column = 0,
                        sticky = "nsew")

        #Adds the scrollbar
        scrollbar = tk.Scrollbar(self, orient = "vertical",
                                 command = self._canvas.yview)
        scrollbar.grid(row = 1,
                       column = 1,
                       sticky = "ns")
        self._canvas.configure(yscrollcommand=scrollbar.set)

        # Table cells will go inside this frame.
        self._body = tk.Frame(self._canvas)
        self._body_window = self._canvas.create_window(
            (0, 0),
            window=self._body,
            anchor="nw",
        )

        # Update the scrolling bounds when the body changes size.
        self._body.bind(
            "<Configure>",
            lambda event: self._canvas.configure(
                scrollregion=self._canvas.bbox("all")
            ),
        )

        # Fill the viewport, but preserve enough width for every column.
        self._canvas.bind("<Configure>", self._resize_content)
        self._head.bind("<Configure>", self._resize_content)
        for widget in (self, self._canvas, self._body, self._head,
                       scrollbar, *self._head_components):
            self._bind_mousewheel(widget)
        self._resize_content()

    def _bind_mousewheel(self, widget):
        widget.bind("<MouseWheel>", self._on_mousewheel)
        widget.bind("<Button-4>", self._on_mousewheel)
        widget.bind("<Button-5>", self._on_mousewheel)

    def _on_mousewheel(self, event):
        if self._canvas.yview() == (0.0, 1.0):
            return "break"
        if event.num == 4:
            units = -1
        elif event.num == 5:
            units = 1
        elif self._windowing_system == "aqua":
            units = -int(event.delta)
        else:
            # Windows reports 120 per wheel notch; preserve smaller deltas.
            self._wheel_remainder += event.delta
            notches = int(self._wheel_remainder / 120)
            self._wheel_remainder -= notches * 120
            units = -notches
        if units:
            self._canvas.yview_scroll(units, "units")
        return "break"

    def _resize_content(self, event=None):
        for i, width in enumerate(self._column_widths):
            self._head.columnconfigure(i, minsize=width, weight=1)
            self._body.columnconfigure(i, minsize=width, weight=1)
        # Canvas windows do not propagate their requested width to the canvas.
        # Request the natural column width explicitly so the page can grow.
        natural_width = max(1, sum(self._column_widths))
        self._canvas.configure(width=natural_width)
        width = max(natural_width, self._canvas.winfo_width())
        self._canvas.itemconfigure(self._body_window, width=width)
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))



    def add_row(self, row:tuple):
        #Check if the length matches
        if len(row) != len(self._columns):
            raise IndexError("Length of row does not match")

        #Checks if the datatype match the columns
        for i, item in enumerate(row):
            if type(item) != self._columns[i].data_type and item is not None:
                raise TypeError(f"Datatype of {item} does not match it's column")

        # Adds the actual components
        row_index = len(self._components)
        self._components.append([])
        for i, item in enumerate(row):
            #Creates the label
            label = tk.Label(self._body, text = str(item))

            #Applies custom rules
            if type(item) == IsEssential:
                if item == IsEssential.ESSENTIAL:
                    label.config(bg = "green")
                elif item == IsEssential.NON_ESSENTIAL:
                    label.config(bg = "red")

            self._bind_mousewheel(label)
            self._column_widths[i] = max(self._column_widths[i],
                                         label.winfo_reqwidth())

            #Adds the component to the list
            self._components[row_index].append(label)

            #Packs the component
            label.grid(row = row_index,
                       column = i,
                       sticky="nsew")
        self._resize_content()







    @property
    def columns(self):
        return self._columns
