"""Imports"""


class TableColumn:
    def __init__(self, text:str,
                 data_type:object):
        self._text = text
        self._data_type = data_type

        
    @property
    def text(self):
        return self._text
    @property
    def data_type(self):
        return self._data_type
