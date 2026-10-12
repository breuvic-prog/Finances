"""Track review imports so successful finalization can remove only its working files."""

from pathlib import Path


class ReviewFilesManager:
    def __init__(self):
        self._files: dict[Path, Path] = {}

    @staticmethod
    def validate_path(path: str | Path, directory: str | Path) -> Path:
        path = Path(path).absolute()
        directory = Path(directory).resolve()
        resolved = path.resolve()
        if resolved == directory or not resolved.is_relative_to(directory):
            raise ValueError(f"Review file is outside its working directory: {path}")
        return path

    def track_file(self, path: str | Path, directory: str | Path) -> None:
        path = self.validate_path(path, directory)
        self._files[path] = Path(directory).resolve()

    def cleanup(self) -> None:
        """Keep failed deletions pending, allowing cleanup to be retried independently."""
        errors = []
        for path, directory in tuple(self._files.items()):
            try:
                # Recheck the resolved path in case a directory or link changed after import.
                self.validate_path(path, directory)
                path.unlink(missing_ok=True)
            except (OSError, ValueError) as error:
                errors.append(f"{path}: {error}")
            else:
                del self._files[path]
        if errors:
            raise OSError("Could not remove these working files:\n" + "\n".join(errors))
