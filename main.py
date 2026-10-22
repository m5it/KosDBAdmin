#!/usr/bin/env python3
"""Entry point for KosDBAdmin."""

import sys
from PyQt5.QtWidgets import QApplication
from kosdbadmin.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("KosDBAdmin")
    app.setApplicationDisplayName("KosDBAdmin")

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
