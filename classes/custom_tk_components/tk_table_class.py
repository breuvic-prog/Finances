"""Imports"""
import tkinter as tk
from classes.table_column_class import TableColumn


class TkTable(tk.Frame):
    def __init__(self, parent: tk.Misc,
                 columns:list[TableColumn],
                 **kwargs):
        super().__init__(parent,
                         **kwargs)
        self._columns = columns
        self._current_index = 0

        #Creates the components
        for i, column in enumerate(self._columns):
            tk.Label(self,
                     text = column.text,
                     borderwidth=2,
                     relief="solid").grid(row=0, column=i)

    def add_row(self, row:tuple):
        #Check if the length matches
        if len(row) != len(self._columns):
            raise IndexError("Length of row does not match")

        #Checks if the datatype match the columns
        for i in range(len(row)):
            if type(row[i] != self._columns[i].data_type):
                raise TypeError(f"Datatype of {row[i]} does not match it's column")

        # Adds the actual components
        for i, item in enumerate(row):
            tk.Label(self,
                     text=str(item)).grid(row=self._current_index,
                                          column=i)

        #Increments the current index
        self._current_index += 1




    @property
    def columns(self):
        return self._columns