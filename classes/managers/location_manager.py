from pathlib import Path

from classes.managers.enum_manager import EnumManager
from enums.finances import locations_enum
from enums.finances.locations_enum import Locations


_LOCATIONS_ENUM_PATH = Path(locations_enum.__file__).resolve()


class LocationManager:
    @staticmethod
    def create(name: str) -> Locations:
        """Save a location in the enum source and make it available immediately."""
        return EnumManager.create(name, Locations, _LOCATIONS_ENUM_PATH, "location")
