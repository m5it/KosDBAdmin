#!/usr/bin/env python3
"""Test parser value parsing with escapes via server."""
import sys
sys.path.insert(0, "/home/t3ch/Working/Hobies/KosDBAdmin")

from kosdbadmin.client import KosDBClient

client = KosDBClient("localhost", 3306, "admin", "skrlat")
client.connect()
client.login()
client.use_database("testdb_roundtrip")

# Insert using the exact dumped string
client.execute_command("DROP TABLE items")
client.create_table("items", ["id INTEGER PRIMARY KEY", "name TEXT"])
client.execute_command("INSERT INTO items (id, name) VALUES (2, 'line\\nbreak')")

data = client.execute_query("SELECT * FROM items")
print("row:", data["rows"][0])
print("repr name:", repr(data["rows"][0]["name"]))
client.disconnect()
