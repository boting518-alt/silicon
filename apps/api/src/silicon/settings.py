import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    database_url: str = field(repr=False)
    environment: str = "development"

    def __post_init__(self):
        if self.environment not in {"development", "test"}:
            raise ValueError("TASK-001 supports development/test only; production identity is not implemented")
        if not self.database_url.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must use postgresql+psycopg")

    @classmethod
    def from_env(cls):
        return cls(os.environ["DATABASE_URL"], os.getenv("SILICON_ENV", "development"))
