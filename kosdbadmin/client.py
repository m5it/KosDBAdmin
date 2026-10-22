"""Socket client for KosDB."""

import json
import os
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
        self._current_database: Optional[str] = None

    def connect(self) -> str:
        """Connect and return the server welcome message."""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.settimeout(30)
        self.socket.connect((self.host, self.port))

        # Server sends a welcome banner plus a help line (often in one packet).
        # We may need to wait briefly or receive two packets.
        welcome = self._receive()
        if welcome is None:
            raise KosDBError("No welcome message from server")
        # If the server split banner and help into two packets, merge them.
        try:
            self.socket.settimeout(0.5)
            extra = self._receive()
            if extra:
                welcome += "\n" + extra
        except Exception:
            pass
        finally:
            self.socket.settimeout(30)
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
        self.authenticated = "OK:" in response and "Welcome" in response
        return self.authenticated

    def enable_json(self) -> bool:
        """Ask server to return query results as JSON."""
        response = self.execute("SET JSON ON")
        self.json_mode = "OK:" in response
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
        self._current_database = db_name

    def _current_db(self) -> Optional[str]:
        return getattr(self, "_current_database", None)

    def _infer_schema(self, table_name: str) -> Optional[Dict[str, Any]]:
        """Infer table schema from a SELECT * query."""
        try:
            self.use_database(self._current_database)
            result = self.execute_query(f"SELECT * FROM {table_name}")
            columns = result.get("columns", [])
            if not columns:
                return None
            return {"columns": columns, "primary_key": None, "indexes": []}
        except Exception:
            return None

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

    def add_column(self, table_name: str, col_name: str, col_type: str,
                   indexed: bool = False, default: str = "") -> str:
        """Add a column by recreating the table with the new schema."""
        return self._alter_table(table_name, "add", {
            "name": col_name,
            "type": col_type,
            "indexed": indexed,
            "default": default
        })

    def rename_column(self, table_name: str, old_name: str, new_name: str) -> str:
        """Rename a column by rewriting every row's key."""
        return self._alter_table(table_name, "rename", {
            "old": old_name,
            "new": new_name
        })

    def drop_column(self, table_name: str, col_name: str) -> str:
        """Drop a column by recreating the table without it."""
        return self._alter_table(table_name, "drop", {"name": col_name})

    def _alter_table(self, table_name: str, operation: str, params: dict) -> str:
        """Client-side ALTER TABLE implementation."""
        import json

        # KosDB has no wire-protocol command to read the schema and the server
        # keeps the LevelDB file locked. Infer the schema from a SELECT * query
        # and treat every column as a regular column (no PK/index metadata).
        schema = self._infer_schema(table_name)
        if not schema:
            raise KosDBError(f"Could not infer schema for table '{table_name}'")

        columns = list(schema.get("columns", []))
        primary_key = schema.get("primary_key")
        indexes = list(schema.get("indexes", []))

        if operation == "add":
            col_name = params["name"]
            if col_name in columns:
                raise KosDBError(f"Column '{col_name}' already exists")
            columns.append(col_name)
            if params.get("indexed") and col_name not in indexes:
                indexes.append(col_name)
        elif operation == "drop":
            col_name = params["name"]
            if col_name not in columns:
                raise KosDBError(f"Column '{col_name}' does not exist")
            if col_name == primary_key:
                raise KosDBError("Cannot drop primary key column")
            columns.remove(col_name)
            if col_name in indexes:
                indexes.remove(col_name)
        elif operation == "rename":
            old_name, new_name = params["old"], params["new"]
            if old_name not in columns:
                raise KosDBError(f"Column '{old_name}' does not exist")
            if new_name in columns:
                raise KosDBError(f"Column '{new_name}' already exists")
            columns[columns.index(old_name)] = new_name
            if old_name in indexes:
                indexes[indexes.index(old_name)] = new_name
            if primary_key == old_name:
                primary_key = new_name

        # Build new CREATE TABLE statement
        col_specs = []
        for col in columns:
            spec = col
            if col == primary_key:
                spec += " PRIMARY KEY"
            if col in indexes:
                spec += " INDEX"
            col_specs.append(spec)

        # Read existing rows (raw JSON, not formatted)
        rows_raw = self.execute(f"SELECT * FROM {table_name}")
        try:
            rows_result = json.loads(rows_raw)
            rows = rows_result.get("rows", [])
        except Exception:
            rows = []

        # Apply schema change: drop old table, create new, re-insert rows
        self.execute_command(f"DROP TABLE {table_name}")
        self.create_table(table_name, col_specs)

        for row in rows:
            if operation == "drop":
                row.pop(params["name"], None)
            elif operation == "rename":
                if params["old"] in row:
                    row[params["new"]] = row.pop(params["old"])
            elif operation == "add":
                if params["name"] not in row:
                    row[params["name"]] = params.get("default", "")

            # Build INSERT with remaining columns
            available_cols = [c for c in columns if c in row]
            if not available_cols:
                continue
            values = [row[c] for c in available_cols]
            col_list = ", ".join(available_cols)
            val_list = ", ".join(self._sql_quote(v) for v in values)
            self.execute_command(f"INSERT INTO {table_name} ({col_list}) VALUES ({val_list})")

        return f"OK: Table '{table_name}' altered"

    @staticmethod
    def _sql_quote(value) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, (list, dict)):
            import json
            return f"'{json.dumps(value).replace(chr(39), chr(39)+chr(39))}'"
        return f"'{str(value).replace(chr(39), chr(39)+chr(39))}'"

    def table_data(self, db_name: str, table_name: str) -> Dict[str, Any]:
        """Return all rows for a table."""
        self.use_database(db_name)
        return self.execute_query(f"SELECT * FROM {table_name}")

    def table_count(self, db_name: str, table_name: str) -> int:
        """Return the number of rows in a table."""
        data = self.table_data(db_name, table_name)
        return data.get("count", len(data.get("rows", [])))
