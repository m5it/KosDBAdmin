"""Async query worker for KosDBAdmin."""

from typing import Optional

from PyQt5.QtCore import QThread, pyqtSignal

from kosdbadmin.client import KosDBClient, KosDBError


class TableQueryWorker(QThread):
    """Run a paginated table query in a background thread."""

    results_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, client: KosDBClient, db_name: str, table_name: str,
                 limit: Optional[int] = None, offset: int = 0,
                 order_by: Optional[str] = None, order_desc: bool = False,
                 parent=None):
        super().__init__(parent)
        self.client = client
        self.db_name = db_name
        self.table_name = table_name
        self.limit = limit
        self.offset = offset
        self.order_by = order_by
        self.order_desc = order_desc

    def run(self):
        try:
            result = self.client.table_data(
                self.db_name, self.table_name,
                limit=self.limit, offset=self.offset,
                order_by=self.order_by, order_desc=self.order_desc
            )
            self.results_ready.emit(result)
        except KosDBError as e:
            self.error_occurred.emit(str(e))
        except Exception as e:
            self.error_occurred.emit(f"Unexpected error: {e}")
