#!/usr/bin/env python3
"""Test server-side LIMIT/OFFSET and client pagination."""
import sys

sys.path.insert(0, "/home/t3ch/Working/Hobies/KosDBAdmin")

from kosdbadmin.client import KosDBClient


def main():
    client = KosDBClient("localhost", 3306, "admin", "skrlat")
    client.connect()
    client.login()
    client.enable_json()

    db_name = "testdb_pagination"
    if db_name in client.list_databases():
        client.execute_command(f"DROP DATABASE {db_name}")
    client.create_database(db_name)
    client.use_database(db_name)
    client.create_table("nums", ["id INTEGER PRIMARY KEY", "n INTEGER"])

    for i in range(1, 101):
        client.execute_command(f"INSERT INTO nums (id, n) VALUES ({i}, {i})")

    # Test LIMIT/OFFSET
    page1 = client.execute_query("SELECT * FROM nums ORDER BY id ASC LIMIT 10 OFFSET 0")
    page2 = client.execute_query("SELECT * FROM nums ORDER BY id ASC LIMIT 10 OFFSET 10")
    print("page1 rows:", [r["n"] for r in page1["rows"]])
    print("page2 rows:", [r["n"] for r in page2["rows"]])
    print("page1 total:", page1.get("total"))
    assert len(page1["rows"]) == 10
    assert len(page2["rows"]) == 10
    assert page1["rows"][0]["n"] == 1
    assert page2["rows"][0]["n"] == 11
    assert page1.get("total") == 100

    # Test client table_data pagination with explicit ordering
    data = client.table_data(db_name, "nums", limit=25, offset=50, order_by="id")
    print("page at offset 50:", [r["n"] for r in data["rows"]])
    assert len(data["rows"]) == 25
    assert data["total"] == 100
    assert data["rows"][0]["n"] == 51

    # Test table_count
    count = client.table_count(db_name, "nums")
    print("table_count:", count)
    assert count == 100

    client.execute_command(f"DROP DATABASE {db_name}")
    client.disconnect()
    print("Pagination test passed")


if __name__ == "__main__":
    main()
