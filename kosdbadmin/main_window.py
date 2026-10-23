"""Main window for KosDBAdmin."""

import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTabWidget, QAction, QMessageBox,
    QLabel, QStatusBar, QToolBar, QFileDialog, QInputDialog
)

from kosdbadmin.client import KosDBClient, KosDBError
from kosdbadmin.connection_dialog import ConnectionDialog
from kosdbadmin.kosdb_local import KosDBLocal
from kosdbadmin.tree_panel import TreePanel
from kosdbadmin.query_widget import QueryWidget
from kosdbadmin.search_widget import SearchWidget
from kosdbadmin.table_browser import TableBrowser


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("KosDBAdmin")
        self.setMinimumSize(1000, 700)

        self.client: KosDBClient = None
        self.local: KosDBLocal = None

        self._build_menu()
        self._build_toolbar()
        self._build_central()
        self._build_status()

        self.show_connection_dialog()

    def _build_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("File")
        connect_action = QAction("Connect...", self)
        connect_action.setShortcut("Ctrl+N")
        connect_action.triggered.connect(self.show_connection_dialog)
        file_menu.addAction(connect_action)

        disconnect_action = QAction("Disconnect", self)
        disconnect_action.triggered.connect(self.disconnect)
        file_menu.addAction(disconnect_action)

        file_menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        tools_menu = menubar.addMenu("Tools")
        query_action = QAction("New query tab", self)
        query_action.setShortcut("Ctrl+T")
        query_action.triggered.connect(self.add_query_tab)
        tools_menu.addAction(query_action)

        search_action = QAction("Search", self)
        search_action.setShortcut("Ctrl+F")
        search_action.triggered.connect(self.add_search_tab)
        tools_menu.addAction(search_action)

        refresh_action = QAction("Refresh tree", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self.refresh_tree)
        tools_menu.addAction(refresh_action)

        tools_menu.addSeparator()

        export_action = QAction("Export database...", self)
        export_action.triggered.connect(self.export_database)
        tools_menu.addAction(export_action)

        import_action = QAction("Import SQL...", self)
        import_action.triggered.connect(self.import_sql)
        tools_menu.addAction(import_action)

        help_menu = menubar.addMenu("Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def _build_toolbar(self):
        toolbar = QToolBar()
        self.addToolBar(toolbar)

        connect_btn = QAction("Connect", self)
        connect_btn.triggered.connect(self.show_connection_dialog)
        toolbar.addAction(connect_btn)

        query_btn = QAction("New query", self)
        query_btn.triggered.connect(self.add_query_tab)
        toolbar.addAction(query_btn)

        search_btn = QAction("Search", self)
        search_btn.triggered.connect(self.add_search_tab)
        toolbar.addAction(search_btn)

        refresh_btn = QAction("Refresh", self)
        refresh_btn.triggered.connect(self.refresh_tree)
        toolbar.addAction(refresh_btn)

    def _build_central(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(4, 4, 4, 4)

        self.splitter = QSplitter(Qt.Horizontal)

        self.tree_panel = None
        self.tree_container = QWidget()
        self.tree_layout = QVBoxLayout(self.tree_container)
        self.tree_layout.setContentsMargins(0, 0, 0, 0)
        self.tree_label = QLabel("Not connected")
        self.tree_layout.addWidget(self.tree_label)
        self.splitter.addWidget(self.tree_container)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.splitter.addWidget(self.tabs)

        self.splitter.setSizes([250, 750])
        layout.addWidget(self.splitter)

    def _build_status(self):
        self.status = QStatusBar()
        self.status_label = QLabel("Disconnected")
        self.status.addWidget(self.status_label)
        self.setStatusBar(self.status)

    def show_connection_dialog(self):
        if self.client:
            self.client.disconnect()

        dlg = ConnectionDialog(self, host="localhost", port=3306,
                               username="admin", password="")
        if dlg.exec_() == ConnectionDialog.Accepted:
            self.set_client(dlg.get_client())
        else:
            if not self.client:
                self.status_label.setText("Disconnected")

    def set_client(self, client: KosDBClient):
        self.client = client
        # Try to locate the server's data directory for local metadata reads.
        self.local = KosDBLocal(self._guess_data_dir())
        self.status_label.setText(f"Connected to {client.host}:{client.port} as {client.username}")

        # Replace tree panel
        if self.tree_panel:
            self.tree_layout.removeWidget(self.tree_panel)
            self.tree_panel.deleteLater()
        self.tree_label.setText(f"{client.host}:{client.port}")
        self.tree_panel = TreePanel(client)
        self.tree_panel.database_selected.connect(self.on_database_selected)
        self.tree_panel.table_selected.connect(self.on_table_selected)
        self.tree_layout.addWidget(self.tree_panel)
        self.tree_panel.refresh()

        # Add default query tab
        self.add_query_tab()

    def disconnect(self):
        if self.client:
            self.client.disconnect()
            self.client = None
        self.status_label.setText("Disconnected")
        self.tabs.clear()
        if self.tree_panel:
            self.tree_panel.deleteLater()
            self.tree_panel = None
        self.tree_label.setText("Not connected")

    def refresh_tree(self):
        if self.tree_panel:
            self.tree_panel.refresh()

    def export_database(self):
        if not self.client:
            QMessageBox.warning(self, "Not connected", "Connect to a server first.")
            return

        db_name, ok = QInputDialog.getText(self, "Export database", "Database name:")
        if not ok or not db_name.strip():
            return
        db_name = db_name.strip()

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export to SQL file", f"{db_name}.sql", "SQL dumps (*.sql);;All files (*.*)"
        )
        if not file_path:
            return

        try:
            result = self.client.export_database(db_name, file_path)
            QMessageBox.information(self, "Export complete", result)
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))

    def import_sql(self):
        if not self.client:
            QMessageBox.warning(self, "Not connected", "Connect to a server first.")
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import SQL file", "", "SQL dumps (*.sql);;All files (*.*)"
        )
        if not file_path:
            return

        try:
            result = self.client.import_sql(file_path)
            QMessageBox.information(self, "Import complete", result)
            self.refresh_tree()
        except Exception as e:
            QMessageBox.critical(self, "Import failed", str(e))

    def on_database_selected(self, db_name: str):
        pass

    def on_table_selected(self, db_name: str, table_name: str):
        self.open_table_tab(db_name, table_name)

    def add_query_tab(self):
        widget = QueryWidget(self.client)
        title = self._next_tab_title("Query")
        index = self.tabs.addTab(widget, title)
        self.tabs.setCurrentIndex(index)
        return widget

    def add_search_tab(self):
        widget = SearchWidget(self.client)
        title = self._next_tab_title("Search")
        index = self.tabs.addTab(widget, title)
        self.tabs.setCurrentIndex(index)
        return widget

    def _next_tab_title(self, prefix: str) -> str:
        existing = {self.tabs.tabText(i) for i in range(self.tabs.count())}
        n = 1
        while f"{prefix} {n}" in existing:
            n += 1
        return f"{prefix} {n}"

    def open_table_tab(self, db_name: str, table_name: str):
        title = f"{db_name}.{table_name}"
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == title:
                self.tabs.setCurrentIndex(i)
                return

        browser = TableBrowser(self.client, local=self.local)
        browser.load(db_name, table_name)
        index = self.tabs.addTab(browser, title)
        self.tabs.setCurrentIndex(index)

    def close_tab(self, index: int):
        widget = self.tabs.widget(index)
        self.tabs.removeTab(index)
        widget.deleteLater()

        # Always keep at least one query tab available.
        if self._query_tab_count() == 0 and self.client:
            self.add_query_tab()

    def show_about(self):
        QMessageBox.about(
            self, "About KosDBAdmin",
            "<b>KosDBAdmin</b><br>"
            "A PyQt5 administration client for KosDB.<br><br>"
            "Version 0.1.0"
        )

    def _query_tab_count(self) -> int:
        return sum(
            1 for i in range(self.tabs.count())
            if self.tabs.tabText(i).startswith("Query")
        )

    def _guess_data_dir(self) -> str:
        """Guess the KosDB server data directory."""
        base = os.path.dirname(os.path.abspath(__file__))
        candidates = [
            os.path.abspath(os.path.join(base, "..", "..", "..", "KosDB", "data")),
            os.path.abspath(os.path.join(base, "..", "..", "KosDB", "data")),
            os.path.abspath(os.path.join(base, "..", "KosDB", "data")),
            os.path.join(os.path.expanduser("~"), "Working", "Hobies", "KosDB", "data"),
            "/home/t3ch/Working/Hobies/KosDB/data",
            os.path.abspath("data"),
        ]
        for path in candidates:
            if os.path.isdir(path):
                return path
        return candidates[-1]

    def closeEvent(self, event):
        if self.client:
            self.client.disconnect()
        event.accept()
