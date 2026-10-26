#!/usr/bin/env python3
"""Test import/export round-trip with semicolons and comments in values."""
import os
import sys

sys.path.insert(0, "/home/t3ch/Working/Hobies/KosDBAdmin")

from kosdbadmin.client import KosDBClient


def main():
    client = KosDBClient("localhost", 3306, "admin", "skrlat")
    client.connect()
    client.login()
    client.enable_json()

    # Use a clean database
    db_name = "testdb_roundtrip"
    if db_name in client.list_databases():
        client.execute_command(f"DROP DATABASE {db_name}")
    client.create_database(db_name)
    client.use_database(db_name)

    # Create table with non-id types
    client.create_table(
        "items",
        ["id INTEGER PRIMARY KEY", "name TEXT", "count INTEGER", "note TEXT INDEX"]
    )

    # Insert tricky values
    client.execute_command("INSERT INTO items (id, name, count, note) VALUES (1, 'hello; world', 42, 'not -- a comment')")
    client.execute_command(r"INSERT INTO items (id, name, count, note) VALUES (2, 'line\nbreak', 7, 'value with /* block */ inside')")
    client.execute_command("INSERT INTO items (id, name, count) VALUES (3, 'no note', 0)")

    # Export and re-import
    client.export_database(db_name, "/tmp/roundtrip.sql")
    print("--- DUMP ---")
    with open("/tmp/roundtrip.sql") as f:
        print(f.read())
    print("--- END DUMP ---")

    # Drop database and re-import
    client.execute_command(f"DROP DATABASE {db_name}")
    result = client.import_sql("/tmp/roundtrip.sql")
    print("import result:", result)

    client.use_database(db_name)
    data = client.execute_query("SELECT * FROM items")
    print("rows after import:", data["rows"])
    assert len(data["rows"]) == 3
    names = {r["name"] for r in data["rows"]}
    assert "hello; world" in names
    assert "line\nbreak" in names

    client.disconnect()
    print("\nImport/export round-trip test passed")


if __name__ == "__main__":
    main()
