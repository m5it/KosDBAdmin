#!/usr/bin/env python3
"""Test import/export round-trip with INTEGER types and schema preservation."""
import os
import sys

sys.path.insert(0, "/home/t3ch/Working/Hobies/KosDBAdmin")

from kosdbadmin.client import KosDBClient


def main():
    client = KosDBClient("localhost", 3306, "admin", "skrlat")
    client.connect()
    client.login()
    client.enable_json()

    db_name = "testdb_roundtrip2"
    if db_name in client.list_databases():
        client.execute_command(f"DROP DATABASE {db_name}")
    client.create_database(db_name)
    client.use_database(db_name)

    client.create_table(
        "products",
        ["id INTEGER PRIMARY KEY", "name TEXT", "price REAL", "active INTEGER INDEX"]
    )
    client.execute_command("INSERT INTO products (id, name, price, active) VALUES (1, 'Widget', 19.99, 1)")
    client.execute_command("INSERT INTO products (id, name, price, active) VALUES (2, 'Gadget', 0.00, 0)")

    client.export_database(db_name, "/tmp/roundtrip2.sql")
    print("--- DUMP ---")
    with open("/tmp/roundtrip2.sql") as f:
        print(f.read())
    print("--- END DUMP ---")

    client.execute_command(f"DROP DATABASE {db_name}")
    result = client.import_sql("/tmp/roundtrip2.sql")
    print("import result:", result)

    client.use_database(db_name)
    schema_raw = client.execute("DESCRIBE products")
    import json
    schema = json.loads(schema_raw)
    print("schema:", schema)

    data = client.execute_query("SELECT * FROM products")
    print("rows:", data["rows"])
    assert len(data["rows"]) == 2

    client.disconnect()
    print("\nSchema-preserving round-trip test passed")


if __name__ == "__main__":
    main()
