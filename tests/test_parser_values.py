#!/usr/bin/env python3
"""Test parser value parsing with escapes."""
import sys
sys.path.insert(0, "/home/t3ch/Working/Hobies/KosDB")

from parser import BackupRestoreParser

p = BackupRestoreParser()

tests = [
    "INSERT INTO t (a) VALUES ('line\\nbreak')",
    "INSERT INTO t (a) VALUES ('hello; world')",
    "INSERT INTO t (a) VALUES ('not -- a comment')",
    "INSERT INTO t (a, b) VALUES ('a\\nb', 'c\\rd')",
]

for cmd in tests:
    t, params = p.parse(cmd)
    print(t, params.get('values'))
