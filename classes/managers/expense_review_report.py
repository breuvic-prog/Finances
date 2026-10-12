import os
import re
import tempfile
import textwrap
from collections import defaultdict
from copy import copy
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from math import atan2, cos, hypot, pi, sin
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing, PolyLine, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    CondPageBreak, HRFlowable, KeepInFrame, KeepTogether, LongTable, PageBreak, Paragraph,
    SimpleDocTemplate, Spacer, Table, TableStyle,
)

from classes.custom_tk_components.tk_table_class import get_location_colors
from classes.managers.category_manager import CategoryManager
from classes.managers.date_manager import DateManager
from classes.managers.description_manager import DescriptionManager
from classes.managers.option_manager import OptionManager
from classes.managers.receipt_group_manager import ReceiptGroupManager, ReceiptTransactionRow
from classes.receipt_class import Receipt
from enums.finances.categories_enum import Categories
from enums.finances.is_essential_enum import IsEssential
from enums.finances.locations_enum import Locations


GREEN = colors.HexColor("#008000")
RED = colors.HexColor("#FF0000")
INK = colors.HexColor("#17324D")
PALETTE = [colors.HexColor(value) for value in
           ("#247BA0", "#008000", "#7356A6", "#C87916", "#CA5265", "#147D75", "#5268B8", "#8A641C")]
PAGE_WIDTH, PAGE_HEIGHT = letter
CONTENT_WIDTH = PAGE_WIDTH - 72


