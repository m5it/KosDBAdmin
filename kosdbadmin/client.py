"""Socket client for KosDB."""

import json
import os
import socket
import ssl
import time
from typing import Any, Dict, List, Optional, Tuple


class KosDBError(Exception):
    """Raised when KosDB returns an error."""
    pass


class KosDBClient:
    """TCP socket client for KosDB command protocol."""

    def __init__(self, host: str = "localhost", port: int = 3306,
                 username: str = "", password: str = "",
                 use_tls: bool = False, tls_cert: Optional[str] = None,
                 tls_require_valid: bool = True):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.tls_cert = tls_cert
        self.tls_require_valid = tls_require_valid
        self.socket: Optional[socket.socket] = None
        self.authenticated = False
        self.json_mode = False
        self.framing = False
        self._current_database: Optional[str] = None

    def connect(self) -> str:
        """Connect and return the server welcome message."""
        plain_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        plain_socket.settimeout(5)
        plain_socket.connect((self.host, self.port))

        if self.use_tls:
            context = ssl.create_default_context()
            if self.tls_cert:
                context.load_verify_locations(self.tls_cert)
            if not self.tls_require_valid:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            self.socket = context.wrap_socket(
                plain_socket, server_hostname=self.host
            )
        else:
            self.socket = plain_socket

        # The server sends the welcome banner and help line as one or two
        # newline-terminated lines. Read enough to get both, leaving extra bytes
        # buffered for later reads.
        buffer = b""
        while buffer.count(b"\n") < 2:
            try:
                chunk = self.socket.recv(4096)
            except socket.timeout:
                break
            except ssl.SSLWantReadError:
                # TLS handshake still in progress; wait briefly and retry.
                time.sleep(0.01)
                continue
            except Exception as e:
                raise KosDBError(f"Failed to receive: {e}")
            if not chunk:
                break
            buffer += chunk
        if not buffer:
            raise KosDBError("No welcome message from server")
        lines = buffer.splitlines()
        if len(lines) > 2:
            self._read_buffer = b"\n".join(lines[2:]) + b"\n"
            lines = lines[:2]
        else:
            self._read_buffer = b""
        welcome = "\n".join(line.decode("utf-8", errors="replace").strip()
                            for line in lines)
        self.socket.settimeout(None)
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
                self.framing = False

    def is_encrypted(self) -> bool:
        """Return True if the current connection uses TLS."""
        return isinstance(self.socket, ssl.SSLSocket)

    def login(self) -> bool:
        """Authenticate with LOGIN command."""
        if not self.is_encrypted() and not self._is_loopback():
            raise KosDBError(
                "Refusing to send credentials over plain TCP to a remote host. "
                "Enable TLS (use_tls=True) or connect via a secure tunnel."
            )
        response = self.execute(f"LOGIN {self.username} {self.password}")
        self.authenticated = "OK:" in response and "Welcome" in response
        if self.authenticated:
            # Prefer framed protocol when the server supports it.
            try:
                self.enable_framing()
            except Exception:
                self.framing = False
        return self.authenticated

    def _is_loopback(self) -> bool:
        """Return True if the configured host resolves to a loopback address."""
        if self.host in ("localhost", "127.0.0.1", "::1", "::ffff:127.0.0.1"):
            return True
        try:
            addr = socket.getaddrinfo(self.host, None)[0][4][0]
            return addr.startswith("127.") or addr == "::1" or addr == "::ffff:127."
        except Exception:
            return False

    def enable_json(self) -> bool:
        """Ask server to return query results as JSON."""
        response = self.execute("SET JSON ON")
        self.json_mode = "OK:" in response
        return self.json_mode

    def enable_framing(self) -> bool:
        """Ask server to use length-prefixed response framing."""
        response = self.execute("SET FRAMING ON")
        self.framing = "enabled" in response.lower()
        return self.framing

    def execute(self, command: str) -> str:
        """Send a single command and return the raw text response."""
        if not self.socket:
            raise KosDBError("Not connected")

        self._send(command)

        response = self._receive()
        if response is None:
            raise KosDBError("No response from server")
        return response

    def _send(self, message: str):
        if not self.socket:
            raise KosDBError("Not connected")
        payload = message.encode()
        if self.framing:
            header = f"{len(payload)}\n".encode()
            self.socket.sendall(header + payload + b"\n")
        else:
            self.socket.sendall(payload + b"\n")

    def _receive(self) -> Optional[str]:
        if not self.socket:
            return None
        if self.framing:
            return self._receive_framed()
        return self._receive_all()


    def _receive_all(self) -> Optional[str]:
        """Read all data available for a line-based server response."""
        if not self.socket:
            return None
        buffer = getattr(self, "_read_buffer", b"")
        self._read_buffer = b""
        # The server sends each complete response in one burst. Read until no
        # more data arrives for a short interval. TLS sockets may raise
        # SSLWantReadError during the initial handshake, so retry briefly.
        self.socket.settimeout(0.1)
        try:
            while True:
                try:
                    chunk = self.socket.recv(4096)
                except socket.timeout:
                    break
                except ssl.SSLWantReadError:
                    time.sleep(0.01)
                    continue
                if not chunk:
                    break
                buffer += chunk
        finally:
            self.socket.settimeout(None)
        if not buffer:
            return None
        return buffer.decode("utf-8", errors="replace").strip()

    def _read_until(self, marker: bytes) -> bytes:
        """Read from the socket until marker is seen; leftover bytes are buffered."""
        buffer = getattr(self, "_read_buffer", b"")
        self._read_buffer = b""
        while marker not in buffer:
            try:
                chunk = self.socket.recv(4096)
            except socket.timeout:
                raise KosDBError("Connection timeout")
            except Exception as e:
                raise KosDBError(f"Failed to receive: {e}")
            if not chunk:
                raise KosDBError("Server closed connection")
            buffer += chunk
        result, _, leftover = buffer.partition(marker)
        if leftover:
            self._read_buffer = leftover
        return result

    def _receive_line(self) -> Optional[str]:
        """Receive a single line terminated by \\n."""
        if not self.socket:
            return None
        data = self._read_until(b"\n")
        if data is None:
            return None
        return data.decode("utf-8", errors="replace").strip()

    def _receive_framed(self) -> Optional[str]:
        """Receive a length-prefixed framed response."""
        if not self.socket:
            return None
        header = self._read_until(b"\n")
        if not header:
            return None
        try:
            length = int(header.decode("utf-8", errors="replace").strip())
        except ValueError:
            raise KosDBError("Invalid framing header from server")
        if length < 0:
            raise KosDBError("Invalid framing length from server")

        # Read exactly length bytes.
        buffer = getattr(self, "_read_buffer", b"")
        self._read_buffer = b""
        while len(buffer) < length:
            try:
                chunk = self.socket.recv(max(4096, length - len(buffer)))
            except socket.timeout:
                raise KosDBError("Connection timeout")
            except Exception as e:
                raise KosDBError(f"Failed to receive: {e}")
            if not chunk:
                raise KosDBError("Server closed connection during framed response")
            buffer += chunk

        payload = buffer[:length]
        leftover = buffer[length:]
        # The server terminates each framed payload with a newline. Consume it.
        if leftover.startswith(b"\n"):
            leftover = leftover[1:]
        else:
            try:
                delim = self.socket.recv(1)
            except socket.timeout:
                raise KosDBError("Connection timeout")
            except Exception as e:
                raise KosDBError(f"Failed to receive: {e}")
            if delim and delim != b"\n":
                # Misbehaving server; keep the byte for the next read.
                leftover += delim
        if leftover:
            self._read_buffer = leftover
        return payload.decode("utf-8", errors="replace")

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
        # Server formats as "OK:\n" followed by one database per line.
        prefix = "OK:\n"
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
        elif raw.startswith("OK:"):
            raw = raw[len("OK:"):].lstrip()
        if raw.startswith("OK: No databases") or raw == "":
            return []
        return [line.strip() for line in raw.splitlines() if line.strip()]

    def use_database(self, db_name: str):
        """Select a database."""
        self.execute_command(f"USE {db_name}")
        self._current_database = db_name

    def _current_db(self) -> Optional[str]:
        return getattr(self, "_current_database", None)

    def _infer_schema(self, table_name: str) -> Optional[Dict[str, Any]]:
        """Read table schema via DESCRIBE, fall back to SELECT *."""
        try:
            self.use_database(self._current_database)
            raw = self.execute(f"DESCRIBE {table_name}")
            if raw.startswith("ERROR:"):
                raise KosDBError(raw)
            schema = json.loads(raw)
            if schema:
                return schema
        except Exception:
            pass

        # Fallback: infer from data rows
        try:
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
        elif raw.startswith("OK:"):
            raw = raw[len("OK:"):].lstrip()
        if raw.startswith("OK: No tables") or raw == "":
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

    def alter_table(self, table_name: str, columns: list, primary_key: str = None,
                    indexes: list = None, next_id: int = None,
                    column_renames: Optional[Dict[str, str]] = None) -> str:
        """Safely rebuild a table with a new column layout.

        The original table is kept intact until all rows have been copied into a
        temporary table. If any read, transform, or insert step fails, the
        original table is left untouched (the temp table is dropped on failure).

        Args:
            table_name: Table to alter.
            columns: List of column names in the desired order.
            primary_key: Name of the primary key column, if any.
            indexes: List of indexed column names.
            next_id: Optional next auto-increment value to restore.
            column_renames: Mapping of new column name -> old column name. Used
                to copy values from old column names into renamed columns.
        """
        indexes = list(indexes or [])
        column_renames = dict(column_renames or {})

        schema = self._infer_schema(table_name)
        if not schema:
            raise KosDBError(f"Could not infer schema for table '{table_name}'")

        old_next_id = schema.get("next_id", 1)

        # Build column specs for CREATE TABLE.
        col_specs = []
        for col in columns:
            spec = col
            if col == primary_key:
                spec += " PRIMARY KEY"
            if col in indexes:
                spec += " INDEX"
            col_specs.append(spec)

        # Read existing rows. A decode error must abort before we touch the
        # original table.
        rows_raw = self.execute(f"SELECT * FROM {table_name}")
        if rows_raw.startswith("ERROR:"):
            raise KosDBError(f"Failed to read table '{table_name}': {rows_raw}")
        try:
            rows = json.loads(rows_raw).get("rows", [])
        except json.JSONDecodeError as e:
            raise KosDBError(
                f"Failed to parse table data for '{table_name}': {e}. "
                "Table was not modified."
            )

        # Build the transformed row set in memory first.
        transformed_rows = []
        for row in rows:
            new_row = {}
            for new_col in columns:
                old_col = column_renames.get(new_col, new_col)
                if old_col in row:
                    new_row[new_col] = row[old_col]
            if new_row:
                transformed_rows.append(new_row)

        # Use a unique temporary table as a safe copy of the transformed data.
        temp_name = f"_tmp_alter_{table_name}_{int(time.time())}"
        try:
            self.create_table(temp_name, col_specs)
        except KosDBError as e:
            raise KosDBError(
                f"Failed to create temp table '{temp_name}': {e}. "
                f"Table '{table_name}' was not modified."
            )

        try:
            # Populate the temp table. If this fails, the original is safe.
            for row in transformed_rows:
                available_cols = [c for c in columns if c in row]
                values = [row[c] for c in available_cols]
                col_list = ", ".join(available_cols)
                val_list = ", ".join(self._sql_quote(v) for v in values)
                self.execute_command(
                    f"INSERT INTO {temp_name} ({col_list}) VALUES ({val_list})"
                )

            # Only after temp table is fully populated do we drop the original.
            self.execute_command(f"DROP TABLE {table_name}")
            self.create_table(table_name, col_specs)

            # Copy the transformed data from temp into the new original table.
            temp_rows = self.execute_query(f"SELECT * FROM {temp_name}").get("rows", [])
            for row in temp_rows:
                available_cols = [c for c in columns if c in row]
                if not available_cols:
                    continue
                values = [row[c] for c in available_cols]
                col_list = ", ".join(available_cols)
                val_list = ", ".join(self._sql_quote(v) for v in values)
                self.execute_command(
                    f"INSERT INTO {table_name} ({col_list}) VALUES ({val_list})"
                )

            # Restore next_id.
            target_next_id = next_id if next_id is not None else old_next_id
            if target_next_id > 1:
                self.execute_command(f"SET TABLE {table_name} next_id {target_next_id}")

        except Exception:
            # On any failure after the original table was dropped, leave the
            # temp table in place so the data can be recovered manually.
            # If the original still exists (failure happened before DROP),
            # drop the temp table to avoid clutter.
            try:
                self.execute(f"SELECT * FROM {table_name}")
            except KosDBError:
                # Original table is gone; keep temp for recovery.
                raise KosDBError(
                    f"Alter failed after dropping '{table_name}'. "
                    f"Recovery data may be in '{temp_name}'."
                )
            try:
                self.execute_command(f"DROP TABLE {temp_name}")
            except KosDBError:
                pass
            raise
        finally:
            # Drop temp only if the original table was successfully recreated.
            try:
                self.execute(f"SELECT * FROM {table_name}")
                self.execute_command(f"DROP TABLE {temp_name}")
            except KosDBError:
                # Original missing or temp missing; leave temp as recovery copy.
                pass

        return f"OK: Table '{table_name}' altered"

    def rename_column(self, table_name: str, old_name: str, new_name: str) -> str:
        """Rename a column while preserving its values."""
        schema = self._infer_schema(table_name)
        if not schema:
            raise KosDBError(f"Could not infer schema for table '{table_name}'")

        columns = list(schema.get("columns", []))
        if old_name not in columns:
            raise KosDBError(f"Column '{old_name}' does not exist")
        if new_name in columns:
            raise KosDBError(f"Column '{new_name}' already exists")
        columns[columns.index(old_name)] = new_name

        indexes = list(schema.get("indexes", []))
        if old_name in indexes:
            indexes[indexes.index(old_name)] = new_name

        primary_key = schema.get("primary_key")
        if primary_key == old_name:
            primary_key = new_name

        return self.alter_table(
            table_name, columns,
            primary_key=primary_key,
            indexes=indexes,
            next_id=schema.get("next_id", 1),
            column_renames={new_name: old_name}
        )

    @staticmethod
    def _sql_quote(value) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, (list, dict)):
            import json
            return "'" + json.dumps(value).replace(chr(39), chr(39)+chr(39)).replace("\\", "\\\\") + "'"
        return "'" + str(value).replace("\\", "\\\\").replace(chr(39), chr(39)+chr(39)).replace("\n", "\\n").replace("\r", "\\r") + "'"

    def table_data(self, db_name: str, table_name: str,
                   limit: Optional[int] = None,
                   offset: Optional[int] = None,
                   order_by: Optional[str] = None,
                   order_desc: bool = False) -> Dict[str, Any]:
        """Return rows for a table, optionally paginated and ordered."""
        self.use_database(db_name)
        clause = f"SELECT * FROM {table_name}"
        if order_by:
            clause += f" ORDER BY {order_by}"
            if order_desc:
                clause += " DESC"
        if limit is not None:
            clause += f" LIMIT {limit}"
        if offset is not None:
            clause += f" OFFSET {offset}"
        return self.execute_query(clause)

    def table_count(self, db_name: str, table_name: str) -> int:
        """Return the total number of rows in a table."""
        data = self.table_data(db_name, table_name, limit=0)
        return data.get("total", data.get("count", 0))

    def export_database(self, db_name: str, file_path: str) -> str:
        """Export a whole database to a SQL dump file via the server."""
        dbs = self.list_databases()
        if db_name not in dbs:
            raise KosDBError(f"ERROR: Database '{db_name}' does not exist")
        self.use_database(db_name)
        tables = self.list_tables()

        lines = [
            f"-- KosDB dump of database '{db_name}'",
            f"CREATE DATABASE {db_name};",
            f"USE {db_name};",
            "",
        ]

        for table_name in tables:
            lines.extend(self._dump_table_sql(db_name, table_name))
            lines.append("")

        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return f"Exported {len(tables)} table(s) to {file_path}"

    def export_table(self, db_name: str, table_name: str, file_path: str) -> str:
        """Export a single table to a SQL dump file via the server."""
        # Validate database exists before trying to describe the table.
        dbs = self.list_databases()
        if db_name not in dbs:
            raise KosDBError(f"ERROR: Database '{db_name}' does not exist")

        lines = [
            f"-- KosDB dump of {db_name}.{table_name}",
            f"CREATE DATABASE {db_name};",
            f"USE {db_name};",
            "",
        ]
        lines.extend(self._dump_table_sql(db_name, table_name))

        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return f"Exported table to {file_path}"

    def _dump_table_sql(self, db_name: str, table_name: str) -> List[str]:
        """Return SQL statements for a single table."""
        self.use_database(db_name)
        schema = self._infer_schema(table_name)
        if not schema:
            return [f"-- Table '{table_name}' schema not found"]

        columns = schema.get("columns", [])
        primary_key = schema.get("primary_key")
        indexes = schema.get("indexes", [])
        next_id = schema.get("next_id", 1)

        column_types = schema.get("column_types", {})
        col_specs = []
        for col in columns:
            col_type = column_types.get(col, "TEXT").upper()
            if col == primary_key:
                spec = f"{col} {col_type} PRIMARY KEY"
            else:
                spec = f"{col} {col_type}"
            if col in indexes:
                spec += " INDEX"
            col_specs.append(spec)

        lines = [f"DROP TABLE IF EXISTS {table_name};"]
        lines.append(f"CREATE TABLE {table_name} ({', '.join(col_specs)});")

        if primary_key and next_id > 1:
            lines.append(f"SET TABLE {table_name} next_id {next_id};")

        data = self.execute_query(f"SELECT * FROM {table_name}")
        rows = data.get("rows", [])
        for row in rows:
            row_columns = [col for col in columns if col in row]
            if not row_columns:
                continue
            values = [self._sql_quote(row[col]) for col in row_columns]
            col_list = ", ".join(row_columns)
            val_list = ", ".join(values)
            lines.append(f"INSERT INTO {table_name} ({col_list}) VALUES ({val_list});")

        return lines

    def import_sql(self, file_path: str) -> str:
        """Execute a SQL dump file through the connected server."""
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        statements = self._split_statements(content)
        executed = 0
        errors = []
        failed = False

        for stmt in statements:
            if failed:
                errors.append(f"Skipped after earlier error: {stmt[:60]}")
                continue
            try:
                self.execute_command(stmt)
                executed += 1
            except KosDBError as e:
                errors.append(f"{stmt[:60]}...: {e}")
                failed = True

        if errors:
            return f"Imported {executed} statement(s), {len(errors)} error(s):\n" + "\n".join(errors)
        return f"Imported {executed} statement(s) from {file_path}"

    @staticmethod
    def _split_statements(sql: str) -> List[str]:
        """Split SQL dump into executable statements, ignoring comments.

        Statement boundaries are only recognised at top-level semicolons so that
        semicolons inside quoted string literals are not treated as terminators.
        """
        import re
        # Strip block comments first.
        sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
        statements = []
        current = []
        quote_char = None
        escape = False
        for ch in sql:
            if escape:
                current.append(ch)
                escape = False
                continue
            if ch == "\\" and quote_char in ("'", '"'):
                current.append(ch)
                escape = True
                continue
            if quote_char is None:
                if ch in ("'", '"'):
                    quote_char = ch
                    current.append(ch)
                elif ch == ";":
                    stmt = "".join(current).strip()
                    stmt = KosDBClient._strip_line_comments(stmt)
                    if stmt:
                        statements.append(stmt)
                    current = []
                else:
                    current.append(ch)
            else:
                current.append(ch)
                if ch == quote_char:
                    quote_char = None
        stmt = "".join(current).strip()
        stmt = KosDBClient._strip_line_comments(stmt)
        if stmt:
            statements.append(stmt)
        return statements

    @staticmethod
    def _strip_line_comments(stmt: str) -> str:
        """Remove line-style comments from a statement without touching quoted strings."""
        result = []
        quote_char = None
        escape = False
        i = 0
        while i < len(stmt):
            ch = stmt[i]
            if escape:
                result.append(ch)
                escape = False
                i += 1
                continue
            if ch == "\\" and quote_char in ("'", '"'):
                result.append(ch)
                escape = True
                i += 1
                continue
            if quote_char is None:
                if ch in ("'", '"'):
                    quote_char = ch
                    result.append(ch)
                elif ch == "-" and i + 1 < len(stmt) and stmt[i + 1] == "-":
                    while i < len(stmt) and stmt[i] != "\n":
                        i += 1
                    continue
                elif ch == "#":
                    while i < len(stmt) and stmt[i] != "\n":
                        i += 1
                    continue
                else:
                    result.append(ch)
            else:
                result.append(ch)
                if ch == quote_char:
                    quote_char = None
            i += 1
        return "".join(result).strip()
