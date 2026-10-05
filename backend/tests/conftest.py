import os
import tempfile

# Point the app at a throwaway SQLite file BEFORE any app module is imported,
# so tests never touch the real Postgres database.
os.environ.setdefault(
    "DATABASE_URL",
    "sqlite:///" + os.path.join(tempfile.mkdtemp(prefix="hallspan-test-"), "test.db"),
)
