"""Imports"""
import tkinter as tk
from collections.abc import Callable
from enum import Enum, StrEnum
from math import ceil
from typing import TypeVar

from classes.general.dollar_amount_class import DollarAmount
from classes.managers.category_manager import CategoryManager
from classes.managers.location_manager import LocationManager
from classes.managers.option_manager import OptionManager
from classes.custom_tk_components.tk_option_dropdown_class import TkOptionDropdown, TkOptionLabel
from classes.table_column_class import TableColumn
from enums.finances.categories_enum import Categories
from enums.finances.is_essential_enum import IsEssential
from enums.finances.locations_enum import Locations
from tkinter import colorchooser, font, messagebox, simpledialog, ttk


_EnumValue = TypeVar("_EnumValue", bound=StrEnum)


def get_location_colors(location: Locations | None) -> tuple[str, str] | None:
    return OptionManager.colors(location)


class TkTable(tk.Frame):
    def __init__(self, parent: tk.Misc,
                 columns:list[TableColumn],
                 on_location_changed: Callable[[int, Locations], None] | None = None,
                 on_category_changed: Callable[[int, Categories], None] | None = None,
                 on_is_essential_changed: Callable[[int, IsEssential], None] | None = None,
                 stretch_column: int | None = None,
                 review_style: bool = False,
                 **kwargs):
        super().__init__(parent,
                         **kwargs)
        self._columns = columns
        self._head_components = []
        self._components = []
        self._on_location_changed = on_location_changed
        self._on_category_changed = on_category_changed
        self._on_is_essential_changed = on_is_essential_changed
        self._enum_dropdowns: dict[type[StrEnum], list[ttk.Combobox]] = {}
        self._category_dropdowns: set[ttk.Combobox] = set()
        self._location_dropdowns: set[ttk.Combobox] = set()
        self._essential_variables: dict[ttk.Combobox, tk.StringVar] = {}
        self._enum_value_providers: dict[ttk.Combobox, Callable[[], list[StrEnum]]] = {}
        self._all_enum_value_providers: dict[ttk.Combobox, Callable[[], list[StrEnum]]] = {}
        self._selected_enum_values: dict[ttk.Combobox, StrEnum | str | None] = {}
        self._enum_action_buttons: dict[ttk.Combobox, tk.Button] = {}
        self._selection_menu: tk.Menu | None = None
        self._fitted_enum_columns: dict[ttk.Combobox, int] = {}
        self._enum_cell_widths: dict[tk.Frame, int] = {}
        self._stretch_column = stretch_column
        self._review_style = review_style
        self._enum_cell_padding = 22 if review_style else 3
        self._header_canvas = None
        default_font = font.nametofont("TkDefaultFont", root=self).actual()
        self._review_font = (default_font["family"], default_font["size"])
        self._review_bold_font = (*self._review_font, "bold")
        OptionManager.subscribe(self._options_changed)
        self.bind("<Destroy>", lambda event: self._close_selection_menu() if event.widget is self else None)
        self._wheel_remainder = 0
        self._windowing_system = self.tk.call("tk", "windowingsystem")
        self.columnconfigure(0, weight = 1)
        self.rowconfigure(1, weight = 1)

        """Creates the head"""
        if review_style:
            self.configure(bg="white", highlightthickness=1, highlightbackground="#DDE4EC")
            self._header_canvas = tk.Canvas(self, bg="#EAF0F7", highlightthickness=0)
            self._header_canvas.grid(row=0, column=0, sticky="ew")
            head_component = self._head = tk.Frame(self._header_canvas)
            self._header_window = self._header_canvas.create_window((0, 0), window=head_component, anchor="nw")
            head_component.configure(bg="#DDE4EC")
        else:
            head_component = self._head = tk.Frame(self)
            head_component.grid(row=0, column=0, sticky="ew")

        for i, column in enumerate(columns):
            #Creates the component
            component = tk.Label(head_component, text = column.text,
                                 borderwidth = 2,
                                 relief = "solid")
            if review_style:
                component.configure(bg="#EAF0F7", fg="#334155", font=self._review_bold_font,
                                    borderwidth=0, relief="flat", padx=10, pady=10, anchor="w")

            #Adds the component to the list
            self._head_components.append(component)

            #Packs the component
            component.grid(row = 0, column = i, sticky="nsew", padx=(0, 1) if review_style else 0)

        self._column_widths = [label.winfo_reqwidth() + int(review_style)
                               for label in self._head_components]

        """Creates the body"""
        # Request a taller viewport so more rows are visible initially.
        self._canvas = tk.Canvas(self, bg = "white", highlightthickness=0,
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
        if review_style:
            self._body.configure(bg="#E5EAF1")
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
        if review_style:
            horizontal = ttk.Scrollbar(self, orient="horizontal", command=self._scroll_horizontal)
            horizontal.grid(row=2, column=0, sticky="ew")
            self._canvas.configure(xscrollcommand=horizontal.set)
        for widget in (self, self._canvas, self._body, self._head,
                       scrollbar, *self._head_components):
            self._bind_mousewheel(widget)
        self._resize_content()

    def create_enum_cell(self, row_index: int, enum_type: type[_EnumValue], label: str,
                         create_value: Callable[[str], _EnumValue],
                         on_changed: Callable[[int, _EnumValue | str], None] | None,
                         value: _EnumValue | str | None = None,
                         locked: bool = False,
                         empty_text: str = "None",
                         fit_column: int | None = None,
                         choices: Callable[[], list[StrEnum]] | None = None,
                         all_choices: Callable[[], list[StrEnum]] | None = None) -> tk.Frame:
        cell = tk.Frame(self._body)
        cell.columnconfigure(0, weight=1)
        if self._review_style:
            cell.rowconfigure(0, weight=1)
        dropdown = TkOptionDropdown(
            cell, state="disabled" if locked else "readonly",
            on_manage=lambda selected, action: self._manage_enum_option(dropdown, enum_type, label, selected, action),
            option_colors=lambda selected: self._enum_option_colors(dropdown, enum_type, selected),
        )
        if enum_type is Categories:
            self._category_dropdowns.add(dropdown)
        elif enum_type is Locations:
            self._location_dropdowns.add(dropdown)
        if choices is not None:
            self._enum_value_providers[dropdown] = choices
        if all_choices is not None:
            self._all_enum_value_providers[dropdown] = all_choices
        self._set_displayed_enum_value(dropdown, enum_type, value, empty_text)
        self._refresh_enum_values(dropdown, enum_type)
        dropdown.configure(postcommand=lambda: self._refresh_enum_values(dropdown, enum_type))
        dropdown.grid(row=0, column=0, sticky="nsew" if self._review_style else "ew",
                      padx=(8, 0) if self._review_style else 0, pady=5 if self._review_style else 0)
        def select_value(event):
            if str(dropdown.cget("state")) == "disabled":
                return
            members = self._enum_choices(dropdown, enum_type)
            selected = next((member for member in members if OptionManager.display(member) == dropdown.get()), None)
            if selected is not None:
                self._set_enum_value(dropdown, row_index, selected, on_changed)

        dropdown.bind("<<ComboboxSelected>>", select_value)
        add_button = tk.Button(cell, text="+", width=2, font=(self._review_font[0], self._review_font[1] + 3),
                               state="disabled" if locked else "normal",
                               command=lambda: self._add_enum_value(
                                   dropdown, row_index, enum_type, label, create_value, on_changed
                               ))
        if self._review_style:
            add_button.configure(relief="flat", borderwidth=0, cursor="hand2")
        add_button.grid(row=0, column=1, sticky="ns", padx=(6, 8) if self._review_style else (3, 0),
                        pady=5 if self._review_style else 0)
        self._enum_action_buttons[dropdown] = add_button
        add_button.configure(command=lambda: self._enum_cell_action(
            dropdown, add_button, row_index, enum_type, label, create_value, on_changed))
        self._refresh_enum_action_button(dropdown)
        self._color_enum_cell(dropdown)
        self._enum_dropdowns.setdefault(enum_type, []).append(dropdown)
        for widget in (dropdown, add_button):
            self._bind_mousewheel(widget)
        self._enum_cell_widths[cell] = dropdown.winfo_reqwidth() + add_button.winfo_reqwidth() + self._enum_cell_padding
        if fit_column is not None:
            self._fitted_enum_columns[dropdown] = fit_column
            self._fit_enum_column(dropdown, fit_column)
        return cell

    def _enum_choices(self, dropdown: ttk.Combobox, enum_type: type[StrEnum]) -> list[StrEnum]:
        provider = self._enum_value_providers.get(dropdown)
        return OptionManager.available(provider() if provider is not None else enum_type)

    def _set_displayed_enum_value(self, dropdown: ttk.Combobox, enum_type: type[StrEnum], value, empty_text: str):
        if isinstance(value, str) and not isinstance(value, StrEnum):
            provider = self._all_enum_value_providers.get(dropdown) or self._enum_value_providers.get(dropdown)
            members = [*enum_type, *(provider() if provider is not None else [])]
            value = OptionManager.resolve(members, value) or value
        self._selected_enum_values[dropdown] = value
        dropdown.set(OptionManager.display(value) if value is not None else empty_text)

    def _refresh_enum_values(self, dropdown: ttk.Combobox, enum_type: type[StrEnum]) -> None:
        dropdown.configure(values=[OptionManager.display(member) for member in self._enum_choices(dropdown, enum_type)])
        self._color_enum_cell(dropdown)
        self._refresh_enum_action_button(dropdown)
        if dropdown in self._fitted_enum_columns:
            self._fit_enum_column(dropdown, self._fitted_enum_columns[dropdown])

    def refresh_enum_cell(self, cell: tk.Frame, enum_type: type[StrEnum],
                          value: StrEnum | str | None, empty_text: str = "None",
                          locked: bool | None = None) -> None:
        dropdown = next(widget for widget in cell.winfo_children() if isinstance(widget, ttk.Combobox))
        if locked is not None:
            if locked:
                dropdown.close_dropdown()
            dropdown.configure(state="disabled" if locked else "readonly")
            add_button = next(widget for widget in cell.winfo_children() if isinstance(widget, tk.Button))
            add_button.configure(state="disabled" if locked else "normal")
        self._set_displayed_enum_value(dropdown, enum_type, value, empty_text)
        self._refresh_enum_values(dropdown, enum_type)

    def _fit_enum_column(self, dropdown: ttk.Combobox, column_index: int) -> None:
        text_font = font.Font(root=self, font=dropdown.cget("font"))
        displayed_values = (*dropdown.cget("values"), dropdown.get())
        longest = max((text_font.measure(value) for value in displayed_values), default=0)
        dropdown.configure(width=max(20, ceil(longest / max(1, text_font.measure("0"))) + 1))
        # Include the dropdown arrow and the adjacent add button in the cell width.
        cell_width = sum(widget.winfo_reqwidth() for widget in dropdown.master.winfo_children()) + self._enum_cell_padding
        self._enum_cell_widths[dropdown.master] = cell_width
        self._column_widths[column_index] = max(self._column_widths[column_index],
                                               cell_width + int(self._review_style))
        self._resize_content()

    def refresh_is_essential_cell(self, row_index: int, column_index: int,
                                  value: IsEssential | None, locked: bool) -> None:
        component = self._components[row_index][column_index]
        if not isinstance(component, ttk.Combobox):
            component.destroy()
            component = TkOptionDropdown(self._body, values=list(IsEssential), state="readonly",
                                         option_colors=lambda value: OptionManager.colors(IsEssential(value)))
            self._configure_is_essential_colors(component)
            if self._on_is_essential_changed is not None:
                component.bind("<<ComboboxSelected>>", lambda event:
                               self._on_is_essential_changed(row_index, IsEssential(event.widget.get())))
            self._bind_mousewheel(component)
            component.grid(row=row_index, column=column_index, sticky="nsew",
                           padx=(0, 1) if self._review_style else 0, pady=(0, 1) if self._review_style else 0)
            self._components[row_index][column_index] = component
            self._column_widths[column_index] = max(self._column_widths[column_index],
                                                   component.winfo_reqwidth() + int(self._review_style))
            self._resize_content()
        component.set(str(value))
        if locked:
            component.close_dropdown()
        component.configure(state="disabled" if locked else "readonly", values=list(IsEssential))

    def _set_enum_value(self, dropdown: ttk.Combobox, row_index: int, value: _EnumValue | str,
                        on_changed: Callable[[int, _EnumValue | str], None] | None) -> None:
        self._selected_enum_values[dropdown] = value
        dropdown.set(OptionManager.display(value))
        self._color_enum_cell(dropdown)
        self._refresh_enum_action_button(dropdown)
        if on_changed is not None:
            on_changed(row_index, value)

    def _color_enum_cell(self, dropdown: ttk.Combobox) -> None:
        selected = self._selected_enum_values.get(dropdown)
        value = selected if selected not in ("", str(None)) else None
        pair = OptionManager.colors(value)
        background, foreground = pair or ("#FFFFFF", "#111111")
        self._set_dropdown_colors(dropdown, background, foreground)
        dropdown.master.configure(bg=background)
        for widget in dropdown.master.winfo_children():
            if isinstance(widget, tk.Button):
                widget.configure(bg=background, fg=foreground, activebackground=background,
                                 activeforeground=foreground, disabledforeground=foreground)

    def _enum_option_colors(self, dropdown, enum_type, selected):
        member = next((member for member in self._enum_choices(dropdown, enum_type)
                       if OptionManager.display(member) == selected), None)
        return OptionManager.colors(member)

    def _configure_is_essential_colors(self, dropdown: ttk.Combobox) -> None:
        variable = tk.StringVar(master=dropdown, value=dropdown.get())
        dropdown.configure(textvariable=variable)
        # Keep the variable alive and update colors for selections and autofills.
        self._essential_variables[dropdown] = variable
        variable.trace_add("write", lambda *args: self._color_is_essential_cell(dropdown))
        self._color_is_essential_cell(dropdown)

    def _color_is_essential_cell(self, dropdown: ttk.Combobox) -> None:
        background, foreground = {
            IsEssential.ESSENTIAL: ("#008000", "#FFFFFF"),
            IsEssential.NON_ESSENTIAL: ("#FF0000", "#111111"),
            IsEssential.NOT_INCLUDED: ("#000000", "#FFFFFF"),
        }.get(dropdown.get(), ("#FFFFFF", "#111111"))
        self._set_dropdown_colors(dropdown, background, foreground)

    def _set_dropdown_colors(self, dropdown: ttk.Combobox, background: str, foreground: str) -> None:
        style = ttk.Style(self)
        style_name = f"Colored{background[1:]}.TCombobox"
        # Windows' native combobox ignores field colors. Use colorable elements
        # for these cells while leaving the application's theme intact.
        if "Colored.field" not in style.element_names():
            style.element_create("Colored.field", "from", "clam", "Combobox.field")
            style.element_create("Colored.downarrow", "from", "clam", "Combobox.downarrow")
        style.layout(style_name, [("Colored.field", {"sticky": "nswe", "children": [
            ("Colored.downarrow", {"side": "right", "sticky": "ns"}),
            ("Combobox.padding", {"sticky": "nswe", "children": [
                ("Combobox.textarea", {"sticky": "nswe"})
            ]}),
        ]})])
        for option, color in (("fieldbackground", background), ("background", background),
                              ("foreground", foreground), ("arrowcolor", foreground),
                              ("selectbackground", background), ("selectforeground", foreground)):
            style.configure(style_name, **{option: color})
            style.map(style_name, **{option: [("disabled", color), ("readonly", color)]})
        dropdown.configure(style=style_name)

    def _add_enum_value(self, dropdown: ttk.Combobox, row_index: int, enum_type: type[_EnumValue],
                        label: str, create_value: Callable[[str], _EnumValue],
                        on_changed: Callable[[int, _EnumValue | str], None] | None) -> None:
        if str(dropdown.cget("state")) == "disabled":
            return
        name = simpledialog.askstring(f"New {label.title()}", f"{label.title()} name:", parent=self)
        if name is None:
            return
        try:
            value = create_value(name)
        except (OSError, ValueError, SyntaxError) as error:
            messagebox.showerror(f"Could not create {label}", str(error), parent=self)
            return
        for enum_dropdown in self._enum_dropdowns[enum_type]:
            self._refresh_enum_values(enum_dropdown, enum_type)
        self._set_enum_value(dropdown, row_index, value, on_changed)

    def _refresh_enum_action_button(self, dropdown):
        button = self._enum_action_buttons.get(dropdown)
        if button is None:
            return
        selected = isinstance(self._selected_enum_values.get(dropdown), StrEnum)
        button.configure(text="\u22ee" if selected else "+",
                         state="normal" if selected or str(dropdown.cget("state")) != "disabled" else "disabled")

    def _enum_cell_action(self, dropdown, button, row_index, enum_type, label, create_value, on_changed):
        member = self._selected_enum_values.get(dropdown)
        if isinstance(member, StrEnum):
            dropdown.close_dropdown()
            provider = self._all_enum_value_providers.get(dropdown)
            choices = provider() if provider is not None else [*enum_type, *type(member)]
            self._show_selection_menu(button, member, label, choices)
        else:
            self._add_enum_value(dropdown, row_index, enum_type, label, create_value, on_changed)

    def _close_selection_menu(self):
        menu, self._selection_menu = self._selection_menu, None
        if menu is not None:
            try:
                menu.unpost()
                menu.grab_release()
                menu.destroy()
            except tk.TclError:
                pass

    def _show_selection_menu(self, button, member, label, choices):
        self._close_selection_menu()
        menu = self._selection_menu = tk.Menu(self, tearoff=False)
        def manage(action):
            self._close_selection_menu()
            self._manage_option(member, label, action, choices)
        for caption, action in (("Rename", "rename"), ("Edit Color", "color"), ("Delete", "delete")):
            colors = {"foreground": "#B91C1C", "activeforeground": "#B91C1C"} if action == "delete" else {}
            menu.add_command(label=caption, command=lambda action=action: self.after_idle(lambda: manage(action)), **colors)
        menu.tk_popup(button.winfo_rootx() + button.winfo_width(), button.winfo_rooty())

    def _manage_enum_option(self, dropdown: ttk.Combobox, enum_type: type[StrEnum], label: str,
                            selected: str, action: str) -> None:
        if str(dropdown.cget("state")) == "disabled":
            return
        choices = self._enum_choices(dropdown, enum_type)
        member = next((member for member in choices if OptionManager.display(member) == selected), None)
        if member is None:
            return
        provider = self._all_enum_value_providers.get(dropdown)
        self._manage_option(member, label, action, provider() if provider is not None else [*enum_type, *choices])

    def _manage_option(self, member, label, action, choices):
        try:
            if action == "rename":
                name = simpledialog.askstring(f"Rename {label.title()}", f"New {label} name:",
                                              initialvalue=OptionManager.display(member), parent=self)
                if name is not None:
                    OptionManager.rename(member, name, choices)
            elif action == "delete":
                OptionManager.delete(member)
            elif action == "color":
                color = colorchooser.askcolor(OptionManager.colors(member)[0],
                                              title=f"Color for {OptionManager.display(member)}", parent=self)[1]
                if color is not None:
                    OptionManager.set_color(member, color)
        except (OSError, ValueError) as error:
            messagebox.showerror(f"Could not {action} {label}", str(error), parent=self)

    def _options_changed(self) -> None:
        try:
            if not self.winfo_exists():
                return
            self._close_selection_menu()
            for enum_type, dropdowns in self._enum_dropdowns.items():
                for dropdown in dropdowns:
                    if dropdown.winfo_exists():
                        dropdown.close_dropdown()
                        selected = self._selected_enum_values.get(dropdown)
                        if selected is not None:
                            dropdown.set(OptionManager.display(selected))
                        self._refresh_enum_values(dropdown, enum_type)
        except tk.TclError:
            pass

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
            weight = 1 if self._stretch_column is None or i == self._stretch_column else 0
            self._head.columnconfigure(i, minsize=width, weight=weight)
            self._body.columnconfigure(i, minsize=width, weight=weight)
        # Canvas windows do not propagate their requested width to the canvas.
        # Request the natural column width explicitly so the page can grow.
        natural_width = max(1, sum(self._column_widths))
        self._canvas.configure(width=natural_width)
        width = max(natural_width, self._canvas.winfo_width())
        self._canvas.itemconfigure(self._body_window, width=width)
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        if self._header_canvas is not None:
            self._header_canvas.itemconfigure(self._header_window, width=width)
            self._header_canvas.configure(height=self._head.winfo_reqheight(),
                                          scrollregion=(0, 0, width, self._head.winfo_reqheight()))
            self._header_canvas.xview_moveto(self._canvas.xview()[0])

    def _scroll_horizontal(self, *args):
        self._canvas.xview(*args)
        self._header_canvas.xview_moveto(self._canvas.xview()[0])



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
                component = self.create_enum_cell(row_index, Locations, "location",
                                                    LocationManager.create, self._on_location_changed)
            elif data_type is Categories and item is None:
                component = self.create_enum_cell(row_index, Categories, "category",
                                                    CategoryManager.create, self._on_category_changed)
            elif issubclass(data_type, Enum) and item is None:
                component = TkOptionDropdown(self._body,
                                         values = list(self.columns[i].data_type),
                                         state="readonly", option_colors=lambda value, enum_type=data_type:
                                         OptionManager.colors(enum_type(value)))
                component.set(str(None))
                if data_type is IsEssential:
                    self._configure_is_essential_colors(component)
                    if self._on_is_essential_changed is not None:
                        component.bind("<<ComboboxSelected>>", lambda event, row_index=row_index:
                                       self._on_is_essential_changed(row_index, IsEssential(event.widget.get())))
            elif isinstance(item, (Locations, Categories)):
                label = "location" if isinstance(item, Locations) else "category"
                component = TkOptionLabel(self._body, item, colorize=True,
                                           on_manage=lambda button, member=item, label=label:
                                           self._show_selection_menu(button, member, label, list(type(member))))
            else:
                component = tk.Label(self._body, text = str(item))

            #Applies custom rules
            if isinstance(item, IsEssential) and item == IsEssential.NOT_INCLUDED:
                component.config(text="", bg="black")
            elif isinstance(item, Locations):
                colors = get_location_colors(item)
                if colors is not None:
                    component.config(bg=colors[0], fg=colors[1])
            elif isinstance(item, Categories):
                colors = CategoryManager.colors(item)
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

            if self._review_style:
                neutral = "#FFFFFF" if row_index % 2 == 0 else "#F8FAFC"
                self._body.rowconfigure(row_index, minsize=36)
                if isinstance(component, tk.Label):
                    component.configure(font=self._review_font, borderwidth=0, padx=10, pady=6)
                    if type(item) == DollarAmount:
                        component.configure(bg=neutral, fg="#15803D" if item > 0 else "#B91C1C" if item < 0 else "#334155",
                                            font=self._review_bold_font, anchor="e")
                    elif not isinstance(item, (Locations, Categories, IsEssential)) and component.cget("bg") != "black":
                        component.configure(bg=neutral, anchor="w")
                        if type(component) is tk.Label:
                            component.configure(fg="#334155")
                elif isinstance(component, tk.Button):
                    component.configure(relief="flat", borderwidth=0, padx=10, pady=6)
                elif isinstance(component, tk.Checkbutton):
                    component.configure(relief="flat", borderwidth=0, highlightthickness=0, padx=10, pady=6)


            self._bind_mousewheel(component)
            self._column_widths[i] = max(self._column_widths[i],
                                         self._enum_cell_widths.get(component, component.winfo_reqwidth())
                                         + int(self._review_style))

            #Adds the component to the list
            self._components[row_index].append(component)

            #Packs the component
            component.grid(in_=self._body,
                       row = row_index,
                       column = i,
                       sticky="nsew", padx=(0, 1) if self._review_style else 0,
                       pady=(0, 1) if self._review_style else 0)
        self._resize_content()







    @property
    def columns(self):
        return self._columns
