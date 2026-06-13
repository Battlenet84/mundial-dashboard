from app.config.settings import DB_PATH
from app.db.connection import init_db


def main() -> None:
    init_db()
    print(f"Base SQLite inicializada: {DB_PATH}")


if __name__ == "__main__":
    main()

