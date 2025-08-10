# Todoist-like Task App (Flask + SQLite)

A simple, local-first task manager inspired by Todoist. Supports projects, labels, priorities, due dates, quick-add parsing, and an HTMX-powered UI for fast interactions.

## Features
- Projects (default Inbox)
- Labels (`@label`)
- Priorities (`p1`..`p4`)
- Due dates ("today", "tomorrow", weekdays, or `YYYY-MM-DD`)
- Quick-add parsing from a single input (e.g. `Pay bills today #Finance @money p2`)
- Complete, edit, delete
- Search and filtering by project/label
- No accounts, local SQLite database

## Quickstart
1. (Recommended) Create a virtualenv and activate it
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the app:
   ```bash
   python -m flask --app todoist_app.app run --debug
   ```
   Then open `http://127.0.0.1:5000`.

## Notes
- The database is created automatically at first run in `instance/todo.db`.
- The default project is `Inbox`.
- Example quick-add: `Email Alice tomorrow @work #Comms p2`.