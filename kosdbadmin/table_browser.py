"""Table data and structure browser for KosDBAdmin."""

import json
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QLabel, QHBoxLayout, QPushButton,
    QMessageBox, QInputDialog, QMenu, QLineEdit
)

from kosdbadmin.client import KosDBClient, KosDBError
from kosdbadmin.utils import format_value



class TableBrowser(QWidget):
    """Tabbed view for a single table: data and structure."""

    def __init__(self, client: KosDBClient, local=None, parent=None):
        super().__init__(parent)
        self.client = client
        self.local = local
        self.db_name = ""
        self.table_name = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_label = QLabel("No table selected")
        layout.addWidget(self.title_label)

        self.tabs = QTabWidget()
        self.data_tab = DataTab(client)
        self.structure_tab = StructureTab(client, local=local)
        self.structure_tab.structure_changed.connect(self.refresh)

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
        self.structure_tab.local = self.local
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
    """Show schema/structure of a table with editing options."""

    structure_changed = pyqtSignal()

    def __init__(self, client: KosDBClient, local=None, parent=None):
        super().__init__(parent)
        self.client = client
        self.local = local
        self.db_name = ""
        self.table_name = ""
        self.columns = []
        self.indexes = []
        self.primary_key = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Column", "Type", "Attributes", "Default"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        layout.addWidget(self.table)

        # Toolbar
        toolbar = QHBoxLayout()
        self.add_btn = QPushButton("Add column")
        self.add_btn.clicked.connect(self.add_column)
        toolbar.addWidget(self.add_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.info_label = QLabel()
        layout.addWidget(self.info_label)

    def load(self, db_name: str, table_name: str):
        self.db_name = db_name
        self.table_name = table_name
        self.table.setRowCount(0)
        self.info_label.setText("Loading...")

        schema = None
        if self.local:
            try:
                schema = self.local.read_schema(db_name, table_name)
            except Exception:
                schema = None

        if not schema:
            # Infer from data
            try:
                self.client.use_database(db_name)
                result = self.client.execute_query(f"SELECT * FROM {table_name}")
                self.columns = result.get("columns", [])
                self.indexes = []
                self.primary_key = None
            except KosDBError as e:
                self.info_label.setText(f"Error: {e}")
                return
        else:
            self.columns = schema.get("columns", [])
            self.indexes = schema.get("indexes", [])
            self.primary_key = schema.get("primary_key")

        if not self.columns:
            self.info_label.setText("No structure information")
            return

        for cidx, col in enumerate(self.columns):
            self._add_row(cidx, col)

        self.table.resizeColumnsToContents()
        if not self.columns:
            self.info_label.setText("No structure information")
            return

        self.table.resizeColumnsToContents()
        self.info_label.setText(
            f"{len(self.columns)} column(s)"
            + (f", PK: {self.primary_key}" if self.primary_key else "")
            + (f", indexes: {', '.join(self.indexes)}" if self.indexes else "")
        )

    def _add_row(self, row: int, col: str, col_type: str = "text", default=""):
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(col))
        item = QTableWidgetItem(col_type)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, 1, item)
        attrs = []
        if self.primary_key and col == self.primary_key:
            attrs.append("PRIMARY KEY")
        if col in self.indexes:
            attrs.append("INDEX")
        if col.lower() == "id":
            attrs.append("auto id")
        self.table.setItem(row, 2, QTableWidgetItem(", ".join(attrs)))
        self.table.setItem(row, 3, QTableWidgetItem(str(default) if default is not None else ""))

    def show_context_menu(self, position):
        row = self.table.rowAt(position.y())
        menu = QMenu()
        if row >= 0:
            edit_action = menu.addAction("Edit column")
            edit_action.triggered.connect(lambda: self.edit_column(row))
            drop_action = menu.addAction("Drop column")
            drop_action.triggered.connect(lambda: self.drop_column(row))
            if self.table.item(row, 0).text() == self.primary_key:
                drop_action.setEnabled(False)
                drop_action.setToolTip("Cannot drop primary key column")
        add_action = menu.addAction("Add column")
        add_action.triggered.connect(self.add_column)
        menu.exec_(self.table.viewport().mapToGlobal(position))

    def add_column(self):
        name, ok = QInputDialog.getText(self, "Add column", "Column name:")
        if not ok or not name.strip():
            return
        col_name = name.strip()

        if col_name in self.columns:
            QMessageBox.warning(self, "Warning", f"Column '{col_name}' already exists")
            return

        type_name, ok2 = QInputDialog.getItem(
            self, "Add column", "Type:",
            ["TEXT", "INTEGER", "REAL", "BOOLEAN", "JSON"], 0, False
        )
        if not ok2:
            return

        indexed, _ = QMessageBox.question(
            self, "Index", f"Create index on '{col_name}'?",
            QMessageBox.Yes | QMessageBox.No
        )

        default, ok3 = QInputDialog.getText(
            self, "Add column", "Default value (optional):"
        )
        if not ok3:
            default = ""

        try:
            self.client.use_database(self.db_name)
            self.client.add_column(
                self.table_name, col_name, type_name,
                indexed=(indexed == QMessageBox.Yes), default=default
            )
            if indexed == QMessageBox.Yes and col_name not in self.indexes:
                self.indexes.append(col_name)
            self.columns.append(col_name)
            self._add_row(self.table.rowCount(), col_name, type_name.lower(), default)
            self.table.resizeColumnsToContents()
            self.info_label.setText(f"{len(self.columns)} column(s)")
            self.structure_changed.emit()
            QMessageBox.information(self, "Success", f"Column '{col_name}' added")
        except KosDBError as e:
            QMessageBox.critical(self, "Error", str(e))

    def edit_column(self, row: int):
        old_name = self.table.item(row, 0).text()
        new_name, ok = QInputDialog.getText(
            self, "Edit column", "New column name:", text=old_name
        )
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return

        new_name = new_name.strip()
        if new_name in self.columns:
            QMessageBox.warning(self, "Warning", f"Column '{new_name}' already exists")
            return

        type_name, ok2 = QInputDialog.getItem(
            self, "Edit column", "Type:",
            ["TEXT", "INTEGER", "REAL", "BOOLEAN", "JSON"], 0, False
        )
        if not ok2:
            return

        default, ok3 = QInputDialog.getText(
            self, "Edit column", "Default value (optional):",
            text=self.table.item(row, 3).text()
        )
        if not ok3:
            return

        reply = QMessageBox.question(
            self, "Confirm",
            f"Apply changes to column '{old_name}'?\n\n"
            "Renaming will update existing rows automatically.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        try:
            self.client.use_database(self.db_name)
            if old_name != new_name:
                self.client.rename_column(self.table_name, old_name, new_name)
                self.columns[row] = new_name
                self.table.item(row, 0).setText(new_name)
                if old_name in self.indexes:
                    self.indexes[self.indexes.index(old_name)] = new_name
                if self.primary_key == old_name:
                    self.primary_key = new_name
            # Type/default change is applied by recreating the table;
            # we pass a dummy rename-to-self to rebuild with defaults if needed.
            if old_name == new_name:
                self.client.rename_column(self.table_name, old_name, old_name)
            self.table.item(row, 1).setText(type_name.lower())
            self.table.item(row, 3).setText(default)
            self.structure_changed.emit()
            QMessageBox.information(self, "Success", "Column updated")
        except KosDBError as e:
            QMessageBox.critical(self, "Error", str(e))

    def drop_column(self, row: int):
        col_name = self.table.item(row, 0).text()
        reply = QMessageBox.question(
            self, "Confirm",
            f"Drop column '{col_name}'?\n\n"
            "This removes the column from all rows.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        try:
            self.client.use_database(self.db_name)
            self.client.drop_column(self.table_name, col_name)
            self.columns.pop(row)
            self.table.removeRow(row)
            self.info_label.setText(f"{len(self.columns)} column(s)")
            self.structure_changed.emit()
            QMessageBox.information(self, "Success", "Column dropped")
        except KosDBError as e:
            QMessageBox.critical(self, "Error", str(e))
