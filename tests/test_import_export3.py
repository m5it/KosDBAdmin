#!/usr/bin/env python3
"""Test import/export round-trip with newly created table after schema change."""
import os
import sys

sys.path.insert(0, "/home/t3ch/Working/Hobies/KosDBAdmin")

from kosdbadmin.client import KosDBClient


def main():
    client = KosDBClient("localhost", 3306, "admin", "skrlat")
    client.connect()
    client.login()
    client.enable_json()

    db_name = "testdb_roundtrip3"
    if db_name in client.list_databases():
        client.execute_command(f"DROP DATABASE {db_name}")
    client.create_database(db_name)
    client.use_database(db_name)

    client.create_table(
        "products",
        ["id INTEGER PRIMARY KEY", "name TEXT", "price REAL", "active INTEGER INDEX"]
    )

    import json
    schema_raw = client.execute("DESCRIBE products")
    schema = json.loads(schema_raw)
    print("original schema:", schema)
    print("original column_types:", schema.get("column_types"))

    client.export_database(db_name, "/tmp/roundtrip3.sql")
    print("--- DUMP ---")
    with open("/tmp/roundtrip3.sql") as f:
        print(f.read())
    print("--- END DUMP ---")

    client.execute_command(f"DROP DATABASE {db_name}")
    client.import_sql("/tmp/roundtrip3.sql")
    client.use_database(db_name)

    schema_raw = client.execute("DESCRIBE products")
    schema = json.loads(schema_raw)
    print("restored schema:", schema)
    print("restored column_types:", schema.get("column_types"))

    assert schema.get("column_types", {}).get("id") == "INTEGER"
    assert schema.get("column_types", {}).get("price") == "REAL"
    assert schema.get("column_types", {}).get("active") == "INTEGER"

    client.disconnect()
    print("\nType-preserving round-trip test passed")


if __name__ == "__main__":
    main()
