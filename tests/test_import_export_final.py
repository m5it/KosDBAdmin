#!/usr/bin/env python3
"""Final import/export round-trip test."""
import os
import sys

sys.path.insert(0, "/home/t3ch/Working/Hobies/KosDBAdmin")

from kosdbadmin.client import KosDBClient


def main():
    client = KosDBClient("localhost", 3306, "admin", "skrlat")
    client.connect()
    client.login()
    client.enable_json()

    db_name = "testdb_roundtrip_final"
    if db_name in client.list_databases():
        client.execute_command(f"DROP DATABASE {db_name}")
    client.create_database(db_name)
    client.use_database(db_name)

    client.create_table(
        "items",
        ["id INTEGER PRIMARY KEY", "name TEXT", "count INTEGER", "note TEXT INDEX"]
    )

    # Tricky values
    client.execute_command("INSERT INTO items (id, name, count, note) VALUES (1, 'hello; world', 42, 'not -- a comment')")
    client.execute_command(r"INSERT INTO items (id, name, count, note) VALUES (2, 'line\nbreak', 7, 'value with /* block */ inside')")
    client.execute_command("INSERT INTO items (id, name, count) VALUES (3, 'no note', 0)")

    client.export_database(db_name, "/tmp/roundtrip_final.sql")
    with open("/tmp/roundtrip_final.sql") as f:
        print(f.read())

    client.execute_command(f"DROP DATABASE {db_name}")
    result = client.import_sql("/tmp/roundtrip_final.sql")
    print("import:", result)

    client.use_database(db_name)
    data = client.execute_query("SELECT * FROM items")
    print("rows:", data["rows"])
    assert len(data["rows"]) == 3

    client.disconnect()
    print("Final round-trip test passed")


if __name__ == "__main__":
    main()
