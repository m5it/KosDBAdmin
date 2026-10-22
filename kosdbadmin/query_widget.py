"""SQL query editor + results table."""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QTextCursor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QSplitter, QMessageBox,
    QLabel, QHeaderView, QAbstractItemView
)

from kosdbadmin.client import KosDBClient, KosDBError
from kosdbadmin.utils import format_value, parse_simple_result


class QueryWidget(QWidget):
    """A query editor with a results table."""

    def __init__(self, client: KosDBClient, parent=None):
        super().__init__(parent)
        self.client = client

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Vertical)

        # Editor
        self.editor = QTextEdit()
        self.editor.setFont(QFont("Consolas", 10))
        self.editor.setPlaceholderText("Enter SQL command here...")
        self.editor.setAcceptRichText(False)
        splitter.addWidget(self.editor)

        # Results
        self.result_table = QTableWidget()
        self.result_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.result_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.result_table.horizontalHeader().setStretchLastSection(True)
        self.result_table.setAlternatingRowColors(True)
        splitter.addWidget(self.result_table)

        splitter.setSizes([120, 280])
        layout.addWidget(splitter)

        # Toolbar
        toolbar = QHBoxLayout()
        self.run_btn = QPushButton("Run")
        self.run_btn.setShortcut("Ctrl+Return")
        self.run_btn.clicked.connect(self.run_query)
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self.clear_editor)
        self.status_label = QLabel("Ready")
        toolbar.addWidget(self.run_btn)
        toolbar.addWidget(self.clear_btn)
        toolbar.addStretch()
        toolbar.addWidget(self.status_label)
        layout.addLayout(toolbar)

    def set_default_query(self, query: str):
        self.editor.setPlainText(query)
        self.editor.moveCursor(QTextCursor.End)

    def clear_editor(self):
        self.editor.clear()
        self.result_table.clear()
        self.result_table.setRowCount(0)
        self.result_table.setColumnCount(0)
        self.status_label.setText("Ready")

    def run_query(self):
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            query = cursor.selectedText().strip()
        else:
            query = self.editor.toPlainText().strip()
        if not query:
            return

        self.status_label.setText("Running...")
        self.setEnabled(False)

        try:
            upper = query.upper()
            is_select = upper.startswith("SELECT") or upper.startswith("SHOW") or upper.startswith("DESCRIBE")
            if is_select:
                result = self.client.execute_query(query)
                self.show_results(result)
                count = result.get("count", len(result.get("rows", [])))
                self.status_label.setText(f"{count} row(s)")
            else:
                response = self.client.execute_command(query)
                self.show_plain_result(response)
                self.status_label.setText(parse_simple_result(response))
        except KosDBError as e:
            QMessageBox.critical(self, "Query error", str(e))
            self.status_label.setText("Error")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            self.status_label.setText("Error")
        finally:
            self.setEnabled(True)

    def show_results(self, result: dict):
        columns = result.get("columns", [])
        rows = result.get("rows", [])

        self.result_table.clear()
        self.result_table.setColumnCount(len(columns))
        self.result_table.setHorizontalHeaderLabels(columns)
        self.result_table.setRowCount(len(rows))

        for ridx, row in enumerate(rows):
            for cidx, col in enumerate(columns):
                value = row.get(col)
                item = QTableWidgetItem(format_value(value))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.result_table.setItem(ridx, cidx, item)

        self.result_table.resizeColumnsToContents()

    def show_plain_result(self, text: str):
        self.result_table.clear()
        self.result_table.setColumnCount(1)
        self.result_table.setHorizontalHeaderLabels(["Result"])
        self.result_table.setRowCount(1)
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        self.result_table.setItem(0, 0, item)
        self.result_table.resizeColumnsToContents()
