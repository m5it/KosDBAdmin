"""Database/table tree panel for KosDBAdmin."""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem,
    QMenu, QMessageBox, QInputDialog, QAbstractItemView
)

from kosdbadmin.client import KosDBClient, KosDBError


class TreePanel(QWidget):
    """Left-side tree showing databases and tables."""

    database_selected = pyqtSignal(str)
    table_selected = pyqtSignal(str, str)  # db_name, table_name
    refresh_requested = pyqtSignal()

    def __init__(self, client: KosDBClient, parent=None):
        super().__init__(parent)
        self.client = client

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("Databases")
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)
        self.tree.itemClicked.connect(self.on_item_clicked)
        self.tree.itemExpanded.connect(self.on_item_expanded)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        layout.addWidget(self.tree)

        self.root = QTreeWidgetItem(self.tree, [f"{client.host}:{client.port}"])
        self.root.setExpanded(True)

        self.refresh_button = None  # optional, can be added later

    def refresh(self):
        """Reload the entire tree."""
        self.tree.clear()
        self.root = QTreeWidgetItem(self.tree, [f"{self.client.host}:{self.client.port}"])
        self.root.setExpanded(True)

        try:
            databases = self.client.list_databases()
        except KosDBError as e:
            QMessageBox.critical(self, "Error", f"Failed to list databases: {e}")
            return

        for db_name in databases:
            if db_name.startswith("_"):
                continue
            db_item = QTreeWidgetItem(self.root, [db_name])
            db_item.setData(0, Qt.UserRole, "database")
            db_item.setExpanded(False)
            # placeholder child so the expand arrow appears
            placeholder = QTreeWidgetItem(db_item, ["Loading..."])
            placeholder.setData(0, Qt.UserRole, "placeholder")

    def on_item_expanded(self, item: QTreeWidgetItem):
        if item.data(0, Qt.UserRole) == "database" and item.childCount() == 1:
            first = item.child(0)
            if first.data(0, Qt.UserRole) == "placeholder":
                self.load_tables(item)

    def load_tables(self, db_item: QTreeWidgetItem):
        db_name = db_item.text(0)
        # remove placeholder
        for i in range(db_item.childCount() - 1, -1, -1):
            child = db_item.child(i)
            if child.data(0, Qt.UserRole) == "placeholder":
                db_item.removeChild(child)

        try:
            tables = self.client.list_tables(db_name)
        except KosDBError as e:
            QMessageBox.critical(self, "Error", f"Failed to list tables: {e}")
            return

        for table_name in tables:
            table_item = QTreeWidgetItem(db_item, [table_name])
            table_item.setData(0, Qt.UserRole, "table")

    def on_item_clicked(self, item: QTreeWidgetItem, column: int):
        kind = item.data(0, Qt.UserRole)
        if kind == "database":
            db_name = item.text(0)
            self.database_selected.emit(db_name)
            if item.childCount() == 1 and item.child(0).data(0, Qt.UserRole) == "placeholder":
                self.load_tables(item)
        elif kind == "table":
            db_item = item.parent()
            if db_item:
                self.table_selected.emit(db_item.text(0), item.text(0))

    def show_context_menu(self, position):
        item = self.tree.itemAt(position)
        if not item:
            return

        menu = QMenu()
        kind = item.data(0, Qt.UserRole)

        if kind == "database":
            refresh = menu.addAction("Refresh tables")
            refresh.triggered.connect(lambda: self.refresh_database(item))
            create_table = menu.addAction("Create table...")
            create_table.triggered.connect(lambda: self.create_table(item.text(0)))
            drop_db = menu.addAction("Drop database")
            drop_db.triggered.connect(lambda: self.drop_database(item.text(0)))
        elif kind == "table":
            db_name = item.parent().text(0)
            table_name = item.text(0)
            refresh = menu.addAction("Refresh")
            refresh.triggered.connect(lambda: self.refresh_table(db_name, table_name))
            drop_table = menu.addAction("Drop table")
            drop_table.triggered.connect(lambda: self.drop_table(db_name, table_name))
        else:
            create_db = menu.addAction("Create database...")
            create_db.triggered.connect(self.create_database)
            refresh_all = menu.addAction("Refresh all")
            refresh_all.triggered.connect(self.refresh)

        menu.exec_(self.tree.viewport().mapToGlobal(position))

    def refresh_database(self, item: QTreeWidgetItem):
        for i in range(item.childCount() - 1, -1, -1):
            item.removeChild(item.child(i))
        placeholder = QTreeWidgetItem(item, ["Loading..."])
        placeholder.setData(0, Qt.UserRole, "placeholder")
        self.load_tables(item)

    def refresh_table(self, db_name: str, table_name: str):
        self.table_selected.emit(db_name, table_name)

    def create_database(self):
        name, ok = QInputDialog.getText(self, "Create database", "Database name:")
        if ok and name.strip():
            try:
                self.client.create_database(name.strip())
                self.refresh()
            except KosDBError as e:
                QMessageBox.critical(self, "Error", str(e))

    def drop_database(self, db_name: str):
        reply = QMessageBox.question(
            self, "Confirm", f"Drop database '{db_name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                self.client.drop_database(db_name)
                self.refresh()
            except KosDBError as e:
                QMessageBox.critical(self, "Error", str(e))

    def create_table(self, db_name: str):
        name, ok = QInputDialog.getText(self, "Create table", "Table name:")
        if not ok or not name.strip():
            return
        cols, ok2 = QInputDialog.getText(
            self, "Create table",
            "Columns (e.g. id INTEGER PRIMARY KEY, name TEXT, INDEX name):",
            text="id INTEGER PRIMARY KEY"
        )
        if ok2:
            try:
                columns = [c.strip() for c in cols.split(",") if c.strip()]
                self.client.use_database(db_name)
                self.client.create_table(name.strip(), columns)
                self.refresh_database(self._db_item(db_name))
            except KosDBError as e:
                QMessageBox.critical(self, "Error", str(e))

    def drop_table(self, db_name: str, table_name: str):
        reply = QMessageBox.question(
            self, "Confirm", f"Drop table '{db_name}.{table_name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                self.client.use_database(db_name)
                self.client.drop_table(table_name)
                self.refresh_database(self._db_item(db_name))
            except KosDBError as e:
                QMessageBox.critical(self, "Error", str(e))

    def _db_item(self, db_name: str) -> QTreeWidgetItem:
        for i in range(self.root.childCount()):
            child = self.root.child(i)
            if child.text(0) == db_name:
                return child
        return None
