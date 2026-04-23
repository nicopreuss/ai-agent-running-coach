"""One-time setup: create all tables defined in db/models.py in the target database."""

from db.client import get_engine
from db.models import Base


def main() -> None:
    engine = get_engine()
    print(f"Connecting to: {engine.url}")
    Base.metadata.create_all(engine)
    tables = list(Base.metadata.tables.keys())
    print(f"Tables created (or already exist): {tables}")


if __name__ == "__main__":
    main()
