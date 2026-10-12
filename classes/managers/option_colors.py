"""Shared default colors for option lists, transaction cells, and reports."""

from colorsys import hls_to_rgb
from hashlib import sha256


DEFAULT_BACKGROUNDS = {
    "Locations.WALMART": "#0053E2", "Locations.AMAZON": "#FF9900",
    "Locations.KWIK_TRIP": "#D71920", "Locations.PLAYSTATION": "#003791",
    "Locations.VENDING_MACHINE": "#455A64", "Locations.MICROSOFT": "#737373",
    "Locations.APPLE": "#A2AAAD", "Locations.DOLLAR_GENERAL": "#FFF200",
    "Locations.FREEDOM_BANK": "#006747", "Locations.FIRST_SECURITY_BANK": "#1D3557",
    "Locations.HUCKLEBERRYS": "#7B2D59", "Locations.CULVERS": "#005696",
    "Locations.PRAIRIE_CINEMA": "#800020", "Locations.DISCOVER": "#FF6000",
    "Categories.CAR": "#1565C0", "Categories.HOUSING": "#6A1B9A",
    "Categories.SUBSCRIPTIONS": "#00796B", "Categories.SHOPPING": "#F9A825",
    "Categories.STUDENT_LOANS": "#3949AB", "Categories.INCOME": "#2E7D32",
    "Categories.CREDIT_CARD": "#455A64", "Categories.DISCRETIONARY_SPENDING": "#C2410C",
    "IsEssential.ESSENTIAL": "#008000", "IsEssential.NON_ESSENTIAL": "#FF0000",
    "IsEssential.NOT_INCLUDED": "#000000",
}


def text_color(background: str) -> str:
    channels = [int(background[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [channel / 12.92 if channel <= .04045 else ((channel + .055) / 1.055) ** 2.4
              for channel in channels]
    luminance = sum(weight * channel for weight, channel in zip((.2126, .7152, .0722), linear))
    return "#111111" if luminance > .179 else "#FFFFFF"


def default_background(option) -> str:
    key = f"{type(option).__name__}.{option.name}"
    if key in DEFAULT_BACKGROUNDS:
        return DEFAULT_BACKGROUNDS[key]
    # Stable colors for options saved before editable colors were introduced.
    name = option.value.casefold() if type(option).__name__ == "Categories" else key
    hue = int.from_bytes(sha256(name.encode("utf-8")).digest()[:2], "big") / 65535
    return "#" + "".join(f"{round(channel * 255):02X}" for channel in hls_to_rgb(hue, .83, .55))
