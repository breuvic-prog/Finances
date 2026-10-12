"""A combobox whose opened list includes a menu beside each option."""

from collections.abc import Callable
from math import ceil
import tkinter as tk
from tkinter import font, ttk

from classes.managers.option_manager import OptionManager


class TkOptionLabel(tk.Label):
    def __init__(self, parent: tk.Misc, value, prefix: str = "", colorize: bool = False,
                 on_manage: Callable[[tk.Button], None] | None = None, **kwargs):
        self._option_value, self._prefix = value, prefix
        self._colorize = colorize
        self._manage_button = None
        super().__init__(parent, text=prefix + OptionManager.display(value), **kwargs)
        if on_manage is not None:
            self._manage_button = tk.Button(self, text="\u22ee", width=2, relief="flat", borderwidth=0,
                                            cursor="hand2", command=lambda: on_manage(self._manage_button))
            self._manage_button.place(relx=1, x=-2, rely=.5, anchor="e")
        self._refresh_option()
        OptionManager.subscribe(self._refresh_option)

    def _refresh_option(self):
        try:
            if self.winfo_exists():
                self.configure(text=self._prefix + OptionManager.display(self._option_value))
                if self._colorize and (colors := OptionManager.colors(self._option_value)):
                    self.configure(bg=colors[0], fg=colors[1])
                if self._manage_button is not None:
                    text_font = font.Font(root=self, font=self.cget("font"))
                    self.configure(anchor="w", width=ceil((text_font.measure(self.cget("text")) + 36)
                                                           / max(1, text_font.measure("0"))))
                    self._manage_button.configure(bg=self.cget("bg"), fg=self.cget("fg"),
                                                  activebackground=self.cget("bg"), activeforeground=self.cget("fg"),
                                                  font=(text_font.actual("family"), text_font.actual("size") + 3))
        except tk.TclError:
            pass


