"""Floating dialog for adding/editing a column."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QComboBox,
    QCheckBox, QDialogButtonBox, QLabel, QMessageBox
)


class ColumnDialog(QDialog):
    """Modal dialog to add or edit a table column."""

    def __init__(self, parent=None, name="", col_type="TEXT", default="",
                 attribute="", edit_mode=False, allow_pk=False, is_pk=False,
                 allow_autoincrement=False):
        super().__init__(parent)
        self.setWindowTitle("Edit column" if edit_mode else "Add column")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit(name)
        self.name_edit.setPlaceholderText("Column name")
        form.addRow("Name:", self.name_edit)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["TEXT", "INTEGER", "REAL", "BOOLEAN", "JSON"])
        self.type_combo.setCurrentText(col_type.upper())
        form.addRow("Type:", self.type_combo)

        self.attr_combo = QComboBox()
        if is_pk:
            # Primary key columns cannot be changed to another attribute.
            self.attr_combo.addItems(["PRIMARY KEY"])
        elif edit_mode:
            # Existing non-PK columns can toggle INDEX or become PK if table has none.
            items = ["(none)", "INDEX"]
            if allow_pk:
                items.append("PRIMARY KEY")
            if allow_autoincrement:
                items.append("AUTO INCREMENT")
            self.attr_combo.addItems(items)
        elif allow_pk:
            items = ["(none)", "INDEX", "PRIMARY KEY"]
            if allow_autoincrement:
                items.append("AUTO INCREMENT")
            self.attr_combo.addItems(items)
        else:
            items = ["(none)", "INDEX"]
            if allow_autoincrement:
                items.append("AUTO INCREMENT")
            self.attr_combo.addItems(items)
        if attribute:
            self.attr_combo.setCurrentText(attribute)
        form.addRow("Attribute:", self.attr_combo)

        self.default_edit = QLineEdit(default)
        self.default_edit.setPlaceholderText("Default value (optional)")
        form.addRow("Default:", self.default_edit)

        if edit_mode:
            self.info_label = QLabel("Changes will recreate the table and re-insert existing rows.")
            self.info_label.setWordWrap(True)
            form.addRow("", self.info_label)

        layout.addLayout(form)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        self.buttons.accepted.connect(self.validate_and_accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def attribute(self) -> str:
        text = self.attr_combo.currentText()
        return "" if text == "(none)" else text

    def is_pk(self) -> bool:
        return self.attribute() == "PRIMARY KEY"

    def is_indexed(self) -> bool:
        return self.attribute() == "INDEX"

    def is_autoincrement(self) -> bool:
        return self.attribute() == "AUTO INCREMENT"

    def validate_and_accept(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Column name is required.")
            return
        if " " in name:
            QMessageBox.warning(self, "Validation", "Column name cannot contain spaces.")
            return
        self.accept()
