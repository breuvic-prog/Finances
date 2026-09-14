from datetime import date


class DateManager:
    """Get the local current month and convert English month names and numbers."""

    MONTH_NAMES = (
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    )

    @staticmethod
    def get_current_month() -> int:
        """Return the current local month as a number from 1 to 12."""
        return date.today().month

    @staticmethod
    def get_current_month_name() -> str:
        """Return the current local month's full English name."""
        return DateManager.month_number_to_name(DateManager.get_current_month())

    @staticmethod
    def month_number_to_name(month: int) -> str:
        """Convert an integer from 1 to 12 to its full English month name."""
        if isinstance(month, bool) or not isinstance(month, int):
            raise TypeError("Month number must be an integer.")
        if not 1 <= month <= 12:
            raise ValueError("Month number must be between 1 and 12.")
        return DateManager.MONTH_NAMES[month - 1]

    @staticmethod
    def month_name_to_number(month: str) -> int:
        """Convert a full English month name, ignoring case and outer spaces."""
        if not isinstance(month, str):
            raise TypeError("Month name must be a string.")
        normalized = month.strip().casefold()
        for number, name in enumerate(DateManager.MONTH_NAMES, start=1):
            if name.casefold() == normalized:
                return number
        raise ValueError(f"Unknown month name: {month!r}")
