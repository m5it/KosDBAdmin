#!/usr/bin/env python3
"""Raw socket test."""
import socket

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(5)
s.connect(("localhost", 3306))
print("1:", s.recv(4096))
print("2:", s.recv(4096))
s.sendall(b"LOGIN admin skrlat\n")
print("login:", s.recv(4096))
s.sendall(b"USE testdb\n")
print("use:", s.recv(4096))
s.sendall(b"SHOW TABLES\n")
print("tables:", s.recv(4096))
s.close()
