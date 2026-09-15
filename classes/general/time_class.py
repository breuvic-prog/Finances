"""Imports"""



class Time:
    def __init__(self, hours:int,
                 minutes:int,
                 seconds:int):
        self._hours = hours
        self._minutes = minutes
        self._seconds = seconds

    @property
    def hours(self):
        return self._hours
    @property
    def minutes(self):
        return self._minutes
    @property
    def seconds(self):
        return self._seconds

    def __str__(self):
        return f"Hours: {self.hours}, Minutes: {self.minutes}, Seconds: {self.seconds}"