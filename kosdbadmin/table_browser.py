"""Table data and structure browser for KosDBAdmin."""

import json
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QLabel, QHBoxLayout, QPushButton,
    QMessageBox
)

from kosdbadmin.client import KosDBClient, KosDBError
from kosdbadmin.utils import format_value


class TableBrowser(QWidget):
    """Tabbed view for a single table: data and structure."""

    def __init__(self, client: KosDBClient, parent=None):
        super().__init__(parent)
        self.client = client
        self.db_name = ""
        self.table_name = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_label = QLabel("No table selected")
        layout.addWidget(self.title_label)

        self.tabs = QTabWidget()
        self.data_tab = DataTab(client)
        self.structure_tab = StructureTab(client)
        self.tabs.addTab(self.data_tab, "Browse")
        self.tabs.addTab(self.structure_tab, "Structure")
        layout.addWidget(self.tabs)

        # Toolbar
        toolbar = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh)
        self.insert_btn = QPushButton("Insert row...")
        self.insert_btn.clicked.connect(self.insert_row)
        toolbar.addWidget(self.refresh_btn)
        toolbar.addWidget(self.insert_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

    def load(self, db_name: str, table_name: str):
        self.db_name = db_name
        self.table_name = table_name
        self.title_label.setText(f"<b>{db_name}.{table_name}</b>")
        self.data_tab.load(db_name, table_name)
        self.structure_tab.load(db_name, table_name)

    def refresh(self):
        if self.db_name and self.table_name:
            self.load(self.db_name, self.table_name)

    def insert_row(self):
        if not self.db_name or not self.table_name:
            return
        try:
            self.client.use_database(self.db_name)
            schema = self.client.execute_query(
                f"SELECT * FROM {self.table_name}"
            )
            columns = schema.get("columns", [])
            if not columns:
                QMessageBox.information(self, "Insert", "No columns available")
                return
            from PyQt5.QtWidgets import QInputDialog
            values_text, ok = QInputDialog.getText(
                self, "Insert row",
                f"Values for ({', '.join(columns)}):\n(comma-separated)",
            )
            if not ok:
                return
            values = [v.strip() for v in values_text.split(",")]
            col_list = ", ".join(columns)
            val_list = ", ".join(self._quote(v) for v in values)
            self.client.execute_command(
                f"INSERT INTO {self.table_name} ({col_list}) VALUES ({val_list})"
            )
            self.refresh()
        except KosDBError as e:
            QMessageBox.critical(self, "Insert error", str(e))

    @staticmethod
    def _quote(value: str) -> str:
        try:
            float(value)
            return value
        except ValueError:
            escaped = value.replace("'", "''")
            return f"'{escaped}'"


class DataTab(QWidget):
    """Browse all rows of a table."""

    def __init__(self, client: KosDBClient, parent=None):
        super().__init__(parent)
        self.client = client

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        self.status = QLabel("No data")
        layout.addWidget(self.status)

    def load(self, db_name: str, table_name: str):
        self.table.clear()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self.status.setText("Loading...")

        try:
            result = self.client.table_data(db_name, table_name)
        except KosDBError as e:
            self.status.setText(f"Error: {e}")
            return

        columns = result.get("columns", [])
        rows = result.get("rows", [])

        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        self.table.setRowCount(len(rows))

        for ridx, row in enumerate(rows):
            for cidx, col in enumerate(columns):
                item = QTableWidgetItem(format_value(row.get(col)))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(ridx, cidx, item)

        self.table.resizeColumnsToContents()
        self.status.setText(f"{len(rows)} row(s)")


class StructureTab(QWidget):
    """Show schema/structure of a table."""

    def __init__(self, client: KosDBClient, parent=None):
        super().__init__(parent)
        self.client = client

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Column", "Type", "Attributes"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        self.info_label = QLabel()
        layout.addWidget(self.info_label)

    def load(self, db_name: str, table_name: str):
        self.table.setRowCount(0)
        self.info_label.setText("Loading...")

        try:
            self.client.use_database(db_name)
            # KosDB stores schema in _schema:table key; we can get it via a query trick
            # SELECT * FROM table returns all columns which gives us the schema
            result = self.client.execute_query(f"SELECT * FROM {table_name}")
            columns = result.get("columns", [])
            if not columns:
                self.info_label.setText("No structure information")
                return

            # Try to infer attributes from the first row
            sample = result.get("rows", [{}])[0] if result.get("rows") else {}
            for cidx, col in enumerate(columns):
                self.table.insertRow(cidx)
                self.table.setItem(cidx, 0, QTableWidgetItem(col))
                value = sample.get(col)
                type_name = type(value).__name__ if value is not None else "text"
                self.table.setItem(cidx, 1, QTableWidgetItem(type_name))
                attrs = []
                if col.lower() == "id":
                    attrs.append("auto id")
                self.table.setItem(cidx, 2, QTableWidgetItem(", ".join(attrs)))

            self.table.resizeColumnsToContents()
            self.info_label.setText(f"{len(columns)} column(s)")
        except KosDBError as e:
            self.info_label.setText(f"Error: {e}")
