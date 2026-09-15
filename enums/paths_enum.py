"""Imports"""
from enum import StrEnum
from pathlib import Path

from classes.managers.path_manager import PathManager
from enums.folders_enum import Folders


class Paths(StrEnum):
    DOWNLOADS = str(Path.home() / "Downloads")
    ASSETS_CSVS = PathManager.join(Folders.ASSETS, Folders.CSVS)
    ASSETS_JSONS = PathManager.join(Folders.ASSETS, Folders.JSONS)
    ASSETS_TXTS = PathManager.join(Folders.ASSETS, Folders.TXTS)
    RECEIPTS = PathManager.join(ASSETS_JSONS, Folders.RECEIPTS)



