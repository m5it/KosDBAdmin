# KosDBAdmin

A lightweight PyQt5 administration client for [KosDB](https://github.com/m5it/kosdb) — a LevelDB socket database with SQL-like command support.

KosDBAdmin provides a phpMyAdmin-like GUI for managing KosDB databases, tables, and data.

## Features

- Connect to a running KosDB server via TCP socket
- Browse databases and tables in a tree view
- Execute arbitrary SQL-like commands with syntax highlighting editor
- Browse table data with automatic column sizing
- View table structure (columns, primary key, indexes)
- Create/drop databases and tables from the UI

## Requirements

- Python 3.7+
- PyQt5
- A running KosDB server

## Installation

```bash
pip install -r requirements.txt
```

## Usage

Start KosDB server first:

```bash
cd ../KosDB
python server.py --prepare-admin admin --prepare-password admin
python server.py
```

Then run KosDBAdmin:

```bash
python main.py
```

Connect with host `localhost`, port `5555`, and your KosDB credentials.

## Project Structure

```
kosdbadmin/
  client.py              # KosDB socket client
  connection_dialog.py   # Login dialog
  main_window.py         # Main application window
  query_widget.py        # SQL editor + results
  table_browser.py       # Data and structure views
  tree_panel.py          # Database/table tree
  utils.py               # Helpers
main.py                  # Entry point
```

## License

MIT
