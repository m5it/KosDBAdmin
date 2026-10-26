#!/usr/bin/env python3
"""Test local schema storage."""
import sys
sys.path.insert(0, "/home/t3ch/Working/Hobies/KosDB")

from database import Database

db = Database("/home/t3ch/Working/Hobies/KosDB/data")
db.use_database("testdb_roundtrip3")
schema = db.get_schema("products")
print("local schema:", schema)
print("column_types:", schema.get("column_types"))
