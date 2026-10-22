"""Search widget for KosDBAdmin."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QComboBox, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QLabel, QMessageBox
)

from kosdbadmin.client import KosDBClient, KosDBError
from kosdbadmin.utils import format_value


class SearchWidget(QWidget):
    """Search panel for finding rows across tables and databases."""

    def __init__(self, client: KosDBClient, parent=None):
        super().__init__(parent)
        self.client = client

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        form = QFormLayout()

        self.db_combo = QComboBox()
        self.db_combo.setMinimumWidth(150)
        self.db_combo.currentIndexChanged.connect(self.on_database_changed)

        self.table_combo = QComboBox()
        self.table_combo.setMinimumWidth(150)

        self.column_combo = QComboBox()
        self.column_combo.addItem("* (all columns)")
        self.column_combo.setMinimumWidth(150)

        self.operator_combo = QComboBox()
        self.operator_combo.addItems(["=", "LIKE", "!=", "<", ">", "<=", ">="])
        self.operator_combo.setMinimumWidth(80)

        self.value_edit = QLineEdit()
        self.value_edit.setPlaceholderText("Search value")
        self.value_edit.returnPressed.connect(self.run_search)

        form.addRow("Database:", self.db_combo)
        form.addRow("Table:", self.table_combo)
        form.addRow("Column:", self.column_combo)
        form.addRow("Operator:", self.operator_combo)
        form.addRow("Value:", self.value_edit)
        layout.addLayout(form)

        # Toolbar
        toolbar = QHBoxLayout()
        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self.run_search)
        self.search_btn.setShortcut("Ctrl+Return")
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self.clear_results)
        toolbar.addWidget(self.search_btn)
        toolbar.addWidget(self.clear_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)

        # Results
        self.result_table = QTableWidget()
        self.result_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.result_table.horizontalHeader().setStretchLastSection(True)
        self.result_table.setAlternatingRowColors(True)
        layout.addWidget(self.result_table)

        self.refresh_databases()

    def refresh_databases(self):
        self.db_combo.clear()
        try:
            databases = self.client.list_databases()
        except KosDBError as e:
            QMessageBox.critical(self, "Error", f"Failed to list databases: {e}")
            return

        for db in databases:
            if not db.startswith("_"):
                self.db_combo.addItem(db)

    def on_database_changed(self, index: int):
        self.table_combo.clear()
        self.column_combo.clear()
        self.column_combo.addItem("* (all columns)")
        db_name = self.db_combo.currentText()
        if not db_name:
            return

        try:
            tables = self.client.list_tables(db_name)
        except KosDBError as e:
            QMessageBox.critical(self, "Error", f"Failed to list tables: {e}")
            return

        for table in tables:
            self.table_combo.addItem(table)
        self.table_combo.currentIndexChanged.connect(self.on_table_changed)
        if self.table_combo.count() > 0:
            self.on_table_changed(0)

    def on_table_changed(self, index: int):
        self.column_combo.clear()
        self.column_combo.addItem("* (all columns)")
        table_name = self.table_combo.currentText()
        db_name = self.db_combo.currentText()
        if not table_name or not db_name:
            return

        try:
            result = self.client.table_data(db_name, table_name)
        except KosDBError as e:
            QMessageBox.critical(self, "Error", f"Failed to read table: {e}")
            return

        columns = result.get("columns", [])
        for col in columns:
            self.column_combo.addItem(col)

    def clear_results(self):
        self.result_table.clear()
        self.result_table.setRowCount(0)
        self.result_table.setColumnCount(0)
        self.status_label.setText("Ready")

    def run_search(self):
        db_name = self.db_combo.currentText()
        table_name = self.table_combo.currentText()
        column = self.column_combo.currentText()
        operator = self.operator_combo.currentText()
        value = self.value_edit.text().strip()

        if not db_name or not table_name:
            QMessageBox.warning(self, "Warning", "Select a database and table first")
            return

        self.status_label.setText("Searching...")

        try:
            result = self.client.table_data(db_name, table_name)
        except KosDBError as e:
            QMessageBox.critical(self, "Error", str(e))
            self.status_label.setText("Error")
            return

        columns = result.get("columns", [])
        rows = result.get("rows", [])

        if not columns:
            self.status_label.setText("No columns to search")
            return

        search_col = None if column == "* (all columns)" else column
        matches = self._filter_rows(rows, columns, search_col, operator, value)

        self._show_results(columns, matches)
        self.status_label.setText(f"{len(matches)} row(s) matched")

    def _filter_rows(self, rows, columns, search_col, operator, value):
        matches = []
        for row in rows:
            if search_col:
                if self._match(str(row.get(search_col, "")), operator, value):
                    matches.append(row)
            else:
                if any(self._match(str(row.get(col, "")), operator, value) for col in columns):
                    matches.append(row)
        return matches

    @staticmethod
    def _match(cell_value: str, operator: str, search_value: str) -> bool:
        if operator == "LIKE":
            pattern = search_value.strip("'\"")
            return pattern.lower() in cell_value.lower()
        if operator == "=":
            return cell_value == search_value
        if operator == "!=":
            return cell_value != search_value

        # Numeric comparisons
        try:
            cell_num = float(cell_value)
            search_num = float(search_value)
        except ValueError:
            return False

        if operator == "<":
            return cell_num < search_num
        if operator == ">":
            return cell_num > search_num
        if operator == "<=":
            return cell_num <= search_num
        if operator == ">=":
            return cell_num >= search_num
        return False

    def _show_results(self, columns, rows):
        self.result_table.clear()
        self.result_table.setColumnCount(len(columns))
        self.result_table.setHorizontalHeaderLabels(columns)
        self.result_table.setRowCount(len(rows))

        for ridx, row in enumerate(rows):
            for cidx, col in enumerate(columns):
                item = QTableWidgetItem(format_value(row.get(col)))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.result_table.setItem(ridx, cidx, item)

        self.result_table.resizeColumnsToContents()
