import ast
import os
import re
import tempfile
import unicodedata
from enum import StrEnum
from pathlib import Path
from typing import TypeVar

from aenum import extend_enum


_EnumValue = TypeVar("_EnumValue", bound=StrEnum)


class EnumManager:
    @staticmethod
    def create(name: str, enum_type: type[_EnumValue], path: Path, label: str) -> _EnumValue:
        """Save a named enum member and make it available immediately."""
        name = " ".join(name.split())
        if not name:
            raise ValueError(f"Enter a {label} name.")
        for member in enum_type:
            if member.value.casefold() == name.casefold():
                return member

        identifier_text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
        identifier = re.sub(r"[^A-Z0-9]+", "_", identifier_text.upper()).strip("_")
        if not identifier:
            raise ValueError(f"The {label} name must contain a letter or number.")
        if identifier[0].isdigit():
            identifier = label.upper() + "_" + identifier

        source = path.read_bytes().decode("utf-8")
        definition = next((node for node in ast.parse(source).body
                           if isinstance(node, ast.ClassDef) and node.name == enum_type.__name__), None)
        if definition is None:
            raise ValueError(f"Could not find the {enum_type.__name__} enum to save the new {label}.")
        source_members = {
            node.targets[0].id: node.value.value
            for node in definition.body
            if isinstance(node, ast.Assign) and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
        }
        # Include any members saved since this process imported the enum.
        for member_name, value in source_members.items():
            if value.casefold() == name.casefold():
                return extend_enum(enum_type, member_name, value)

        member_name = identifier
        suffix = 2
        while hasattr(enum_type, member_name) or member_name in source_members:
            member_name = f"{identifier}_{suffix}"
            suffix += 1

        newline = "\r\n" if "\r\n" in source else "\n"
        lines = source.splitlines(keepends=True)
        insertion_line = definition.end_lineno
        if not lines[insertion_line - 1].endswith(("\n", "\r")):
            lines[insertion_line - 1] += newline
        indent = " " * definition.body[0].col_offset
        lines.insert(insertion_line, f"{indent}{member_name} = {name!r}{newline}")
        updated_source = "".join(lines)
        compile(updated_source, str(path), "exec")

        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="",
                                             dir=path.parent, prefix=f".{path.name}.",
                                             suffix=".tmp", delete=False) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(updated_source)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

        return extend_enum(enum_type, member_name, name)
