"""Create a fresh, isolated database for the synthetic recording demo."""

import argparse
from pathlib import Path

from backend.database import audited_transaction, connect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    args = parser.parse_args()
    # Exclusive creation protects existing databases from accidental overwrite.
    with args.database.open("xb"):
        pass
    db, context = connect(str(args.database))
    try:
        with audited_transaction(db, context, actor="foreman", reason="Set up synthetic demo for recording"):
            db.executemany("INSERT INTO members(id, name) VALUES (?, ?)",
                           [(f"member-{i:02}", f"Member {i:02}") for i in range(1, 21)])
            db.execute("INSERT INTO months(month, due_date) VALUES (3, '2026-03-10')")
    finally:
        db.close()
    print(f"Synthetic demo database created: {args.database}")


if __name__ == "__main__":
    main()
