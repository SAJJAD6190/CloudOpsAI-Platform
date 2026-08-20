"""Delete and recreate the local demonstration database."""

from pathlib import Path

from app.config import DATA_DIR
from app.database import Base, SessionLocal, engine
from app.seed import seed_demo_data


def main() -> None:
    db_path = DATA_DIR / "cloudopsai.db"
    engine.dispose()
    if db_path.exists():
        db_path.unlink()
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_demo_data(db)
    print(f"Reset complete: {db_path}")


if __name__ == "__main__":
    main()
