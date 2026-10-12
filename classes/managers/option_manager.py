"""Persist option labels, colors, and visibility without changing enum identities."""

import json
import os
import re
from colorsys import hls_to_rgb
from pathlib import Path
import tempfile
import unicodedata
import weakref
from collections.abc import Callable, Iterable
from enum import StrEnum

from classes.managers.option_colors import DEFAULT_BACKGROUNDS, default_background, text_color


_OPTIONS_PATH = Path(__file__).resolve().parents[2] / "assets" / "jsons" / "option_preferences.json"


class OptionManager:
    _loaded_path: Path | None = None
    _preferences: dict[str, dict] = {}
    _listeners: set[weakref.WeakMethod] = set()

    @staticmethod
    def key(option: StrEnum) -> str:
        return f"{type(option).__name__}.{option.name}"

    @classmethod
    def _load(cls) -> dict[str, dict]:
        if cls._loaded_path != _OPTIONS_PATH:
            preferences = json.loads(_OPTIONS_PATH.read_text(encoding="utf-8")) if _OPTIONS_PATH.exists() else {}
            if not isinstance(preferences, dict) or any(not isinstance(record, dict) for record in preferences.values()):
                raise ValueError("Invalid option preferences file.")
            cls._preferences = preferences
            cls._loaded_path = _OPTIONS_PATH
        return cls._preferences

    @classmethod
    def display(cls, value) -> str:
        if not isinstance(value, StrEnum):
            return str(value) if value is not None else ""
        return cls._load().get(cls.key(value), {}).get("label", value.value)

    @classmethod
    def available(cls, options: Iterable[StrEnum]) -> list[StrEnum]:
        preferences = cls._load()
        return [option for option in options if not preferences.get(cls.key(option), {}).get("hidden", False)]

    @classmethod
    def colors(cls, option) -> tuple[str, str] | None:
        if not isinstance(option, StrEnum):
            return None
        background = cls._load().get(cls.key(option), {}).get("color", default_background(option))
        return background, text_color(background)

    @classmethod
    def set_color(cls, option: StrEnum, color: str) -> None:
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise ValueError("Choose a valid color.")
        record = {**cls._load().get(cls.key(option), {}), "color": color.upper()}
        cls._save({**cls._load(), cls.key(option): record})

    @classmethod
    def assign_unused_color(cls, option: StrEnum, choices: Iterable[StrEnum]) -> StrEnum:
        from enums.finances.categories_enum import Categories
        from enums.finances.locations_enum import Locations
        from classes.managers.description_manager import DescriptionManager

        if cls._load().get(cls.key(option), {}).get("color"):
            return option
        all_choices = [*choices, *Categories, *Locations, *DescriptionManager.choices(include_hidden=True)]
        for category in Categories:
            all_choices.extend(DescriptionManager.choices(category, include_hidden=True))
        used = set(DEFAULT_BACKGROUNDS.values())
        used.update(record["color"].upper() for record in cls._load().values() if record.get("color"))
        used.update(cls.colors(member)[0] for member in all_choices if cls.key(member) != cls.key(option))
        index = 0
        while True:
            hue = (index * .3819660112501051) % 1
            lightness = .78 - .04 * ((index // 360) % 6)
            color = "#" + "".join(f"{round(channel * 255):02X}" for channel in hls_to_rgb(hue, lightness, .65))
            if color not in used:
                cls.set_color(option, color)
                return option
            index += 1

    @classmethod
    def resolve(cls, options: Iterable[StrEnum], name: str) -> StrEnum | None:
        if isinstance(options, type) and issubclass(options, StrEnum):
            try:
                return options(name)
            except ValueError:
                pass
        options = list(options)
        normalized = " ".join(name.split()).casefold()
        canonical = next((option for option in options if normalized == option.value.casefold()), None)
        return canonical or next((option for option in options if normalized == cls.display(option).casefold()), None)

    @classmethod
    def rename(cls, option: StrEnum, name: str, choices: Iterable[StrEnum]) -> None:
        name = " ".join(name.split())
        if not name or not any(character.isalnum() for character in unicodedata.normalize("NFKD", name)):
            raise ValueError("Enter a name containing a letter or number.")
        if name.casefold() == "none":
            raise ValueError('"None" is reserved for an unfilled field.')
        if name.casefold() == "not included":
            raise ValueError('Choose a different name. "Not Included" belongs in Is Essential.')
        existing = cls.resolve(type(option), name)
        if existing is not None and cls.key(existing) != cls.key(option):
            raise ValueError("An option with that name already exists.")
        for other in [*choices, *type(option)]:
            if cls.key(other) != cls.key(option) and name.casefold() in (
                    cls.display(other).casefold(), other.value.casefold()):
                raise ValueError("An option with that name already exists.")
        if name != cls.display(option):
            record = {**cls._load().get(cls.key(option), {}), "label": name}
            cls._save({**cls._load(), cls.key(option): record})

    @classmethod
    def delete(cls, option: StrEnum) -> None:
        record = {**cls._load().get(cls.key(option), {}), "hidden": True}
        cls._save({**cls._load(), cls.key(option): record})

    @classmethod
    def restore(cls, option: StrEnum) -> StrEnum:
        record = cls._load().get(cls.key(option), {})
        if record.get("hidden"):
            cls._save({**cls._load(), cls.key(option): {**record, "hidden": False}})
        return option

    @classmethod
    def subscribe(cls, callback: Callable) -> None:
        cls._listeners.add(weakref.WeakMethod(callback))

    @classmethod
    def _save(cls, preferences: dict[str, dict]) -> None:
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=_OPTIONS_PATH.parent,
                                             prefix=".option_preferences.", suffix=".tmp", delete=False) as temporary:
                temporary_path = Path(temporary.name)
                json.dump(preferences, temporary, indent=2, ensure_ascii=False)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, _OPTIONS_PATH)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        cls._preferences = preferences
        cls._loaded_path = _OPTIONS_PATH
        for listener in tuple(cls._listeners):
            callback = listener()
            if callback is None:
                cls._listeners.discard(listener)
            else:
                callback()
