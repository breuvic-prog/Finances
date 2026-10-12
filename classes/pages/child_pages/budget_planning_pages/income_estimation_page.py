"""Manage recurring hourly jobs and estimate earnings for the next calendar month."""

import tkinter as tk
from collections.abc import Callable
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from tkinter import font, messagebox, ttk

from classes.budget_job_class import BudgetJob, WEEKDAYS
from classes.work_shift_class import WorkShift
from classes.custom_tk_components.tk_document_input_class import BACKGROUND, BORDER, INK, MUTED, document_button
from classes.custom_tk_components.tk_table_class import TkTable
from classes.custom_tk_components.tk_food_plan_editor import FoodPlanEditor
from classes.food_consumption_class import validate_food_plan
from classes.managers.budget_jobs_manager import BudgetJobsManager
from classes.managers.day_off_foods_manager import DayOffFoodsManager
from classes.managers.grocery_catalog_manager import GroceryCatalogManager
from classes.managers.prepared_foods_manager import PreparedFoodsManager
from classes.managers.income_estimation_manager import IncomeEstimationManager, IncomeEstimate
from classes.pages.leaf_page_class import LeafPage
from classes.table_column_class import TableColumn


def _money(value) -> str:
    return f"${value:,.2f}"


def _hours(value) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _work_hours(value) -> str:
    return _hours(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class IncomeEstimationPage(LeafPage):
    def __init__(self, parent_root: tk.Misc, parent_next_method: Callable,
                 jobs_manager: BudgetJobsManager | None = None,
                 today: Callable[[], date] = date.today, on_back: Callable | None = None,
                 catalog_manager: GroceryCatalogManager | None = None,
                 day_off_foods_manager: DayOffFoodsManager | None = None,
                 foods_manager: PreparedFoodsManager | None = None):
        self._jobs_manager = jobs_manager if jobs_manager is not None else BudgetJobsManager()
        self._catalog_manager = catalog_manager if catalog_manager is not None else GroceryCatalogManager()
        self._day_off_foods_manager = day_off_foods_manager if day_off_foods_manager is not None else DayOffFoodsManager()
        self._foods_manager = foods_manager if foods_manager is not None else PreparedFoodsManager()
        self._food_editor = None
        self._editor_foods = ()
        self._on_back = on_back
        self._today = today
        self._jobs: list[BudgetJob] = []
        self._estimate = IncomeEstimationManager.estimate([], self._today())
        self._load_error = None
        self._job_table = None
        self._editor = None
        self._reload_jobs()
        super().__init__(parent_root, parent_next_method)

    @property
    def income_estimate(self) -> IncomeEstimate:
        return self._estimate

    def activate(self):
        super().activate()
        self._reload_jobs()
        self._refresh()

    def _reload_jobs(self):
        try:
            self._jobs = self._jobs_manager.load()
        except (OSError, ValueError) as error:
            self._load_error = str(error)
        else:
            self._load_error = None

    def _setup_components(self):
        self._root.configure(bg=BACKGROUND)
        self._root.columnconfigure(0, weight=1)
        self._root.rowconfigure(3, weight=1)
        default = font.nametofont("TkDefaultFont", root=self._root).actual()
        self._normal_font = (default["family"], default["size"])
        self._bold_font = (*self._normal_font, "bold")
        header = tk.Frame(self._root, bg=BACKGROUND)
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 14))
        header.columnconfigure(0, weight=1)
        tk.Label(header, text="BUDGET PLANNING · STEP 4", bg=BACKGROUND, fg=MUTED,
                 anchor="w", font=self._bold_font).grid(row=0, column=0, sticky="w")
        tk.Label(header, text="Income Estimation", bg=BACKGROUND, fg=INK, anchor="w",
                 font=(default["family"], default["size"] + 7, "bold")).grid(row=1, column=0, sticky="ew", pady=(5, 0))
        self._month_label = tk.Label(header, bg="#E5EFFB", fg="#234E78", padx=12, pady=8,
                                    font=self._bold_font)
        self._month_label.grid(row=1, column=1, sticky="e", padx=(12, 0))
        self._subtitle = tk.Label(header, bg=BACKGROUND, fg=MUTED, anchor="w", justify="left")
        self._subtitle.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        header.bind("<Configure>", lambda event: self._subtitle.configure(wraplength=max(100, event.width)))

        totals = tk.Frame(self._root, bg=BACKGROUND)
        totals.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 16))
        self._total_labels = {}
        for index, (key, title, background, foreground) in enumerate((
                ("gross", "Estimated gross income", "white", INK),
                ("tax", "Estimated tax", "#FFF1F2", "#BE123C"),
                ("take_home", "Estimated take-home pay", "#ECFDF5", "#15803D"))):
            totals.columnconfigure(index, weight=1, uniform="income_totals")
            card = tk.Frame(totals, bg=background, highlightthickness=1, highlightbackground=BORDER)
            card.grid(row=0, column=index, sticky="nsew", padx=(0, 10) if index < 2 else 0)
            tk.Label(card, text=title, bg=background, fg=MUTED, anchor="w").pack(fill="x", padx=14, pady=(12, 6))
            value = tk.Label(card, bg=background, fg=foreground, anchor="w",
                             font=(default["family"], default["size"] + 7, "bold"))
            value.pack(fill="x", padx=14, pady=(0, 14))
            self._total_labels[key] = value

        toolbar = tk.Frame(self._root, bg=BACKGROUND)
        toolbar.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 10))
        toolbar.columnconfigure(0, weight=1)
        self._jobs_heading = tk.Label(toolbar, bg=BACKGROUND, fg=INK, anchor="w", font=self._bold_font)
        self._jobs_heading.grid(row=0, column=0, sticky="w")
        self._day_off_foods_button = document_button(toolbar, "Food for Days Off", self._show_day_off_foods)
        self._day_off_foods_button.grid(row=0, column=1, padx=(8, 8))
        document_button(toolbar, "Reload Jobs", self._reload_and_refresh).grid(row=0, column=2, padx=(0, 8))
        self._add_button = document_button(toolbar, "+ Add Job", self._show_job_editor, primary=True)
        self._add_button.grid(row=0, column=3)

        footer = tk.Frame(self._root, bg=BACKGROUND)
        footer.grid(row=4, column=0, sticky="ew", padx=20, pady=(12, 18))
        self._status = tk.Label(footer, bg=BACKGROUND, fg=MUTED, anchor="w", justify="left")
        self._status.pack(fill="x")
        tk.Label(footer, text="Schedules repeat weekly. Paid hours exclude unpaid breaks; tax is a percentage of gross pay.",
                 bg=BACKGROUND, fg=MUTED, anchor="w", justify="left").pack(fill="x", pady=(6, 0))
        tk.Label(footer, text="Shift and day-off food plans are extras added to your Daily Use baseline.",
                 bg=BACKGROUND, fg=MUTED, anchor="w", justify="left").pack(fill="x", pady=(6, 0))
        actions = tk.Frame(footer, bg=BACKGROUND)
        actions.pack(fill="x", pady=(12, 0))
        actions.columnconfigure(1, weight=1)
        if self._on_back is not None:
            self._back_button = document_button(actions, "Back to Daily Use", self._on_back)
            self._back_button.configure(height=2, pady=1)
            self._back_button.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self._continue_button = document_button(actions, "Continue to Overall Budget", self._finalize, primary=True)
        self._continue_button.configure(height=2, pady=1)
        self._continue_button.grid(row=0, column=1, sticky="ew")
        self._refresh()

    def _reload_and_refresh(self):
        self._reload_jobs()
        self._refresh()

    def _refresh(self):
        self._estimate = IncomeEstimationManager.estimate(self._jobs, self._today())
        month = self._estimate.month.strftime("%B %Y")
        self._month_label.configure(text=month)
        self._subtitle.configure(text=f"Plan income for {month} using your jobs and the actual number of scheduled days that month.")
        self._jobs_heading.configure(text=f"Your jobs ({len(self._jobs)})")
        self._add_button.configure(state="disabled" if self._load_error else "normal")
        self._continue_button.configure(state="disabled" if self._load_error else "normal")
        self._status.configure(text=self._load_error or "Job changes are saved automatically for future budgets.",
                               fg="#B91C1C" if self._load_error else MUTED)
        for key, label in self._total_labels.items():
            label.configure(text=("-" if key == "tax" and self._estimate.tax else "") + _money(getattr(self._estimate, key)))
        if self._job_table is not None:
            self._job_table.destroy()
        self._job_table = table = TkTable(self._root, review_style=True, stretch_column=1, columns=[
            TableColumn("Job", str), TableColumn("Weekly Schedule", tk.Widget), TableColumn("Wage / Hour", str),
            TableColumn("Tax %", str), TableColumn("Month Hours", str), TableColumn("Gross", str),
            TableColumn("Tax", str), TableColumn("Take-home", tk.Widget), TableColumn("Actions", tk.Widget)])
        table.grid(row=3, column=0, sticky="nsew", padx=20)
        for estimate in self._estimate.jobs:
            job = estimate.job
            if job.weekly_shifts is not None:
                groups = {}
                for day, shift in zip(WEEKDAYS, job.weekly_shifts):
                    if shift is not None:
                        groups.setdefault(shift, []).append(day[:3])
                schedule = "\n".join(f"{', '.join(days)}: {shift.start} – {shift.end}"
                                     + (" (next day)" if shift.overnight else "")
                                     + (f" ({shift.unpaid_break_minutes} min unpaid break)" if shift.unpaid_break_minutes else "")
                                     for shift, days in groups.items())
            else:
                schedule = " · ".join(f"{day[:3]} {_work_hours(hours)}h" for day, hours in zip(WEEKDAYS, job.weekly_hours) if hours)
                if schedule:
                    schedule = "Shift times not set\n" + schedule
            schedule = (schedule or "No scheduled shifts") + f"\n{_work_hours(job.hours_per_week)} paid hours / week"
            schedule_label = tk.Label(table._body, text=schedule, justify="left", wraplength=340)
            net = tk.Label(table._body, text=_money(estimate.take_home), fg="#15803D", font=self._bold_font)
            actions = tk.Frame(table._body)
            edit = document_button(actions, "Edit", lambda job=job: self._show_job_editor(job))
            edit.pack(side="left", padx=(0, 6))
            remove = document_button(actions, "Remove", lambda job=job: self._remove_job(job))
            remove.configure(bg="#FEE2E2", fg="#B91C1C", activebackground="#FECACA", activeforeground="#B91C1C")
            remove.pack(side="left")
            if self._load_error:
                edit.configure(state="disabled")
                remove.configure(state="disabled")
            # Let the action frame request its full width before sizing the matching header column.
            actions.update_idletasks()
            table.add_row((job.name, schedule_label, _money(job.hourly_wage), f"{_hours(job.tax_percentage)}%",
                           _work_hours(estimate.hours), _money(estimate.gross), "-" + _money(estimate.tax), net, actions))
            net.configure(fg="#15803D", font=self._bold_font)
        if not self._jobs:
            message = "Saved jobs could not be loaded. Resolve the saved-jobs error, then click Reload Jobs." if self._load_error else (
                "No jobs added yet\nAdd a job to estimate your income for next month.")
            tk.Label(table._body, text=message, bg="white", fg=MUTED, justify="center", padx=24, pady=40).grid(
                row=0, column=0, columnspan=len(table.columns), sticky="ew")

    def _commit_jobs(self, jobs: list[BudgetJob]) -> bool:
        try:
            self._jobs_manager.save(jobs)
        except (OSError, ValueError) as error:
            messagebox.showerror("Could not save jobs", str(error), parent=self._root)
            return False
        self._jobs = jobs
        self._refresh()
        return True

    def _remove_job(self, job: BudgetJob):
        if self._load_error:
            return
        if messagebox.askyesno("Remove job?", f'Remove "{job.name}" from your income estimate?',
                              parent=self._root, default="no"):
            self._commit_jobs([existing for existing in self._jobs if existing.job_id != job.job_id])

    def _show_job_editor(self, job: BudgetJob | None = None):
        if self._load_error:
            return None
        if self._editor is not None and self._editor.winfo_exists():
            self._editor.lift()
            return self._editor
        window = self._editor = tk.Toplevel(self._root)
        window.title("Edit Job" if job is not None else "Add Job")
        window.transient(self._root.winfo_toplevel())
        window.configure(bg=BACKGROUND)
        window.geometry("850x760")
        window.minsize(760, 700)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(1, weight=1)
        tk.Label(window, text="Edit Job" if job is not None else "Add a Job", bg=BACKGROUND, fg=INK,
                 anchor="w", font=(self._normal_font[0], self._normal_font[1] + 5, "bold")).grid(
            row=0, column=0, sticky="ew", padx=20, pady=(18, 12))
        form = tk.Frame(window, bg="white", highlightthickness=1, highlightbackground=BORDER)
        form.grid(row=1, column=0, sticky="nsew", padx=20)
        for column in range(5):
            form.columnconfigure(column, weight=1 if column in (1, 2) else 0)
        shifts = job.weekly_shifts if job and job.weekly_shifts is not None else (None,) * 7
        self._editor_foods = job.foods_per_shift if job else ()
        self._editor_values = {
            "name": tk.StringVar(window, value=job.name if job else ""),
            "wage": tk.StringVar(window, value=_hours(job.hourly_wage) if job else ""),
            "tax": tk.StringVar(window, value=_hours(job.tax_percentage) if job else "0"),
            "working": [tk.BooleanVar(window, value=bool(job and job.weekly_hours[day])) for day in range(7)],
            "starts": [tk.StringVar(window, value=shift.start if shift else "") for shift in shifts],
            "ends": [tk.StringVar(window, value=shift.end if shift else "") for shift in shifts],
            "breaks": [tk.StringVar(window, value=str(shift.unpaid_break_minutes) if shift else "0") for shift in shifts],
        }
        tk.Label(form, text="Job name", bg="white", fg=INK, anchor="w", font=self._bold_font).grid(
            row=0, column=0, columnspan=5, sticky="ew", padx=14, pady=(12, 4))
        name = ttk.Entry(form, textvariable=self._editor_values["name"])
        name.grid(row=1, column=0, columnspan=5, sticky="ew", padx=14, pady=(0, 10))
        for column, span, label, key in ((0, 2, "Hourly wage ($)", "wage"), (2, 3, "Tax percentage (%)", "tax")):
            tk.Label(form, text=label, bg="white", fg=INK, anchor="w").grid(
                row=2, column=column, columnspan=span, sticky="ew", padx=14)
            ttk.Entry(form, textvariable=self._editor_values[key]).grid(
                row=3, column=column, columnspan=span, sticky="ew", padx=14, pady=(4, 10))
        tk.Label(form, text="Weekly schedule", bg="white", fg=INK,
                 anchor="w", font=self._bold_font).grid(row=4, column=0, columnspan=5, sticky="ew", padx=14, pady=(4, 8))
        for column, label in enumerate(("Work day", "Start time", "End time", "Unpaid break\n(minutes)", "Paid hours")):
            tk.Label(form, text=label, bg="white", fg=MUTED, anchor="w", justify="left").grid(
                row=5, column=column, sticky="ew", padx=14, pady=(0, 4))
        self._shift_entries = []
        self._shift_hours_labels = []
        for day_index, day in enumerate(WEEKDAYS):
            row = day_index + 6
            tk.Checkbutton(form, text=day, variable=self._editor_values["working"][day_index],
                           bg="white", fg=INK, activebackground="white", anchor="w").grid(
                row=row, column=0, sticky="ew", padx=10, pady=5)
            entries = []
            for column, key in ((1, "starts"), (2, "ends"), (3, "breaks")):
                entry = ttk.Entry(form, textvariable=self._editor_values[key][day_index], width=7 if key == "breaks" else 14)
                entry.grid(row=row, column=column, sticky="ew", padx=14, pady=5)
                entries.append(entry)
            hours_label = tk.Label(form, bg="white", fg=MUTED, anchor="w", width=7)
            hours_label.grid(row=row, column=4, sticky="ew", padx=14, pady=5)
            self._shift_entries.append(entries)
            self._shift_hours_labels.append(hours_label)
            for key in ("working", "starts", "ends", "breaks"):
                self._editor_values[key][day_index].trace_add("write", lambda *args, day=day_index: self._update_shift_preview(day))
            self._update_shift_preview(day_index)
        food_bar = tk.Frame(form, bg="white")
        food_bar.grid(row=13, column=0, columnspan=5, sticky="ew", padx=14, pady=(12, 14))
        food_bar.columnconfigure(0, weight=1)
        self._shift_foods_label = tk.Label(food_bar, bg="white", fg=INK, anchor="w", font=self._bold_font)
        self._shift_foods_label.grid(row=0, column=0, sticky="ew")
        self._shift_foods_button = document_button(food_bar, "Manage Food per Shift", self._show_shift_foods)
        self._shift_foods_button.grid(row=0, column=1, padx=(12, 0))
        self._refresh_shift_foods_label()
        hint = "Enter shift times and total unpaid break minutes for each working day. Leave breaks blank or zero for none. Earlier end times mean the next day."
        if job and job.weekly_shifts is None and job.hours_per_week:
            hint = "Saved hours are unchanged until you save. Enter times and unpaid break minutes for working days, or uncheck days off. Earlier end times mean the next day."
        self._editor_error = tk.Label(window, text=hint,
                                      bg=BACKGROUND, fg=MUTED, justify="left", anchor="w", wraplength=540)
        self._editor_error.grid(row=2, column=0, sticky="ew", padx=20, pady=(10, 0))
        window.bind("<Configure>", lambda event: self._editor_error.configure(wraplength=max(100, event.width - 40))
                    if event.widget is window else None)
        actions = tk.Frame(window, bg=BACKGROUND)
        actions.grid(row=3, column=0, sticky="ew", padx=20, pady=14)
        actions.columnconfigure(1, weight=1)
        document_button(actions, "Cancel", window.destroy).grid(row=0, column=0, padx=(0, 10))
        self._save_job_button = document_button(actions, "Save Job", lambda: self._save_job(job), primary=True)
        self._save_job_button.grid(row=0, column=1, sticky="ew")
        window.bind("<Escape>", lambda event: window.destroy())
        window.bind("<Return>", lambda event: self._save_job(job))
        name.focus_set()
        return window

    def _save_job(self, existing: BudgetJob | None):
        if self._food_window_open():
            self._food_editor.window.lift()
            return
        values = self._editor_values
        try:
            shifts = []
            for day, working, start, end, unpaid_break in zip(WEEKDAYS, values["working"], values["starts"], values["ends"], values["breaks"]):
                if not working.get():
                    shifts.append(None)
                    continue
                try:
                    shifts.append(WorkShift(start.get(), end.get(), unpaid_break.get().strip() or "0"))
                except ValueError as error:
                    raise ValueError(f"{day}: {error}") from error
            fields = {"name": values["name"].get(), "hourly_wage": values["wage"].get(),
                      "tax_percentage": values["tax"].get(), "weekly_hours": (0,) * 7, "weekly_shifts": tuple(shifts),
                      "foods_per_shift": self._editor_foods}
            if existing is not None:
                fields["job_id"] = existing.job_id
            job = BudgetJob(**fields)
        except ValueError as error:
            self._editor_error.configure(text=str(error), fg="#B91C1C")
            return
        jobs = [job if existing is not None and other.job_id == existing.job_id else other for other in self._jobs]
        if existing is None:
            jobs.append(job)
        if self._commit_jobs(jobs):
            self._editor.destroy()

    def _food_window_open(self) -> bool:
        return self._food_editor is not None and bool(self._food_editor.window.winfo_exists())

    def _refresh_shift_foods_label(self):
        count = len(self._editor_foods)
        self._shift_foods_label.configure(text=f"Food per shift: {count} {'food' if count == 1 else 'foods'}")

    def _show_shift_foods(self):
        if self._food_window_open():
            self._food_editor.window.lift()
            return self._food_editor
        if self._editor is None or not self._editor.winfo_exists():
            return None
        def save_foods(foods):
            self._editor_foods = validate_food_plan(foods)
            self._refresh_shift_foods_label()
            return True
        def close_foods():
            if self._editor.winfo_exists() and self._save_job_button.winfo_exists():
                self._save_job_button.configure(state="normal")
        name = self._editor_values["name"].get().strip() or "this job"
        self._food_editor = FoodPlanEditor(
            self._editor, "Food per Shift", f"Extra food for one shift at {name}, on top of Daily Use. Changes are kept when you save the job.",
            "Quantity / shift", self._editor_foods, self._catalog_manager, save_foods, close_foods,
            foods_manager=self._foods_manager)
        self._save_job_button.configure(state="disabled")
        return self._food_editor

    def _show_day_off_foods(self):
        if self._food_window_open():
            self._food_editor.window.lift()
            return self._food_editor
        try:
            foods = self._day_off_foods_manager.load()
        except (OSError, ValueError) as error:
            messagebox.showerror("Could not load food for days off", str(error), parent=self._root)
            return None
        def save_foods(foods):
            self._day_off_foods_manager.save(foods)
            return True
        self._food_editor = FoodPlanEditor(
            self._root, "Food for Days Off", "Extra food for a day off, on top of Daily Use. This plan is shared across your jobs.",
            "Quantity / day", foods, self._catalog_manager, save_foods, foods_manager=self._foods_manager)
        return self._food_editor

    def _update_shift_preview(self, day: int):
        values = self._editor_values
        working = values["working"][day].get()
        for entry in self._shift_entries[day]:
            entry.configure(state="normal" if working else "disabled")
        text = "Off"
        if working:
            try:
                shift = WorkShift(values["starts"][day].get(), values["ends"][day].get(),
                                  values["breaks"][day].get().strip() or "0")
                text = f"{_work_hours(shift.hours)} h"
            except ValueError:
                text = "—"
        self._shift_hours_labels[day].configure(text=text)

    def _finalize(self):
        if not self._load_error:
            self._parent_next_method()
