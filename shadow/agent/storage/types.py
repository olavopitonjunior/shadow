from dataclasses import dataclass


@dataclass
class Task:
    id: int | str
    title: str
    due_at: str | None
    status: str


@dataclass
class Appointment:
    id: int | str
    title: str
    scheduled_at: str
    duration_minutes: int
