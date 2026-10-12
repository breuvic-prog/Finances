from pathlib import Path
from colorsys import hls_to_rgb
from hashlib import sha256

from classes.managers.enum_manager import EnumManager
from classes.managers.option_manager import OptionManager
from enums.finances import categories_enum
from enums.finances.categories_enum import Categories


_CATEGORIES_ENUM_PATH = Path(categories_enum.__file__).resolve()

class CategoryManager:
    @staticmethod
    def create(name: str) -> Categories:
        """Save a category in the enum source and make it available immediately."""
        if " ".join(name.split()).casefold() == "not included":
            raise ValueError('Select "Not Included" in Is Essential instead.')
        if " ".join(name.split()).casefold() == "groceries":
            return Categories.SHOPPING
        if " ".join(name.split()).casefold() == "paycheck":
            return Categories.INCOME
        return EnumManager.create(name, Categories, _CATEGORIES_ENUM_PATH, "category")

    @staticmethod
    def colors(category: Categories | str | None) -> tuple[str, str] | None:
        """Share category colors between editable cells, report tables, and charts."""
        if category is None or not str(category).strip():
            return None
        category = OptionManager.resolve(Categories, str(category)) or category
        if isinstance(category, Categories):
            return OptionManager.colors(category)
        name = " ".join(str(category).split()).casefold()
        # User-created categories keep a stable pastel color across restarts.
        hue = int.from_bytes(sha256(name.encode("utf-8")).digest()[:2], "big") / 65535
        rgb = hls_to_rgb(hue, .83, .55)
        return "#" + "".join(f"{round(channel * 255):02X}" for channel in rgb), "#111111"
