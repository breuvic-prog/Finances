"""Imports"""
from abc import ABC
from classes.pages.page_container_class import PageContainer

class RootPage(PageContainer, ABC):
    def __init__(self):
        super().__init__()