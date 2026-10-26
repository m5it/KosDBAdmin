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
- Export databases or individual tables to SQL dump files
- Import SQL dump files through the connected server

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

Connect with host `localhost`, port `3306`, and your KosDB credentials.

### Export and Import

KosDBAdmin can export and import SQL dumps through the connected KosDB server (the server must be running).

- **Tools → Export database...** — export a whole database (e.g. `testdb`) or a single table (`testdb.users`) to a `.sql` file.
- **Tools → Import SQL...** — execute a `.sql` dump against the current server.
- Right-click a database in the tree → **Export database...**
- Right-click a table in the tree → **Export table...**

The generated dump uses plain SQL compatible with KosDB (`CREATE DATABASE`, `USE`, `DROP TABLE IF EXISTS`, `CREATE TABLE`, `SET TABLE ... next_id`, `INSERT`). When importing, existing tables are automatically recreated so the dump can be replayed cleanly.

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
