import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.models import init_database


def main():
    parser = argparse.ArgumentParser(description="Install schema and upsert the default accounts.")
    parser.add_argument("--test", action="store_true", help="use TEST_DATABASE_URL")
    args = parser.parse_args()
    app = create_app("testing" if args.test else None)
    init_database(app)
    print("Database initialized with 3 default accounts.")


if __name__ == "__main__":
    main()