def _cents(amount) -> int:
    return int((Decimal(str(float(amount))) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _money(cents: int) -> str:
    return f"{'-' if cents < 0 else ''}${abs(cents) / 100:,.2f}"


def _time(receipt: Receipt | None, seconds: bool = False) -> str:
    if receipt is None or receipt.time is None:
        return ""
    value = receipt.time
    suffix = f":{value.seconds:02}" if seconds else ""
    return f"{value.hours % 12 or 12}:{value.minutes:02}{suffix} {'AM' if value.hours < 12 else 'PM'}"


def _is_excluded(transaction) -> bool:
    return transaction.excluded_from_totals or transaction.is_essential == IsEssential.NOT_INCLUDED


def _slice_label_fits(text, angle, sweep, radius, font_size):
    """Require the padded text rectangle to fit inside its circular sector."""
    width = pdfmetrics.stringWidth(text, "ReviewBold", font_size) + 6
    height = font_size + 6
    x, y = radius * .65 * cos(angle), radius * .65 * sin(angle)
    for dx in (-width / 2, width / 2):
        for dy in (-height / 2, height / 2):
            px, py = x + dx, y + dy
            if hypot(px, py) > radius:
                return False
            difference = atan2(sin(atan2(py, px) - angle), cos(atan2(py, px) - angle))
            if abs(difference) > sweep / 2:
                return False
    return True


def _space_labels(labels, lower, upper, gap):
    """Spread callouts vertically without changing their order along the pie."""
    labels.sort(key=lambda label: label["y"])
    for index, label in enumerate(labels):
        label["y"] = max(lower if index == 0 else labels[index - 1]["y"] + gap, label["y"])
    if labels and labels[-1]["y"] > upper:
        labels[-1]["y"] = upper
        for index in range(len(labels) - 2, -1, -1):
            labels[index]["y"] = min(labels[index]["y"], labels[index + 1]["y"] - gap)


@dataclass
class ExpenseSummary:
    earned: int = 0
    spent: int = 0
    essential: int = 0
    non_essential: int = 0
    essential_categories: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    essential_descriptions: dict[str, dict[str, int]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(int)))
    non_essential_locations: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    @classmethod
    def from_rows(cls, rows: list[ReceiptTransactionRow], all_positive_income: bool = False):
        summary = cls()
        for row in rows:
            transaction = row.transaction
            if _is_excluded(transaction):
                continue
            amount = _cents(transaction.amount)
            if transaction.category == Categories.INCOME:
                if amount > 0:
                    summary.earned += amount
                continue
            if amount > 0:
                if all_positive_income:
                    summary.earned += amount
                continue
            spending = -amount
            summary.spent += spending
            if transaction.is_essential == IsEssential.ESSENTIAL:
                category = OptionManager.display(transaction.category or "Unspecified")
                description = DescriptionManager.display(transaction.description or "Unspecified", transaction.category)
                summary.essential += spending
                summary.essential_categories[category] += spending
                summary.essential_descriptions[category][description] += spending
            else:
                summary.non_essential += spending
                summary.non_essential_locations[OptionManager.display(transaction.location or "Unspecified")] += spending
        return summary


class ReportGenerationError(RuntimeError):
    pass


class ExpenseReviewReport:
    @staticmethod
    def generate(destination: str | Path, rows: list[ReceiptTransactionRow], receipts: list[Receipt],
                 review_date: date | None = None, all_positive_income: bool = False,
                 preview_note: str | None = None, overwrite: bool = False) -> Path:
        """Write the saved review, defaulting to the previous calendar month."""
        destination = Path(destination)
        if destination.exists() and not overwrite:
            raise FileExistsError(f"Confirm replacement before writing the existing report: {destination}")
        period = review_date or date.today().replace(day=1) - timedelta(days=1)
        builder = _ReportBuilder(rows, receipts, period, all_positive_income)
        output = BytesIO()
        document = SimpleDocTemplate(output, pagesize=(PAGE_WIDTH, PAGE_HEIGHT),
                                     leftMargin=36, rightMargin=36, topMargin=32, bottomMargin=36,
                                     title=builder.title, author="Finances", pageCompression=1)
        try:
            document.build(builder.story(preview_note), onFirstPage=builder.footer, onLaterPages=builder.footer)
        except Exception as error:
            raise ReportGenerationError(f"Could not build Expense Review.pdf: {error}") from error
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(dir=destination.parent, prefix="expense-review-",
                                             suffix=".pdf", delete=False) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(output.getvalue())
            if overwrite:
                os.replace(temporary_path, destination)
            elif os.name == "nt":
                os.rename(temporary_path, destination)
            else:
                with destination.open("xb") as output_file:
                    output_file.write(output.getvalue())
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        return destination


class _ReportBuilder:
    def __init__(self, rows, receipts, period, all_positive_income):
        self.rows = rows
        self.visible_rows = [row for row in rows if not ReceiptGroupManager.is_hidden(row)]
        self.period = period
        self.all_positive_income = all_positive_income
        self.summary = ExpenseSummary.from_rows(rows, all_positive_income)
        self.title = f"Expense Review, {DateManager.month_number_to_name(period.month)} {period.year}"
        self._register_fonts()
        self.styles = {
            "title": ParagraphStyle("ReviewTitle", fontName="ReviewBold", fontSize=26, leading=32,
                                    alignment=TA_CENTER, spaceAfter=14),
            "section": ParagraphStyle("ReviewSection", fontName="ReviewBold", fontSize=20, leading=25,
                                      textColor=INK, spaceAfter=12, keepWithNext=True),
            "heading": ParagraphStyle("ReviewHeading", fontName="ReviewBold", fontSize=13, leading=18,
                                      textColor=INK, spaceAfter=9, keepWithNext=True),
            "body": ParagraphStyle("ReviewBody", fontName="Review", fontSize=9, leading=13, spaceAfter=7),
            "cell": ParagraphStyle("ReviewCell", fontName="Review", fontSize=7.5, leading=10),
            "receipt_amount": ParagraphStyle("ReceiptAmount", fontName="Review", fontSize=9,
                                              leading=12, spaceAfter=3),
            "legend": ParagraphStyle("ReviewLegend", fontName="Review", fontSize=8, leading=11),
        }
        self.receipts = []
        self.purchases = {}
        seen = set()
        hidden_receipts = ReceiptGroupManager.hidden_receipt_ids(rows)
        for row in rows:
            if row.purchase.receipt is not None:
                self.purchases[id(row.purchase.receipt)] = row.purchase
        candidates = list(receipts) + [row.purchase.receipt for row in rows if row.purchase.receipt is not None]
        for receipt in candidates:
            if (id(receipt) not in seen and id(receipt) not in hidden_receipts
                    and (receipt.date.year, receipt.date.month) == (period.year, period.month)):
                self.receipts.append(receipt)
                seen.add(id(receipt))
        self.receipts.sort(key=lambda receipt: (
            receipt.date.day,
            (receipt.time.hours, receipt.time.minutes, receipt.time.seconds) if receipt.time else (-1, -1, -1),
            receipt.location,
        ))
        self.receipt_numbers = {id(receipt): index for index, receipt in enumerate(self.receipts, start=1)}

    @staticmethod
    def _register_fonts():
        if "Review" in pdfmetrics.getRegisteredFontNames():
            return
        font_directory = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        regular, bold = font_directory / "arial.ttf", font_directory / "arialbd.ttf"
        if not regular.is_file() or not bold.is_file():
            font_directory = Path(reportlab.__file__).parent / "fonts"
            regular, bold = font_directory / "Vera.ttf", font_directory / "VeraBd.ttf"
        pdfmetrics.registerFont(TTFont("Review", str(regular)))
        pdfmetrics.registerFont(TTFont("ReviewBold", str(bold)))
        pdfmetrics.registerFontFamily("Review", normal="Review", bold="ReviewBold")

    def paragraph(self, value, style="body", color=None, markup=False):
        text = str(value) if markup else escape(OptionManager.display(value))
        if style in ("title", "section", "heading"):
            text = re.sub(r"\b(?:Non-Essential|Essential)\b", lambda match:
                          f'<font color="{"red" if match[0].lower().startswith("non-") else "green"}">{match[0]}</font>',
                          text, flags=re.IGNORECASE)
        paragraph_style = self.styles[style]
        if color is not None:
            paragraph_style = ParagraphStyle("ColoredCell", parent=paragraph_style, textColor=color)
        return Paragraph(text, paragraph_style)

    def footer(self, canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#CDD6DF"))
        canvas.line(36, 27, PAGE_WIDTH - 36, 27)
        canvas.setFillColor(INK)
        canvas.setFont("Review", 8)
        canvas.drawString(36, 15, self.title)
        canvas.drawRightString(PAGE_WIDTH - 36, 15, f"Page {document.page}")
        canvas.restoreState()

    def story(self, preview_note):
        summary = self.summary
        story = [self.paragraph(f"<u>{escape(self.title)}</u>", "title", markup=True)]
        if preview_note:
            story.append(self.paragraph(preview_note))
        for label, amount, color in (("Amount earned", summary.earned, GREEN),
                                     ("Amount spent", summary.spent, RED),
                                     ("Difference", summary.earned - summary.spent,
                                      GREEN if summary.earned >= summary.spent else RED)):
            story.append(self.paragraph(f"<b>{label}: {_money(amount)}</b>", "heading", color, markup=True))
        income_definition = "all positive transactions" if self.all_positive_income else "positive Income transactions"
        story.append(self.paragraph(f"Income includes {income_definition}. Spending includes outgoing expenses. "
                                    "Income is excluded from spending totals and charts. "
                                    "Internal transfers and transactions marked Not Included are excluded from all totals."))
        story.extend([HRFlowable(width="100%", color=INK), Spacer(1, 12),
                      self.paragraph("Essential vs Non-Essential Spending", "heading")])
        comparison = {"Essential": summary.essential, "Non-Essential": summary.non_essential}
        story.append(self.pie_with_legend(comparison, CONTENT_WIDTH,
                                          {"Essential": GREEN, "Non-Essential": RED}, size=300))
        self.add_chart_section(story, "Essential Spending", "Essential spending by category",
                               summary.essential_categories, category_colors=True)
        for category in sorted(summary.essential_descriptions):
            self.add_chart_section(story, "Essential Spending", f"{category} - by description",
                                   summary.essential_descriptions[category], side_by_side=True)
        self.add_chart_section(story, "Non-Essential Spending", "Non-essential spending by location",
                               summary.non_essential_locations, location_colors=True)
        story.extend([PageBreak(), self.paragraph("Expenses", "section"), self.expense_table(),
                      PageBreak(), self.paragraph("Receipts", "section")])
        if not self.receipts:
            story.append(self.paragraph("No receipts for this review month."))
        for index, receipt in enumerate(self.receipts, start=1):
            section = self.receipt_section(index, receipt)
            if index > 1:
                section = [Spacer(1, 8), HRFlowable(width="100%", thickness=3, color=colors.black),
                           Spacer(1, 8)] + section
            # Short receipts stay intact and share pages. Oversized receipts
            # still paginate normally, with the item table repeating its header.
            story.append(KeepTogether(section))
        return [flowable for entry in story for flowable in (entry if isinstance(entry, list) else [entry])]

    def add_chart_section(self, story, title, heading, values, location_colors=False, side_by_side=False,
                          category_colors=False):
        charts = self.paired_charts(values, location_colors, side_by_side, category_colors)
        content = ([self.paragraph(f"{title}: {heading}", "heading")] if side_by_side else
                   [self.paragraph(title, "section"), self.paragraph(heading, "heading")])
        content.extend(charts if isinstance(charts, list) else [charts])
        story.append(Spacer(1, 18))
        if isinstance(charts, list):
            story.extend(content)
        else:
            story.append(KeepTogether(content))

    @staticmethod
    def chart_entries(values):
        return sorted(((label, cents) for label, cents in values.items() if cents > 0),
                      key=lambda item: (-item[1], item[0]))

    def pie_with_legend(self, values, width, color_map=None, size=205):
        entries = self.chart_entries(values)
        if not entries:
            return self.paragraph("No spending in this section.")
        total = sum(value for _, value in entries)
        font_size = 7 if size < 150 else 11 if size > 250 else 8 if len(entries) <= 6 else 7
        labels = [_money(value) for _, value in entries]
        margin = max(pdfmetrics.stringWidth(label, "ReviewBold", font_size) for label in labels) + 14
        drawing = Drawing(size + margin * 2, max(size + 32, len(entries) * (font_size + 6) + 20))
        radius = size / 2
        center_x, center_y = margin + radius, drawing.height / 2
        pie = Pie()
        pie.x, pie.y, pie.width, pie.height = margin, center_y - radius, size, size
        pie.data = [value / 100 for _, value in entries]
        pie.slices.label_visible = False
        pie.slices.strokeColor = colors.white
        pie.slices.strokeWidth = 1
        drawing.add(pie)
        outside = {False: [], True: []}
        angle = pi / 2
        for index, (label, value) in enumerate(entries):
            color = (color_map or {}).get(label, PALETTE[index % len(PALETTE)])
            pie.slices[index].fillColor = color
            sweep = value / total * 2 * pi
            middle = angle - sweep / 2
            angle -= sweep
            luminance = 0.299 * color.red + 0.587 * color.green + 0.114 * color.blue
            text = labels[index]
            if _slice_label_fits(text, middle, sweep, radius, font_size):
                drawing.add(String(center_x + radius * .65 * cos(middle),
                                   center_y + radius * .65 * sin(middle) - font_size * .35, text,
                                   textAnchor="middle", fontName="ReviewBold", fontSize=font_size,
                                   fillColor=colors.black if luminance > .6 else colors.white))
            else:
                outside[cos(middle) >= 0].append({"text": text, "angle": middle,
                                                "y": center_y + radius * sin(middle)})
        for right, callouts in outside.items():
            _space_labels(callouts, 10, drawing.height - 10, font_size + 6)
            direction = 1 if right else -1
            label_x = center_x + direction * (radius + 12)
            for callout in callouts:
                middle, y = callout["angle"], callout["y"]
                drawing.add(PolyLine((center_x + radius * cos(middle), center_y + radius * sin(middle),
                                      center_x + direction * (radius + 5), y,
                                      label_x - direction * 2, y), strokeColor=INK, strokeWidth=.6))
                drawing.add(String(label_x, y - font_size * .35, callout["text"],
                                   textAnchor="start" if right else "end", fontName="ReviewBold",
                                   fontSize=font_size, fillColor=INK))
        legend_data = []
        for index, (label, value) in enumerate(sorted(values.items(), key=lambda item: (-item[1], item[0]))):
            color = (color_map or {}).get(label, PALETTE[index % len(PALETTE)])
            legend_data.append([self.paragraph("■", "legend", color),
                                self.paragraph(f"{label}: {value / total:.1%}", "legend")])
        legend_width = width - drawing.width - 8
        legend = Table(legend_data, colWidths=[13, legend_width - 13],
                       style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                         ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                         ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                                         ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
        return Table([[drawing, KeepInFrame(legend_width, 400, [legend], mode="shrink")]],
                     colWidths=[drawing.width + 4, legend_width + 4],
                     style=TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                       ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                       ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))

    def paired_charts(self, values, location_colors=False, side_by_side=False, category_colors=False):
        entries = self.chart_entries(values)
        if not entries:
            return self.paragraph("No spending in this section.")
        color_map = {}
        for index, (label, _) in enumerate(entries):
            pair = (self.category_color(label) if category_colors else
                    self.location_color(label) if location_colors else None)
            color_map[label] = pair[0] if pair else PALETTE[index % len(PALETTE)]
        if len(entries) <= 12:
            return self.chart_pair(entries, color_map, side_by_side=side_by_side)
        total = sum(value for _, value in entries)
        remaining_label = "Other groups (combined)"
        while remaining_label in values:
            remaining_label += " - remaining"
        color_map[remaining_label] = colors.HexColor("#CBD5E1")
        sections = []
        for offset in range(0, len(entries), 12):
            chunk = entries[offset:offset + 12]
            section = []
            if offset:
                sections.append(Spacer(1, 18))
                section.append(self.paragraph("Spending breakdown - continued", "heading"))
            caption = self.paragraph(
                f"Groups {offset + 1}-{offset + len(chunk)} of {len(entries)}. "
                "Pie percentages refer to the full section total; the gray slice combines the other groups.")
            caption.keepWithNext = True
            section.append(caption)
            pie_values = dict(chunk)
            pie_values[remaining_label] = total - sum(value for _, value in chunk)
            section.append(self.chart_pair(chunk, color_map, pie_values, side_by_side))
            sections.extend(section)
        return sections

    def chart_pair(self, entries, color_map, pie_values=None, side_by_side=False):
        pie_width = CONTENT_WIDTH * .56 if side_by_side else CONTENT_WIDTH
        width = CONTENT_WIDTH - pie_width if side_by_side else CONTENT_WIDTH
        pie = self.pie_with_legend(pie_values if pie_values is not None else dict(entries),
                                   pie_width - 8 if side_by_side else pie_width, color_map,
                                   size=130 if side_by_side else 205)
        height = min(320, max(150 if side_by_side else 260, len(entries) * 23))
        drawing = Drawing(width, height + 36)
        bars = HorizontalBarChart()
        bars.x = 85 if side_by_side else 113
        bars.y, bars.width, bars.height = 28, width - bars.x - 12, height
        bars.data = [[value / 100 for _, value in reversed(entries)]]
        bars.categoryAxis.categoryNames = ["\n".join(textwrap.wrap(label[:40], 16 if side_by_side else 22))
                                           for label, _ in reversed(entries)]
        bars.categoryAxis.labels.fontName = "Review"
        bars.categoryAxis.labels.fontSize = max(5, min(8, height / len(entries) / 3))
        bars.categoryAxis.labels.leading = bars.categoryAxis.labels.fontSize + 1
        bars.valueAxis.valueMin = 0
        label_width = max(pdfmetrics.stringWidth(_money(value), "ReviewBold", 7) for _, value in entries) + 8
        bars.valueAxis.valueMax = max(value for _, value in entries) / 100 * bars.width / max(1, bars.width - label_width)
        bars.valueAxis.labels.fontName = "Review"
        bars.valueAxis.labels.fontSize = 7
        bars.valueAxis.labelTextFormat = lambda value: f"${value:,.0f}"
        bars.barLabelFormat = lambda value: f"${value:,.2f}"
        bars.barLabels.fontName = "ReviewBold"
        bars.barLabels.fontSize = 7
        bars.barLabels.boxAnchor = "w"
        bars.barLabels.nudge = 4
        bars.bars.strokeColor = None
        for index, (label, _) in enumerate(reversed(entries)):
            bars.bars[0, index].fillColor = color_map[label]
        drawing.add(bars)
        return Table([[pie, drawing]] if side_by_side else [[pie], [drawing]],
                     colWidths=[pie_width, width] if side_by_side else [CONTENT_WIDTH],
                     style=TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                       ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                       ("RIGHTPADDING", (0, 0), (-1, -1), 8)]))

    @staticmethod
    def category_color(category):
        pair = CategoryManager.colors(category)
        return tuple(colors.HexColor(value) for value in pair) if pair else None

    @staticmethod
    def location_color(location):
        location = OptionManager.resolve(Locations, str(location)) or location
        normalized = "".join(character for character in str(location).casefold() if character.isalnum())
        if normalized == "kwikstar":
            normalized = "kwiktrip"
        for candidate in Locations:
            if normalized == "".join(character for character in str(candidate).casefold() if character.isalnum()):
                pair = get_location_colors(candidate)
                if pair:
                    return tuple(colors.HexColor(value) for value in pair)
        return None

    def table(self, headings, data, widths, cell_colors):
        header = [self.paragraph(f"<b>{escape(heading)}</b>", "cell", colors.white, markup=True)
                  for heading in headings]
        widths = [width / sum(widths) * CONTENT_WIDTH for width in widths]
        table = LongTable([header] + data, colWidths=widths, repeatRows=1, splitInRow=1)
        style = [("BACKGROUND", (0, 0), (-1, 0), INK),
                 ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F4F7")]),
                 ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BEC9D3")),
                 ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                 ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]
        style.extend(("BACKGROUND", (column, row), (column, row), color)
                     for column, row, color in cell_colors)
        table.setStyle(TableStyle(style))
        return table

    def expense_table(self):
        data, backgrounds = [], []
        for row_number, row in enumerate(self.visible_rows, start=1):
            transaction = row.transaction
            receipt_number = self.receipt_numbers.get(id(transaction.receipt))
            fields = [str(transaction.date), _time(transaction.receipt), OptionManager.display(transaction.location or ""),
                      _money(_cents(transaction.amount)), OptionManager.display(transaction.category or ""),
                      DescriptionManager.display(transaction.description or "", transaction.category), str(transaction.is_essential or ""),
                      f"Receipt {receipt_number}" if receipt_number is not None else ""]
            row_colors = {}
            location = self.location_color(transaction.location)
            if location:
                backgrounds.append((2, row_number, location[0]))
                row_colors[2] = location[1]
            category = self.category_color(transaction.category)
            if category:
                backgrounds.append((4, row_number, category[0]))
                row_colors[4] = category[1]
            amount = _cents(transaction.amount)
            if amount:
                backgrounds.append((3, row_number, GREEN if amount > 0 else RED))
            if transaction.is_essential in (IsEssential.ESSENTIAL, IsEssential.NON_ESSENTIAL):
                backgrounds.append((6, row_number, GREEN if transaction.is_essential == IsEssential.ESSENTIAL else RED))
            if transaction.is_essential == IsEssential.NOT_INCLUDED:
                backgrounds.append((6, row_number, colors.black))
                row_colors[6] = colors.white
            if not fields[1]:
                backgrounds.append((1, row_number, colors.black))
            if receipt_number is None:
                backgrounds.append((7, row_number, colors.black))
            cells = [self.paragraph(value, "cell", row_colors.get(column)) for column, value in enumerate(fields)]
            if receipt_number is not None:
                cells[7] = self.paragraph(f'<link href="#receipt-{receipt_number}" color="#17324D">'
                                          f'Receipt {receipt_number}</link>', "cell", markup=True)
            data.append(cells)
        if not data:
            return self.paragraph("No visible transactions in this review." if self.rows else "No transactions in this review.")
        return self.table(["Date", "Time", "Location", "Amount", "Category", "Description", "Is Essential?", "Receipt"],
                          data, [64, 52, 88, 70, 105, 175, 92, 74], backgrounds)

    def receipt_section(self, index, receipt):
        location_name = OptionManager.display(OptionManager.resolve(Locations, receipt.location) or receipt.location)
        heading = f'<a name="receipt-{index}"/>Receipt {index}: {escape(location_name)}'
        content = [self.paragraph(heading, "heading", markup=True)]
        location = self.location_color(receipt.location)
        metadata = Table([[self.paragraph(f"<b>Date: {receipt.date}</b>", markup=True),
                           self.paragraph(f"<b>Location: {escape(location_name)}</b>",
                                          color=location[1] if location else None, markup=True),
                           self.paragraph(f"<b>Time: {_time(receipt, True) or 'Not provided'}</b>", markup=True)]],
                         colWidths=[CONTENT_WIDTH / 3] * 3)
        metadata.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 1, INK),
                                      ("INNERGRID", (0, 0), (-1, -1), 1, INK),
                                      ("TOPPADDING", (0, 0), (-1, -1), 8),
                                      ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]
                                     + ([("BACKGROUND", (1, 0), (1, 0), location[0])] if location else [])))
        content.extend([metadata, Spacer(1, 4),
                        self.paragraph(f"Subtotal: {_money(_cents(receipt.subtotal))}", "receipt_amount"),
                        self.paragraph(f"Tax: {_money(_cents(receipt.taxes))}", "receipt_amount"),
                        HRFlowable(width="100%", color=INK),
                        self.paragraph(f"<b>Total: {_money(_cents(receipt.total))}</b>",
                                       "receipt_amount", markup=True), Spacer(1, 8)])
        purchase = self.purchases.get(id(receipt))
        data, backgrounds = [], []
        for row_number, original in enumerate(receipt.items, start=1):
            item = copy(original)
            if purchase is not None:
                for field_name in ("category", "is_essential", "description"):
                    value = getattr(purchase, field_name)
                    if value is not None:
                        setattr(item, field_name, value)
            name = escape(item.name)
            if item.link:
                name = f'<link href="{escape(item.link, {chr(34): "&quot;"})}" color="#17324D">{name}</link>'
            cost = -_cents(item.cost)
            if cost:
                backgrounds.append((2, row_number, RED if cost < 0 else GREEN))
            selected = item.is_essential == IsEssential.ESSENTIAL
            backgrounds.append((5, row_number, GREEN if selected else RED))
            category = self.category_color(item.category)
            if category:
                backgrounds.append((3, row_number, category[0]))
            data.append([self.paragraph(name, "cell", markup=True), self.paragraph(f"{item.quantity:g}", "cell"),
                         self.paragraph(_money(cost), "cell"),
                         self.paragraph(item.category or "", "cell", category[1] if category else None),
                         self.paragraph(DescriptionManager.display(item.description, item.category) or item.name, "cell"),
                         self.paragraph("Yes" if selected else "No", "cell", colors.white)])
        if data:
            headings = ["Item", "Quantity", "Cost", "Category", "Description", "Is Essential?"]
            widths = [160, 64, 72, 126, 220, 78]
            first_row_height = self.table(headings, data[:1], widths, []).wrap(CONTENT_WIDTH, PAGE_HEIGHT)[1]
            # Reserve the metadata and first item before starting a long receipt.
            # Its remaining rows can then continue on later pages.
            minimum_height = first_row_height + sum(
                flowable.wrap(CONTENT_WIDTH, PAGE_HEIGHT)[1]
                + flowable.getSpaceBefore() + flowable.getSpaceAfter() for flowable in content
            )
            content.insert(0, CondPageBreak(minimum_height))
            content.append(self.table(headings, data, widths, backgrounds))
        else:
            content.append(self.paragraph("No items listed."))
        return content
