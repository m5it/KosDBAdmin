"""Table data and structure browser for KosDBAdmin."""

import json
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QLabel, QHBoxLayout, QPushButton,
    QMessageBox, QInputDialog, QMenu, QDialog, QComboBox
)

from kosdbadmin.async_worker import TableQueryWorker
from kosdbadmin.client import KosDBClient, KosDBError
from kosdbadmin.column_dialog import ColumnDialog
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
    """Browse rows of a table with pagination."""

    PAGE_SIZES = [100, 250, 500, 1000]
    DEFAULT_PAGE_SIZE = 500

    def __init__(self, client: KosDBClient, parent=None):
        super().__init__(parent)
        self.client = client
        self.db_name = ""
        self.table_name = ""
        self.page = 0
        self.page_size = self.DEFAULT_PAGE_SIZE
        self.total = 0
        self.order_by = None
        self._worker = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Pagination toolbar
        pagination = QHBoxLayout()
        self.page_size_combo = QComboBox()
        for size in self.PAGE_SIZES:
            self.page_size_combo.addItem(str(size), size)
        self.page_size_combo.setCurrentIndex(self.PAGE_SIZES.index(self.DEFAULT_PAGE_SIZE))
        self.page_size_combo.currentIndexChanged.connect(self._page_size_changed)

        self.prev_btn = QPushButton("< Previous")
        self.prev_btn.clicked.connect(self._prev_page)
        self.next_btn = QPushButton("Next >")
        self.next_btn.clicked.connect(self._next_page)
        self.page_label = QLabel("Page 1 of 1")

        pagination.addWidget(QLabel("Page size:"))
        pagination.addWidget(self.page_size_combo)
        pagination.addStretch()
        pagination.addWidget(self.prev_btn)
        pagination.addWidget(self.page_label)
        pagination.addWidget(self.next_btn)
        layout.addLayout(pagination)

        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        self.status = QLabel("No data")
        layout.addWidget(self.status)

    def load(self, db_name: str, table_name: str):
        self.db_name = db_name
        self.table_name = table_name
        self.page = 0
        self.order_by = None
        try:
            self.client.use_database(db_name)
            schema = json.loads(self.client.execute(f"DESCRIBE {table_name}"))
            if "id" in schema.get("columns", []):
                self.order_by = "id"
        except Exception:
            pass
        self._load_page()

    def refresh(self):
        if self.db_name and self.table_name:
            self._load_page()

    def _page_size_changed(self):
        self.page_size = int(self.page_size_combo.currentData())
        self.page = 0
        self._load_page()

    def _prev_page(self):
        if self.page > 0:
            self.page -= 1
            self._load_page()

    def _next_page(self):
        if (self.page + 1) * self.page_size < self.total:
            self.page += 1
            self._load_page()

    def _load_page(self):
        self.table.clear()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self.status.setText("Loading...")
        self._set_pagination_enabled(False)

        if self._worker is not None and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(1000)

        offset = self.page * self.page_size
        self._worker = TableQueryWorker(
            self.client, self.db_name, self.table_name,
            limit=self.page_size, offset=offset,
            order_by=self.order_by
        )
        self._worker.results_ready.connect(self._on_results)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _on_results(self, result: dict):
        columns = result.get("columns", [])
        rows = result.get("rows", [])
        self.total = result.get("total", len(rows))

        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        self.table.setRowCount(len(rows))

        for ridx, row in enumerate(rows):
            for cidx, col in enumerate(columns):
                item = QTableWidgetItem(format_value(row.get(col)))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(ridx, cidx, item)

        self.table.resizeColumnsToContents()
        self._update_pagination()
        self.status.setText(f"{self.total} total row(s) | showing {len(rows)} row(s)")

    def _on_error(self, message: str):
        self.status.setText(f"Error: {message}")
        self._set_pagination_enabled(False)

    def _update_pagination(self):
        total_pages = max(1, (self.total + self.page_size - 1) // self.page_size)
        self.page_label.setText(f"Page {self.page + 1} of {total_pages}")
        self.prev_btn.setEnabled(self.page > 0)
        self.next_btn.setEnabled((self.page + 1) * self.page_size < self.total)
        self.page_size_combo.setEnabled(True)

    def _set_pagination_enabled(self, enabled: bool):
        self.prev_btn.setEnabled(enabled and self.page > 0)
        self.next_btn.setEnabled(enabled and (self.page + 1) * self.page_size < self.total)
        self.page_size_combo.setEnabled(enabled)


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
            try:
                self.client.use_database(db_name)
                schema = self.client._infer_schema(table_name)
            except KosDBError as e:
                self.info_label.setText(f"Error: {e}")
                return

        if not schema:
            self.info_label.setText("No structure information")
            return

        self.columns = schema.get("columns", [])
        self.indexes = schema.get("indexes", [])
        self.primary_key = schema.get("primary_key")

        for cidx, col in enumerate(self.columns):
            self._add_row(cidx, col)

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
            # Only show auto id when id is the actual primary key
            if col.lower() == "id":
                attrs.append("auto id")
        if col in self.indexes:
            attrs.append("INDEX")
        self.table.setItem(row, 2, QTableWidgetItem(", ".join(attrs)))
        self.table.setItem(row, 3, QTableWidgetItem(str(default) if default is not None else ""))

    def show_context_menu(self, position):
        row = self.table.rowAt(position.y())
        menu = QMenu()
        if row >= 0:
            col_name = self.table.item(row, 0).text()
            is_pk = col_name == self.primary_key
            edit_action = menu.addAction("Edit column")
            edit_action.triggered.connect(lambda: self.edit_column(row))
            drop_action = menu.addAction("Drop column")
            drop_action.triggered.connect(lambda: self.drop_column(row))
            if is_pk and col_name.lower() != "id":
                # Non-id primary keys cannot be edited because we can't safely
                # reassign PK values.
                edit_action.setEnabled(False)
                edit_action.setToolTip("Cannot edit primary key column")
                drop_action.setEnabled(False)
                drop_action.setToolTip("Cannot drop primary key column")
        add_action = menu.addAction("Add column")
        add_action.triggered.connect(self.add_column)
        menu.exec_(self.table.viewport().mapToGlobal(position))

    def add_column(self):
        has_pk = bool(self.primary_key)
        dlg = ColumnDialog(self, allow_pk=not has_pk, allow_autoincrement=True)
        if dlg.exec_() != QDialog.Accepted:
            return

        col_name = dlg.name_edit.text().strip()
        if not col_name:
            return
        if col_name in self.columns:
            QMessageBox.warning(self, "Warning", f"Column '{col_name}' already exists")
            return

        type_name = dlg.type_combo.currentText()
        default = dlg.default_edit.text()
        attr = dlg.attribute()

        try:
            self.client.use_database(self.db_name)
            new_columns = list(self.columns)
            new_columns.append(col_name)
            new_indexes = list(self.indexes)
            new_pk = self.primary_key

            if attr == "INDEX" and col_name not in new_indexes:
                new_indexes.append(col_name)
            if attr in ("PRIMARY KEY", "AUTO INCREMENT"):
                new_pk = col_name
                # Reordering: put PK column first for clarity.
                if col_name in new_columns:
                    new_columns.remove(col_name)
                new_columns.insert(0, col_name)

            self.client.alter_table(
                self.table_name, new_columns,
                primary_key=new_pk,
                indexes=new_indexes
            )

            if default:
                self.client.execute_command(
                    f"UPDATE {self.table_name} SET {col_name}="
                    f"'{default.replace(chr(39), chr(39)+chr(39))}'"
                )

            self.columns = new_columns
            self.indexes = new_indexes
            self.primary_key = new_pk
            self._add_row(self.table.rowCount(), col_name, type_name.lower(), default)
            self.table.resizeColumnsToContents()
            self.info_label.setText(f"{len(self.columns)} column(s)")
            self.structure_changed.emit()
        except KosDBError as e:
            QMessageBox.critical(self, "Error", str(e))

    def edit_column(self, row: int):
        old_name = self.table.item(row, 0).text()
        old_type = self.table.item(row, 1).text()
        old_default = self.table.item(row, 3).text()
        is_pk = old_name == self.primary_key
        was_indexed = old_name in self.indexes
        current_attr = "PRIMARY KEY" if is_pk else ("INDEX" if was_indexed else "(none)")

        has_pk = bool(self.primary_key)
        is_autoincrement = is_pk and old_name.lower() == "id"
        current_attr = "PRIMARY KEY" if is_pk else ("INDEX" if was_indexed else "(none)")
        if is_autoincrement:
            current_attr = "AUTO INCREMENT"

        dlg = ColumnDialog(self, name=old_name, col_type=old_type,
                           default=old_default, attribute=current_attr,
                           edit_mode=True, is_pk=is_pk,
                           allow_pk=not has_pk,
                           allow_autoincrement=(old_type.upper() == "INTEGER"))
        if dlg.exec_() != QDialog.Accepted:
            return

        new_name = dlg.name_edit.text().strip()
        if not new_name:
            return
        if new_name != old_name and new_name in self.columns:
            QMessageBox.warning(self, "Warning", f"Column '{new_name}' already exists")
            return

        type_name = dlg.type_combo.currentText()
        default = dlg.default_edit.text()
        new_attr = dlg.attribute()

        try:
            self.client.use_database(self.db_name)
            if old_name != new_name:
                self.columns[row] = new_name
                self.table.item(row, 0).setText(new_name)
                if old_name in self.indexes:
                    self.indexes[self.indexes.index(old_name)] = new_name
                if self.primary_key == old_name:
                    self.primary_key = new_name

            # Apply attribute change for non-PK columns.
            if not is_pk:
                if new_attr == "INDEX" and new_name not in self.indexes:
                    self.indexes.append(new_name)
                elif new_attr == "" and new_name in self.indexes:
                    self.indexes.remove(new_name)
                elif new_attr in ("PRIMARY KEY", "AUTO INCREMENT"):
                    self.primary_key = new_name
                    # Move PK column first.
                    if new_name in self.columns:
                        self.columns.remove(new_name)
                    self.columns.insert(0, new_name)
                    if new_name in self.indexes:
                        self.indexes.remove(new_name)

            # Apply attribute change via server-side ALTER TABLE when possible.
            if old_name == new_name and type_name.upper() == old_type.upper():
                # Only metadata changed; use lightweight server command.
                if self.primary_key == new_name:
                    attr_cmd = "AUTO_INCREMENT" if new_name.lower() == "id" else "PRIMARY KEY"
                elif new_name in self.indexes:
                    attr_cmd = "INDEX"
                else:
                    attr_cmd = "NONE"
                self.client.execute_command(
                    f"ALTER TABLE {self.table_name} MODIFY COLUMN {new_name} {type_name} {attr_cmd}"
                )
            else:
                # Rebuild table with updated metadata.
                self.client.alter_table(
                    self.table_name, self.columns,
                    primary_key=self.primary_key,
                    indexes=self.indexes
                )
            if default:
                self.client.execute_command(
                    f"UPDATE {self.table_name} SET {new_name}="
                    f"'{default.replace(chr(39), chr(39)+chr(39))}'"
                )
            self.table.item(row, 1).setText(type_name.lower())
            self.table.item(row, 3).setText(default)
            self.structure_changed.emit()
        except KosDBError as e:
            QMessageBox.critical(self, "Error", str(e))

    def drop_column(self, row: int):
        col_name = self.table.item(row, 0).text()
        if col_name == self.primary_key:
            QMessageBox.warning(
                self, "Warning",
                "Cannot drop the primary key column."
            )
            return

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
            new_columns = list(self.columns)
            new_columns.pop(row)
            new_indexes = list(self.indexes)
            if col_name in new_indexes:
                new_indexes.remove(col_name)
            self.client.alter_table(
                self.table_name, new_columns,
                primary_key=self.primary_key,
                indexes=new_indexes
            )
            self.columns = new_columns
            self.indexes = new_indexes
            self.table.removeRow(row)
            self.info_label.setText(f"{len(self.columns)} column(s)")
            self.structure_changed.emit()
        except KosDBError as e:
            QMessageBox.critical(self, "Error", str(e))
