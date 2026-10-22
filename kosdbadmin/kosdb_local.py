"""Direct LevelDB access for reading KosDB schema locally."""

import json
import os
import sys
from typing import Any, Dict, List, Optional

# Allow using the system python3-plyvel package from a virtual environment.
if "/usr/lib/python3/dist-packages" not in sys.path:
    sys.path.append("/usr/lib/python3/dist-packages")


class KosDBLocal:
    """Read-only helper that opens the same LevelDB used by the KosDB server.

    This avoids needing special wire-protocol commands for reading metadata.
    """

    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self._db = None

    def _open_db(self, db_name: str):
        import plyvel
        path = os.path.join(self.data_dir, db_name)
        return plyvel.DB(path, create_if_missing=False)

    def read_schema(self, db_name: str, table_name: str) -> Optional[Dict[str, Any]]:
        db = self._open_db(db_name)
        try:
            raw = db.get(f"_schema:{table_name}".encode())
            if raw:
                return json.loads(raw.decode())
            return None
        finally:
            db.close()

    def list_tables(self, db_name: str) -> List[str]:
        db = self._open_db(db_name)
        try:
            tables = set()
            for key, _ in db.iterator():
                k = key.decode()
                if k.startswith("_schema:"):
                    tables.add(k.split(":", 1)[1])
                elif ":" in k and not k.startswith("_"):
                    tables.add(k.split(":", 1)[0])
            return sorted(tables)
        finally:
            db.close()
