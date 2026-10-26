#!/usr/bin/env python3
"""Headless smoke test for KosDBAdmin widgets."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication
from kosdbadmin.client import KosDBClient
from kosdbadmin.tree_panel import TreePanel
from kosdbadmin.query_widget import QueryWidget
from kosdbadmin.table_browser import TableBrowser


def main():
    app = QApplication(sys.argv)

    client = KosDBClient("localhost", 3306, "admin", "skrlat")
    client.connect()
    if not client.login():
        print("Login failed")
        return 1
    client.enable_json()

    # Ensure a test database exists
    try:
        client.create_database("testdb_smoke")
    except Exception:
        pass
    dbs = client.list_databases()
    if "testdb_smoke" not in dbs:
        client.create_database("testdb_smoke")
    client.use_database("testdb_smoke")
    try:
        client.create_table("smoke_table", ["id INTEGER PRIMARY KEY", "value TEXT"])
    except Exception:
        pass
    try:
        client.execute_command("DELETE FROM smoke_table")
    except Exception:
        pass
    client.execute_command("INSERT INTO smoke_table (id, value) VALUES (1, 'hello')")

    tree = TreePanel(client)
    tree.refresh()
    assert tree.root.childCount() >= 1, "Tree has no databases"

    query = QueryWidget(client)
    query.set_default_query("SELECT * FROM smoke_table")
    query.run_query()
    assert query.result_table.rowCount() >= 1, "Query returned no rows"

    # Test fully qualified name and backticks
    for q in ["SELECT * FROM testdb_smoke.smoke_table",
              "SELECT * FROM `testdb_smoke`.`smoke_table`"]:
        query.set_default_query(q)
        query.run_query()
        assert query.result_table.rowCount() >= 1, f"Fully qualified query failed: {q}"

    browser = TableBrowser(client)
    browser.load("testdb_smoke", "smoke_table")
    assert browser.data_tab.table.rowCount() >= 1, "Table browser has no rows"

    # Test client export/import
    client.export_database("testdb_smoke", "/tmp/admin_smoke_export.sql")
    client.import_sql("/tmp/admin_smoke_export.sql")

    # Test Tools-style db.table export
    client.export_table("testdb_smoke", "smoke_table", "/tmp/admin_tools_export.sql")

    client.disconnect()
    print("Smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
