import sqlite3
import sys
from pathlib import Path


TABLES = ["user", "study", "enrollment", "comment", "comment_likes", "chat_message"]


def quote_sql(value):
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("'", "''")
    return f"'{text}'"


def export_table(cursor, table_name):
    rows = cursor.execute(f"SELECT * FROM {table_name}").fetchall()
    if not rows:
        return []
    columns = [description[0] for description in cursor.description]
    prefix = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES"
    statements = []
    for row in rows:
        values = ", ".join(quote_sql(value) for value in row)
        statements.append(f"{prefix} ({values});")
    return statements


def main():
    if len(sys.argv) != 2:
        print("Usage: python cloudflare/export_sqlite_to_d1.py <sqlite-db-path>")
        raise SystemExit(1)

    db_path = Path(sys.argv[1]).resolve()
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        raise SystemExit(1)

    connection = sqlite3.connect(str(db_path))
    cursor = connection.cursor()

    print("PRAGMA foreign_keys = OFF;")
    for table in TABLES:
        for statement in export_table(cursor, table):
            print(statement)
    print("PRAGMA foreign_keys = ON;")

    connection.close()


if __name__ == "__main__":
    main()