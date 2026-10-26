#!/usr/bin/env python3
"""Debug raw socket framing."""
import socket

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(5)
s.connect(("localhost", 3306))
print("welcome:", s.recv(4096))
s.sendall(b"LOGIN admin skrlat\n")
print("login:", s.recv(4096))
s.sendall(b"SET FRAMING ON\n")
print("framing:", s.recv(4096))
# Consume any leftover bytes
s.settimeout(0.2)
try:
    print("extra:", s.recv(4096))
except Exception as e:
    print("no extra:", e)
s.settimeout(5)

cmd = b"SHOW DATABASES"
s.sendall(f"{len(cmd)}\n".encode() + cmd)
# Read header
header = b""
while True:
    ch = s.recv(1)
    if not ch or ch == b"\n":
        break
    header += ch
print("show header:", header)
length = int(header.decode().strip())
print("show length:", length)
data = b""
while len(data) < length:
    chunk = s.recv(length - len(data))
    if not chunk:
        break
    data += chunk
print("show:", data)
s.close()
