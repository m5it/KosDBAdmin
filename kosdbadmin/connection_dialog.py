"""Connection/login dialog for KosDBAdmin."""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIntValidator
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QDialogButtonBox,
    QLabel, QMessageBox, QCheckBox
)

from kosdbadmin.client import KosDBClient, KosDBError


class ConnectionDialog(QDialog):
    """Dialog to collect KosDB connection details and authenticate."""

    def __init__(self, parent=None, host="localhost", port=5555,
                 username="", password=""):
        super().__init__(parent)
        self.setWindowTitle("Connect to KosDB")
        self.setMinimumWidth(360)

        self.client = None

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.host_edit = QLineEdit(host)
        self.port_edit = QLineEdit(str(port))
        self.port_edit.setValidator(QIntValidator(1, 65535))
        self.port_edit.setMaximumWidth(80)
        self.user_edit = QLineEdit(username)
        self.pass_edit = QLineEdit(password)
        self.pass_edit.setEchoMode(QLineEdit.Password)

        self.save_check = QCheckBox("Remember credentials (not encrypted)")
        self.save_check.setChecked(False)

        form.addRow("Host:", self.host_edit)
        form.addRow("Port:", self.port_edit)
        form.addRow("Username:", self.user_edit)
        form.addRow("Password:", self.pass_edit)
        layout.addLayout(form)
        layout.addWidget(self.save_check)

        self.status_label = QLabel("Enter connection details")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self.buttons.accepted.connect(self.try_connect)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def try_connect(self):
        host = self.host_edit.text().strip()
        try:
            port = int(self.port_edit.text().strip())
        except ValueError:
            QMessageBox.warning(self, "Invalid port", "Port must be a number.")
            return

        username = self.user_edit.text().strip()
        password = self.pass_edit.text()

        self.status_label.setText("Connecting...")
        self.setEnabled(False)

        client = KosDBClient(host=host, port=port,
                             username=username, password=password)
        try:
            client.connect()
            if not client.login():
                raise KosDBError("Authentication failed")
            client.enable_json()
            self.client = client
            self.status_label.setText("Connected")
            self.accept()
        except KosDBError as e:
            self.status_label.setText(f"Error: {e}")
            QMessageBox.critical(self, "Connection failed", str(e))
            client.disconnect()
        except Exception as e:
            self.status_label.setText(f"Error: {e}")
            QMessageBox.critical(self, "Connection failed", str(e))
            client.disconnect()
        finally:
            self.setEnabled(True)

    def get_client(self) -> KosDBClient:
        return self.client
