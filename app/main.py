import os
import re
import io
import glob
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import streamlit as st
import frontmatter
import networkx as nx
from pyvis.network import Network
import markdown as md

WIKILINK_PATTERN = re.compile(r"\[\[([^\[\]]+)\]\]")


@dataclass
class Note:
    path: Path
    title: str
    content: str
    links: List[str]
    tags: List[str]


def normalize_title(name: str) -> str:
    # Map file stem to comparable title
    return name.strip().lower().replace(" ", "-")


def parse_note(path: Path) -> Note:
    raw = path.read_text(encoding="utf-8")
    post = frontmatter.loads(raw)

    body = post.content
    meta = post.metadata or {}

    # Title priority: frontmatter.title -> first H1 -> filename stem
    fm_title = str(meta.get("title")) if meta.get("title") else None
    h1_match = re.search(r"^#\s+(.+)$", body, flags=re.MULTILINE)
    h1_title = h1_match.group(1).strip() if h1_match else None
    file_title = path.stem
    title = fm_title or h1_title or file_title

    # Links
    links = [link.strip() for link in WIKILINK_PATTERN.findall(body)]

    # Tags
    tags = meta.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    return Note(path=path, title=title, content=body, links=links, tags=tags)


def index_notes(root: Path) -> Tuple[Dict[str, Note], Dict[str, Set[str]]]:
    notes: Dict[str, Note] = {}
    backlinks: Dict[str, Set[str]] = {}

    for file_path in root.rglob("*.md"):
        note = parse_note(file_path)
        key = normalize_title(Path(file_path).stem)
        notes[key] = note

    for key, note in notes.items():
        for link in note.links:
            link_key = normalize_title(link)
            backlinks.setdefault(link_key, set()).add(key)

    return notes, backlinks


def build_graph(notes: Dict[str, Note], backlinks: Dict[str, Set[str]], tag_filter: Optional[Set[str]] = None) -> nx.Graph:
    g = nx.Graph()

    # Add nodes
    for key, note in notes.items():
        include = True
        if tag_filter:
            include = bool(set(note.tags) & tag_filter)
        if include:
            g.add_node(key, label=note.title, existent=True, tags=note.tags)

    # Add edges and ghost nodes
    for src_key, note in notes.items():
        if src_key not in g:
            continue
        for link in note.links:
            dst_key = normalize_title(link)
            if dst_key not in g and dst_key not in notes:
                # ghost node
                g.add_node(dst_key, label=link, existent=False, tags=[])
            if dst_key in g:
                g.add_edge(src_key, dst_key)

    return g


def graph_to_pyvis(g: nx.Graph) -> Network:
    net = Network(height="650px", width="100%", bgcolor="#111", font_color="#ddd", notebook=False)
    net.barnes_hut()

    for node, data in g.nodes(data=True):
        color = "#7bd389" if data.get("existent") else "#888888"
        border = "#2e8540" if data.get("existent") else "#555555"
        shape = "dot"
        title = data.get("label", node)
        tags = data.get("tags") or []
        tooltip = f"<b>{title}</b><br>Tags: {', '.join(tags) if tags else '—'}"
        net.add_node(node, label=data.get("label", node), color=color, borderWidth=2, shape=shape, title=tooltip)

    for src, dst in g.edges():
        net.add_edge(src, dst, color="#5fa8d3")

    return net


def render_html(net: Network) -> str:
    # pyvis can generate a full HTML document string suitable for embedding
    return net.generate_html()


def render_markdown(content: str) -> str:
    # Convert markdown to HTML but keep [[links]] clickable via anchors with data-key
    def replace_wikilink(match: re.Match) -> str:
        inner = match.group(1).strip()
        key = normalize_title(inner)
        return f"<a href='#' data-note-key='{key}' class='wikilink'>[[{inner}]]</a>"

    content_with_links = WIKILINK_PATTERN.sub(replace_wikilink, content)
    return md.markdown(content_with_links, extensions=["fenced_code", "tables", "toc"])


def main() -> None:
    st.set_page_config(page_title="Notes Graph", layout="wide")

    st.sidebar.title("Notes Graph")
    default_root = Path(st.session_state.get("notes_root", str(Path.cwd() / "notes")))

    root_input = st.sidebar.text_input("Notes directory", value=str(default_root))
    root = Path(root_input).expanduser().resolve()
    st.session_state["notes_root"] = str(root)

    if not root.exists():
        st.sidebar.warning(f"Directory does not exist: {root}")
        if st.sidebar.button("Create directory"):
            root.mkdir(parents=True, exist_ok=True)
        st.stop()

    notes, backlinks = index_notes(root)

    # Sidebar: filters and search
    all_tags: List[str] = sorted({t for note in notes.values() for t in note.tags})
    selected_tags = st.sidebar.multiselect("Filter by tags", options=all_tags)
    tag_filter = set(selected_tags) if selected_tags else None

    search_query = st.sidebar.text_input("Search notes")

    # Pick note
    selectable = [(k, n.title) for k, n in notes.items() if (not tag_filter or (set(n.tags) & tag_filter))]
    selectable.sort(key=lambda x: x[1].lower())

    current_key = st.session_state.get("current_note_key")
    if current_key not in dict(selectable):
        current_key = selectable[0][0] if selectable else None

    current_key = st.sidebar.selectbox("Open note", options=[k for k, _ in selectable], format_func=lambda k: dict(selectable)[k] if selectable else k, index=( [k for k, _ in selectable].index(current_key) if current_key else 0 ) if selectable else None)
    st.session_state["current_note_key"] = current_key

    # Layout
    col_left, col_right = st.columns([0.55, 0.45])

    # Graph
    with col_right:
        g = build_graph(notes, backlinks, tag_filter)
        net = graph_to_pyvis(g)
        html = render_html(net)
        st.components.v1.html(html, height=680, scrolling=True)

    # Note content and backlinks
    with col_left:
        st.subheader(dict(selectable).get(current_key, current_key) if current_key else "Notes")

        if search_query:
            matches: List[Tuple[str, str]] = []
            for key, note in notes.items():
                hay = f"{note.title}\n{note.content}"
                if search_query.lower() in hay.lower():
                    matches.append((key, note.title))
            st.caption(f"Search results for '{search_query}'")
            for key, title in matches[:100]:
                st.write(f"- [{title}](#)  ")

        if current_key and current_key in notes:
            note = notes[current_key]
            html = render_markdown(note.content)
            st.markdown(html, unsafe_allow_html=True)

            # Backlinks
            st.divider()
            st.caption("Backlinks")
            refs = sorted([(k, notes[k].title) for k in backlinks.get(current_key, set()) if k in notes], key=lambda x: x[1].lower())
            if not refs:
                st.write("No backlinks")
            else:
                for k, title in refs:
                    st.write(f"- {title}")
        else:
            st.info("No note selected or note missing.")

    # New note creator
    st.sidebar.divider()
    st.sidebar.caption("Create note")
    new_title = st.sidebar.text_input("New note title")
    if st.sidebar.button("Create") and new_title.strip():
        key = normalize_title(new_title)
        filename = f"{key}.md"
        target = root / filename
        if target.exists():
            st.sidebar.error("Note already exists")
        else:
            target.write_text(f"# {new_title}\n\n", encoding="utf-8")
            st.session_state["current_note_key"] = key
            st.experimental_rerun()


if __name__ == "__main__":
    main()