class TkOptionDropdown(ttk.Combobox):
    def __init__(self, parent: tk.Misc, on_manage: Callable[[str, str], None] | None = None,
                 option_colors: Callable[[str], tuple[str, str] | None] | None = None, **kwargs):
        super().__init__(parent, **kwargs)
        self._on_manage = on_manage
        self._option_colors = option_colors
        self._popup: tk.Toplevel | None = None
        self._menu: tk.Menu | None = None
        self._menu_open = False
        self._focus_job = None
        self._list_canvas = None
        self._outside_binding = None
        self._choice_buttons: list[tk.Button] = []
        self._menu_buttons: list[tk.Button] = []
        self.bind("<Button-1>", self._open_dropdown)
        for key in ("<Down>", "<Alt-Down>", "<F4>", "<space>"):
            self.bind(key, self._open_dropdown)
        self.bind("<Escape>", lambda event: self.close_dropdown())
        self.bind("<Destroy>", self._destroy_dropdown)

    def _open_dropdown(self, event=None):
        if str(self.cget("state")) == "disabled":
            self.close_dropdown()
            return "break"
        if self._popup is not None and self._popup.winfo_exists():
            self.close_dropdown()
            return "break"
        postcommand = self.cget("postcommand")
        if postcommand:
            self.tk.call(postcommand)
        values = self.cget("values")
        text_font = font.Font(root=self, font=self.cget("font"))
        width = min(self.winfo_screenwidth() - 16,
                    max(self.winfo_width(), min(600, max((text_font.measure(value) for value in values), default=180) + 70)))
        popup = self._popup = tk.Toplevel(self)
        popup.withdraw()
        popup.overrideredirect(True)
        popup.transient(self.winfo_toplevel())
        popup.configure(bg="#DDE4EC")
        popup.columnconfigure(0, weight=1)
        popup.rowconfigure(0, weight=1)
        canvas = tk.Canvas(popup, bg="white", highlightthickness=0, width=width - 18)
        self._list_canvas = canvas
        canvas.grid(row=0, column=0, sticky="nsew", padx=(1, 0), pady=1)
        scrollbar = ttk.Scrollbar(popup, orient="vertical", command=canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 1), pady=1)
        canvas.configure(yscrollcommand=scrollbar.set)
        body = tk.Frame(canvas, bg="white")
        canvas.create_window((0, 0), window=body, anchor="nw", width=width - 18)
        body.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
        self._choice_buttons, self._menu_buttons = [], []
        for value in values:
            colors = self._option_colors(value) if self._option_colors is not None else None
            background, foreground = colors or ("white", "#334155")
            row = tk.Frame(body, bg=background)
            row.pack(fill="x")
            row.columnconfigure(0, weight=1)
            selected = value == self.get()
            if selected and colors is None:
                background = "#E5EFFB"
            choice = tk.Button(row, text=value, anchor="w", justify="left", wraplength=max(100, width - 76),
                               bg=background, fg=foreground, activebackground=background, activeforeground=foreground,
                               relief="flat", borderwidth=0, padx=12, pady=8, cursor="hand2",
                               font=(text_font.actual("family"), text_font.actual("size"), "bold" if selected else "normal"),
                               state="disabled" if str(self.cget("state")) == "disabled" else "normal",
                               disabledforeground="#64748B",
                               command=lambda value=value: self._select_option(value))
            choice.grid(row=0, column=0, sticky="nsew")
            controls = [row, choice]
            if self._on_manage is not None:
                dots = tk.Button(row, text="\u22ee", bg=background, fg=foreground, activebackground=background,
                                 activeforeground=foreground, relief="flat", borderwidth=0, width=2, cursor="hand2",
                                 font=(text_font.actual("family"), text_font.actual("size") + 3))
                dots.configure(command=lambda value=value, dots=dots: self._show_option_menu(value, dots))
                dots.grid(row=0, column=1, sticky="ns", padx=(0, 4))
                self._menu_buttons.append(dots)
                controls.append(dots)
            for widget in controls:
                widget.bind("<MouseWheel>", lambda event: self._scroll_list(canvas, event))
                widget.bind("<Button-4>", lambda event: canvas.yview_scroll(-1, "units"))
                widget.bind("<Button-5>", lambda event: canvas.yview_scroll(1, "units"))
            choice.bind("<Return>", lambda event, value=value: self._select_option(value))
            self._choice_buttons.append(choice)
        if not values:
            tk.Label(body, text="Use + to add an option.", bg="white", fg="#64748B", padx=12, pady=12).pack(fill="x")
        body.update_idletasks()
        height = min(320, body.winfo_reqheight() + 2)
        x = min(self.winfo_rootx(), self.winfo_screenwidth() - width - 8)
        y = self.winfo_rooty() + self.winfo_height()
        if y + height > self.winfo_screenheight() - 8:
            y = max(0, self.winfo_rooty() - height)
        popup.geometry(f"{width}x{height}+{max(0, x)}+{y}")
        popup.bind("<Escape>", lambda event: self.close_dropdown())
        popup.bind("<FocusOut>", lambda event: self._schedule_focus_check())
        popup.bind("<Down>", lambda event: self._move_focus(1))
        popup.bind("<Up>", lambda event: self._move_focus(-1))
        popup.bind("<Return>", self._confirm_focus)
        popup.deiconify()
        popup.lift()
        popup.focus_set()
        owner = self.winfo_toplevel()
        binding = owner.bind("<ButtonPress-1>", self._outside_click, add="+")
        self._outside_binding = (owner, binding)
        return "break"

    def _outside_click(self, event):
        if event.widget is self:
            return
        for window in (self._popup, self._menu):
            if window is not None and window.winfo_exists():
                if (window.winfo_rootx() <= event.x_root < window.winfo_rootx() + window.winfo_width()
                        and window.winfo_rooty() <= event.y_root < window.winfo_rooty() + window.winfo_height()):
                    return
        self.close_dropdown()

    def _select_option(self, value: str):
        self.close_dropdown()
        if str(self.cget("state")) != "disabled":
            self.set(value)
            self.event_generate("<<ComboboxSelected>>")
            if self.winfo_exists():
                self.focus_set()
        return "break"

    @staticmethod
    def _scroll_list(canvas, event):
        if event.delta:
            canvas.yview_scroll(-int(event.delta / 120), "units")
        return "break"

    def _move_focus(self, direction):
        if self._choice_buttons:
            focused = self.focus_get()
            index = self._choice_buttons.index(focused) if focused in self._choice_buttons else (-1 if direction > 0 else 0)
            choice = self._choice_buttons[(index + direction) % len(self._choice_buttons)]
            choice.focus_set()
            canvas = self._list_canvas
            bounds = canvas.bbox("all")
            if bounds and bounds[3]:
                top = choice.master.winfo_y()
                bottom = top + choice.master.winfo_height()
                visible_top = canvas.canvasy(0)
                if top < visible_top:
                    canvas.yview_moveto(top / bounds[3])
                elif bottom > visible_top + canvas.winfo_height():
                    canvas.yview_moveto((bottom - canvas.winfo_height()) / bounds[3])
        return "break"

    def _confirm_focus(self, event=None):
        focused = self.focus_get()
        if focused in self._menu_buttons:
            focused.invoke()
        elif focused in self._choice_buttons:
            focused.invoke()
        elif self._choice_buttons:
            selected = next((button for button in self._choice_buttons if button.cget("text") == self.get()),
                            self._choice_buttons[0])
            selected.invoke()
        return "break"

    def _show_option_menu(self, value: str, dots: tk.Button):
        self._menu_open = True
        menu = self._menu = tk.Menu(self._popup, tearoff=False)
        menu.add_command(label="Rename", command=lambda: self._manage(value, "rename"))
        menu.add_command(label="Edit Color", command=lambda: self._manage(value, "color"))
        menu.add_command(label="Delete", foreground="#B91C1C", activeforeground="#B91C1C",
                         command=lambda: self._manage(value, "delete"))
        menu.bind("<Unmap>", self._menu_closed)
        menu.tk_popup(dots.winfo_rootx() + dots.winfo_width(), dots.winfo_rooty())

    def _menu_closed(self, event=None):
        self._menu_open = False
        self._schedule_focus_check()

    def _manage(self, value: str, action: str):
        # Let the native Windows menu finish invoking the colored entry before destroying it.
        self.after_idle(lambda: self._finish_manage(value, action))

    def _finish_manage(self, value: str, action: str):
        self.close_dropdown()
        if str(self.cget("state")) != "disabled" and self._on_manage is not None:
            self._on_manage(value, action)

    def _check_focus(self):
        self._focus_job = None
        if self._popup is None or self._menu_open:
            return
        try:
            focused = self.focus_get()
            if focused is None or (focused is not self and not str(focused).startswith(str(self._popup) + ".")
                                    and focused is not self._popup):
                self.close_dropdown()
        except tk.TclError:
            self.close_dropdown()

    def _schedule_focus_check(self):
        if self._popup is not None:
            if self._focus_job is not None:
                self.after_cancel(self._focus_job)
            self._focus_job = self.after_idle(self._check_focus)

    def _destroy_dropdown(self, event):
        self.close_dropdown()

    def close_dropdown(self):
        if self._outside_binding is not None:
            owner, binding = self._outside_binding
            self._outside_binding = None
            try:
                owner.unbind("<ButtonPress-1>", binding)
            except tk.TclError:
                pass
        if self._focus_job is not None:
            self.after_cancel(self._focus_job)
            self._focus_job = None
        menu, popup = self._menu, self._popup
        self._menu = self._popup = None
        if menu is not None:
            try:
                menu.unpost()
                menu.grab_release()
                menu.destroy()
            except tk.TclError:
                pass
        if popup is not None:
            popup.destroy()
        self._choice_buttons, self._menu_buttons = [], []
        self._list_canvas = None
        self._menu_open = False
        return "break"
