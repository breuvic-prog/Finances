"""Imports"""
import tkinter as tk
from collections.abc import Callable
from enum import Enum, StrEnum
from typing import TypeVar

from classes.general.dollar_amount_class import DollarAmount
from classes.managers.category_manager import CategoryManager
from classes.managers.location_manager import LocationManager
from classes.table_column_class import TableColumn
from enums.finances.categories_enum import Categories
from enums.finances.is_essential_enum import IsEssential
from enums.finances.locations_enum import Locations
from tkinter import messagebox, simpledialog, ttk


_EnumValue = TypeVar("_EnumValue", bound=StrEnum)


# Background and text colors inspired by each location's branding.
_LOCATION_COLORS: dict[Locations, tuple[str, str]] = {
    Locations.WALMART: ("#0053E2", "#FFFFFF"),
    Locations.AMAZON: ("#FF9900", "#111111"),
    Locations.KWIK_TRIP: ("#D71920", "#FFFFFF"),
    Locations.PLAYSTATION: ("#003791", "#FFFFFF"),
    Locations.VENDING_MACHINE: ("#455A64", "#FFFFFF"),
    Locations.MICROSOFT: ("#737373", "#FFFFFF"),
    Locations.APPLE: ("#A2AAAD", "#111111"),
    Locations.DOLLAR_GENERAL: ("#FFF200", "#111111"),
    Locations.FREEDOM_BANK: ("#006747", "#FFFFFF"),
    Locations.FIRST_SECURITY_BANK: ("#1D3557", "#FFFFFF"),
    Locations.HUCKLEBERRYS: ("#7B2D59", "#FFFFFF"),
    Locations.CULVERS: ("#005696", "#FFFFFF"),
    Locations.PRAIRIE_CINEMA: ("#800020", "#FFFFFF"),
}


class TkTable(tk.Frame):
    def __init__(self, parent: tk.Misc,
                 columns:list[TableColumn],
                 on_location_changed: Callable[[int, Locations], None] | None = None,
                 on_category_changed: Callable[[int, Categories], None] | None = None,
                 **kwargs):
        super().__init__(parent,
                         **kwargs)
        self._columns = columns
        self._head_components = []
        self._components = []
        self._on_location_changed = on_location_changed
        self._on_category_changed = on_category_changed
        self._enum_dropdowns: dict[type[StrEnum], list[ttk.Combobox]] = {}
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

    def _create_enum_cell(self, row_index: int, enum_type: type[_EnumValue], label: str,
                          create_value: Callable[[str], _EnumValue],
                          on_changed: Callable[[int, _EnumValue], None] | None) -> tk.Frame:
        cell = tk.Frame(self._body)
        cell.columnconfigure(0, weight=1)
        dropdown = ttk.Combobox(cell, values=list(enum_type), state="readonly")
        dropdown.set(str(None))
        dropdown.configure(postcommand=lambda: dropdown.configure(values=list(enum_type)))
        dropdown.grid(row=0, column=0, sticky="ew")
        dropdown.bind("<<ComboboxSelected>>", lambda event: self._set_enum_value(
            dropdown, row_index, enum_type(dropdown.get()), on_changed
        ))
        add_button = tk.Button(cell, text="+", width=2,
                               command=lambda: self._add_enum_value(
                                   dropdown, row_index, enum_type, label, create_value, on_changed
                               ))
        add_button.grid(row=0, column=1, sticky="ns", padx=(3, 0))
        self._enum_dropdowns.setdefault(enum_type, []).append(dropdown)
        for widget in (dropdown, add_button):
            self._bind_mousewheel(widget)
        return cell

    def _set_enum_value(self, dropdown: ttk.Combobox, row_index: int, value: _EnumValue,
                        on_changed: Callable[[int, _EnumValue], None] | None) -> None:
        dropdown.set(value.value)
        if on_changed is not None:
            on_changed(row_index, value)

    def _add_enum_value(self, dropdown: ttk.Combobox, row_index: int, enum_type: type[_EnumValue],
                        label: str, create_value: Callable[[str], _EnumValue],
                        on_changed: Callable[[int, _EnumValue], None] | None) -> None:
        name = simpledialog.askstring(f"New {label.title()}", f"{label.title()} name:", parent=self)
        if name is None:
            return
        try:
            value = create_value(name)
        except (OSError, ValueError, SyntaxError) as error:
            messagebox.showerror(f"Could not create {label}", str(error), parent=self)
            return
        for enum_dropdown in self._enum_dropdowns[enum_type]:
            enum_dropdown.configure(values=list(enum_type))
        self._set_enum_value(dropdown, row_index, value, on_changed)

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
            if item is not None and not isinstance(item, self._columns[i].data_type):
                raise TypeError(f"Datatype of {item} does not match it's column")

        # Adds the actual components
        row_index = len(self._components)
        self._components.append([])
        for i, item in enumerate(row):
            #Creates the label
            data_type = self._columns[i].data_type

            if isinstance(item, tk.Widget):
                component = item
            elif issubclass(data_type, tk.Widget) and item is None:
                component = tk.Label(self._body, text="")
            elif data_type is Locations and item is None:
                component = self._create_enum_cell(row_index, Locations, "location",
                                                    LocationManager.create, self._on_location_changed)
            elif data_type is Categories and item is None:
                component = self._create_enum_cell(row_index, Categories, "category",
                                                    CategoryManager.create, self._on_category_changed)
            elif issubclass(data_type, Enum) and item is None:
                component = ttk.Combobox(self._body,
                                         values = list(self.columns[i].data_type),
                                         state="readonly")
                component.set(str(None))
            else:
                component = tk.Label(self._body, text = str(item))

            #Applies custom rules
            if isinstance(item, str) and item.casefold() == "not included":
                component.config(text="", bg="black")
            elif isinstance(item, Locations):
                colors = _LOCATION_COLORS.get(item)
                if colors is not None:
                    component.config(bg=colors[0], fg=colors[1])
            elif type(item) == IsEssential:
                if item == IsEssential.ESSENTIAL:
                    component.config(bg = "green")
                elif item == IsEssential.NON_ESSENTIAL:
                    component.config(bg = "red")
            elif type(item) == DollarAmount:
                if item > 0:
                    component.config(bg = "green")
                elif item < 0:
                    component.config(bg = "red")


            self._bind_mousewheel(component)
            self._column_widths[i] = max(self._column_widths[i],
                                         component.winfo_reqwidth())

            #Adds the component to the list
            self._components[row_index].append(component)

            #Packs the component
            component.grid(in_=self._body,
                       row = row_index,
                       column = i,
                       sticky="nsew")
        self._resize_content()







    @property
    def columns(self):
        return self._columns
