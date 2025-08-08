# Notes Graph App (Obsidian-like)

Local-first markdown notes with wiki-links `[[Note Title]]`, frontmatter, and a graph view.

## Features
- Markdown notes in a folder
- Wiki-links `[[like this]]`
- Backlinks panel
- Tag parsing from YAML frontmatter (`tags: [a, b]`)
- Interactive graph view of notes
- Full-text search

## Quickstart
1. Create and activate a virtualenv (optional)
2. Install deps:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the app:
   ```bash
   streamlit run app/main.py
   ```
4. By default it loads notes from `notes/`. Change in the left sidebar.

## Notes Format
- Files end with `.md`
- Use `[[Wiki Link]]` to link notes by title (file stem). If a note does not exist yet, it will be shown as a dashed node in the graph.
- YAML frontmatter is supported at the top:
  ```yaml
  ---
  title: Optional custom title
  tags: [personal, idea]
  ---
  ```

## Dev
- Hot-reloads on file changes
- Python 3.10+