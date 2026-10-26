#!/usr/bin/env python3
"""Test parser value parsing with escapes."""
import sys
sys.path.insert(0, "/home/t3ch/Working/Hobies/KosDB")

from parser import BackupRestoreParser

p = BackupRestoreParser()

tests = [
    ("INSERT INTO t (a) VALUES ('line\\nbreak')", ['line\nbreak']),
    ("INSERT INTO t (a) VALUES ('hello; world')", ['hello; world']),
    ("INSERT INTO t (a) VALUES ('not -- a comment')", ['not -- a comment']),
    ("INSERT INTO t (a, b) VALUES ('a\\nb', 'c\\rd')", ['a\nb', 'c\rd']),
]

for cmd, expected in tests:
    t, params = p.parse(cmd)
    got = params.get('values')
    print(repr(cmd), "=>", got)
    assert got == expected, f"expected {expected}, got {got}"

print("Parser value tests passed")
