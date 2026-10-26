#!/usr/bin/env python3
"""Test import/export round-trip directly via local exporter/importer."""
import os
import sys

sys.path.insert(0, "/home/t3ch/Working/Hobies/KosDB")

from database import Database
from export_import import KosDBExporter, KosDBImporter

DATA_DIR = "/home/t3ch/Working/Hobies/KosDB/data"

db = Database(DATA_DIR)
if "testdb_roundtrip" in db.list_databases():
    db.drop_database("testdb_roundtrip")
db.create_database("testdb_roundtrip")
db.use_database("testdb_roundtrip")
db.create_table("items", ["id INTEGER PRIMARY KEY", "name TEXT", "count INTEGER", "note TEXT INDEX"])
db.insert_with_columns("items", ["id", "name", "count", "note"], [1, "hello; world", 42, "not -- a comment"])
db.insert_with_columns("items", ["id", "name", "count", "note"], [2, "line\nbreak", 7, "value with /* block */ inside"])
db.insert_with_columns("items", ["id", "name", "count"], [3, "no note", 0])

exporter = KosDBExporter(DATA_DIR)
print(exporter.export("testdb_roundtrip", "/tmp/roundtrip_direct.sql"))
with open("/tmp/roundtrip_direct.sql") as f:
    print(f.read())
exporter.close()

db.drop_database("testdb_roundtrip")

importer = KosDBImporter(DATA_DIR)
print(importer.import_sql("/tmp/roundtrip_direct.sql"))
importer.close()

db.use_database("testdb_roundtrip")
rows = db.select("items", raw=True)
print("rows:", rows)
assert len(rows) == 3
names = {r["name"] for r in rows}
assert "hello; world" in names
assert "line\nbreak" in names

db.close()
print("Direct round-trip test passed")
