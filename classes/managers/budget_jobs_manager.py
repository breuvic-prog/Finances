"""Store reusable budget jobs separately from temporary expense-review imports."""

import json
import os
from pathlib import Path
import tempfile

from classes.budget_job_class import BudgetJob


_JOBS_PATH = Path(__file__).resolve().parents[2] / "assets" / "jsons" / "budget_jobs.json"


class BudgetJobsManager:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else _JOBS_PATH

    def load(self) -> list[BudgetJob]:
        if not self.path.exists():
            return []
        try:
            record = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(record, dict) or record.get("version") != 1 or not isinstance(record.get("jobs"), list):
                raise ValueError("Invalid saved jobs format.")
            jobs = [BudgetJob.from_dict(job) for job in record["jobs"]]
            if len({job.job_id for job in jobs}) != len(jobs):
                raise ValueError("Saved jobs contain duplicate identifiers.")
            return jobs
        except (ValueError, TypeError) as error:
            raise ValueError(f"Could not read saved jobs: {error}") from error

    def save(self, jobs: list[BudgetJob]) -> None:
        if len({job.job_id for job in jobs}) != len(jobs):
            raise ValueError("Jobs must have unique identifiers.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=self.path.parent,
                                             prefix=".budget-jobs-", suffix=".tmp", delete=False) as temporary:
                temporary_path = Path(temporary.name)
                json.dump({"version": 1, "jobs": [job.to_dict() for job in jobs]}, temporary,
                          ensure_ascii=False, indent=2)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
