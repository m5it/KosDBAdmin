#!/usr/bin/env python3
"""Test parser value parsing with escapes."""
import sys
sys.path.insert(0, "/home/t3ch/Working/Hobies/KosDB")

from parser import BackupRestoreParser

p = BackupRestoreParser()

cmd = "INSERT INTO items (id, name) VALUES (2, 'line\\\\nbreak')"
print("input:", cmd)
t, params = p.parse(cmd)
print("parsed values:", params.get('values'))
print("repr:", [repr(v) for v in params.get('values', [])])
