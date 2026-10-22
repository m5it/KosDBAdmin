"""Socket client for KosDB."""

import json
import socket
from typing import Any, Dict, List, Optional, Tuple


class KosDBError(Exception):
    """Raised when KosDB returns an error."""
    pass


class KosDBClient:
    """TCP socket client for KosDB command protocol."""

    def __init__(self, host: str = "localhost", port: int = 5555,
                 username: str = "", password: str = ""):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.socket: Optional[socket.socket] = None
        self.authenticated = False
        self.json_mode = False

    def connect(self) -> str:
        """Connect and return the server welcome message."""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.settimeout(30)
        self.socket.connect((self.host, self.port))

        # Server sends a welcome banner plus a help line (often in one packet).
        welcome = self._receive()
        if welcome is None:
            raise KosDBError("No welcome message from server")
        return welcome

    def disconnect(self):
        """Close the connection."""
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            finally:
                self.socket = None
                self.authenticated = False
                self.json_mode = False

    def login(self) -> bool:
        """Authenticate with LOGIN command."""
        response = self.execute(f"LOGIN {self.username} {self.password}")
        self.authenticated = response.startswith("OK:")
        return self.authenticated

    def enable_json(self) -> bool:
        """Ask server to return query results as JSON."""
        response = self.execute("SET JSON ON")
        self.json_mode = response.startswith("OK:")
        return self.json_mode

    def execute(self, command: str) -> str:
        """Send a single command and return the raw text response."""
        if not self.socket:
            raise KosDBError("Not connected")

        try:
            self.socket.sendall(command.encode() + b"\n")
        except Exception as e:
            raise KosDBError(f"Failed to send command: {e}")

        response = self._receive()
        if response is None:
            raise KosDBError("No response from server")
        return response

    def _send(self, message: str):
        if not self.socket:
            raise KosDBError("Not connected")
        self.socket.sendall(message.encode() + b"\n")

    def _receive(self) -> Optional[str]:
        if not self.socket:
            return None
        try:
            data = self.socket.recv(65536)
            if not data:
                return None
            return data.decode("utf-8", errors="replace").strip()
        except socket.timeout:
            raise KosDBError("Connection timeout")
        except Exception as e:
            raise KosDBError(f"Failed to receive: {e}")

    def _receive_line(self) -> Optional[str]:
        """Receive a single line terminated by \\n."""
        if not self.socket:
            return None
        try:
            data = self.socket.recv(4096)
            if not data:
                return None
            return data.decode("utf-8", errors="replace").strip()
        except Exception as e:
            raise KosDBError(f"Failed to receive line: {e}")

    def execute_query(self, query: str) -> Dict[str, Any]:
        """Execute a SELECT-like query and return parsed JSON result."""
        if not self.json_mode:
            self.enable_json()

        raw = self.execute(query)
        if raw.startswith("ERROR:"):
            raise KosDBError(raw)

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            # Fallback: treat as plain text result (non-tabular)
            parsed = {"columns": ["result"], "rows": [{"result": raw}], "count": 1}
            return parsed

        # Work around server bug: SELECT * returns columns=["*"].
        rows = parsed.get("rows", [])
        columns = parsed.get("columns", [])
        if columns == ["*"] and rows:
            parsed["columns"] = list(rows[0].keys())
        return parsed

    def execute_command(self, command: str) -> str:
        """Execute a non-query command and return status text."""
        raw = self.execute(command)
        if raw.startswith("ERROR:"):
            raise KosDBError(raw)
        return raw

    def list_databases(self) -> List[str]:
        """Return list of database names."""
        raw = self.execute("SHOW DATABASES")
        if raw.startswith("ERROR:"):
            raise KosDBError(raw)
        prefix = "OK:\n"
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
        if raw in ("OK: No databases", ""):
            return []
        return [line.strip() for line in raw.splitlines() if line.strip()]

    def use_database(self, db_name: str):
        """Select a database."""
        self.execute_command(f"USE {db_name}")

    def list_tables(self, db_name: Optional[str] = None) -> List[str]:
        """Return list of table names in the current or given database."""
        if db_name:
            self.use_database(db_name)
        raw = self.execute("SHOW TABLES")
        if raw.startswith("ERROR:"):
            raise KosDBError(raw)
        prefix = "OK:\n"
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
        if raw in ("OK: No tables", ""):
            return []
        return [line.strip() for line in raw.splitlines() if line.strip()]

    def create_database(self, db_name: str) -> str:
        return self.execute_command(f"CREATE DATABASE {db_name}")

    def drop_database(self, db_name: str) -> str:
        return self.execute_command(f"DROP DATABASE {db_name}")

    def create_table(self, name: str, columns: List[str]) -> str:
        col_spec = ", ".join(columns) if columns else "id INTEGER PRIMARY KEY"
        return self.execute_command(f"CREATE TABLE {name} ({col_spec})")

    def drop_table(self, name: str) -> str:
        return self.execute_command(f"DROP TABLE {name}")

    def table_data(self, db_name: str, table_name: str) -> Dict[str, Any]:
        """Return all rows for a table."""
        self.use_database(db_name)
        return self.execute_query(f"SELECT * FROM {table_name}")

    def table_count(self, db_name: str, table_name: str) -> int:
        """Return the number of rows in a table."""
        data = self.table_data(db_name, table_name)
        return data.get("count", len(data.get("rows", [])))
