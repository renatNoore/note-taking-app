import os
import re
from datetime import datetime, date, timedelta
from typing import List, Optional, Tuple

from dateutil import parser as date_parser
from flask import Flask, render_template, request, redirect, url_for, abort
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, select, Table, Column, Integer, ForeignKey
from sqlalchemy.orm import relationship


def create_app() -> Flask:
    app = Flask(__name__, instance_relative_config=True, template_folder="templates", static_folder="static")

    # Ensure instance folder exists
    os.makedirs(app.instance_path, exist_ok=True)

    db_path = os.path.join(app.instance_path, "todo.db")
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{db_path}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret"),
    )

    db = SQLAlchemy(app)

    # Association table for many-to-many Task<->Label
    task_labels: Table = Table(
        "task_labels",
        db.metadata,
        Column("task_id", Integer, ForeignKey("tasks.id"), primary_key=True),
        Column("label_id", Integer, ForeignKey("labels.id"), primary_key=True),
    )

    class Project(db.Model):
        __tablename__ = "projects"
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(100), unique=True, nullable=False)
        is_inbox = db.Column(db.Boolean, default=False, nullable=False)
        tasks = relationship("Task", back_populates="project", cascade="all, delete")

        def __repr__(self) -> str:
            return f"<Project {self.id} {self.name}>"

    class Label(db.Model):
        __tablename__ = "labels"
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(64), unique=True, nullable=False)
        tasks = relationship("Task", secondary=task_labels, back_populates="labels")

        def __repr__(self) -> str:
            return f"<Label {self.id} {self.name}>"

    class Task(db.Model):
        __tablename__ = "tasks"
        id = db.Column(db.Integer, primary_key=True)
        content = db.Column(db.Text, nullable=False)
        completed = db.Column(db.Boolean, default=False, nullable=False)
        priority = db.Column(db.Integer, default=1, nullable=False)
        due_date = db.Column(db.Date, nullable=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
        order_index = db.Column(db.Integer, default=0, nullable=False)

        project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)
        project = relationship("Project", back_populates="tasks")

        labels = relationship("Label", secondary=task_labels, back_populates="tasks")

        def __repr__(self) -> str:
            return f"<Task {self.id} {self.content[:20]}>"

    def ensure_seed() -> None:
        with app.app_context():
            db.create_all()
            inbox = Project.query.filter_by(is_inbox=True).first()
            if not inbox:
                inbox = Project(name="Inbox", is_inbox=True)
                db.session.add(inbox)
                db.session.commit()

    ensure_seed()

    # Helpers
    WEEKDAYS = {
        "monday": 0,
        "mon": 0,
        "tuesday": 1,
        "tue": 1,
        "wednesday": 2,
        "wed": 2,
        "thursday": 3,
        "thu": 3,
        "friday": 4,
        "fri": 4,
        "saturday": 5,
        "sat": 5,
        "sunday": 6,
        "sun": 6,
    }

    def parse_quick_add(text: str) -> Tuple[str, Optional[str], List[str], int, Optional[date]]:
        content_parts: List[str] = []
        labels: List[str] = []
        project_name: Optional[str] = None
        priority: int = 1
        due: Optional[date] = None

        tokens = text.split()
        skip_indices: set[int] = set()

        for idx, token in enumerate(tokens):
            lower = token.lower()
            if lower.startswith("@") and len(token) > 1:
                labels.append(token[1:])
                skip_indices.add(idx)
                continue
            if lower.startswith("#") and len(token) > 1:
                project_name = token[1:]
                skip_indices.add(idx)
                continue
            if lower in {"p1", "p2", "p3", "p4"}:
                priority = int(lower[1])
                skip_indices.add(idx)
                continue

        # Detect simple due words
        text_lower = text.lower()
        if " today" in f" {text_lower}" or text_lower.startswith("today"):
            due = date.today()
        elif " tomorrow" in f" {text_lower}" or text_lower.startswith("tomorrow"):
            due = date.today() + timedelta(days=1)
        else:
            # Look for "next <weekday>"
            for wname, windex in WEEKDAYS.items():
                if f"next {wname}" in text_lower:
                    today_idx = date.today().weekday()
                    days_ahead = (windex - today_idx + 7) % 7
                    if days_ahead == 0:
                        days_ahead = 7
                    due = date.today() + timedelta(days=days_ahead)
                    break
            # Try direct date parse (YYYY-MM-DD or similar)
            if due is None:
                try:
                    parsed_dt = date_parser.parse(text, fuzzy=True, default=datetime.combine(date.today(), datetime.min.time()))
                    if parsed_dt:
                        due = parsed_dt.date()
                except Exception:
                    pass

        for idx, token in enumerate(tokens):
            if idx in skip_indices:
                continue
            if token.lower() in {"today", "tomorrow"}:
                continue
            if token.lower().startswith("next") and any(token.lower().endswith(k) for k in WEEKDAYS.keys()):
                continue
            content_parts.append(token)

        content = " ".join(content_parts).strip()
        return content, project_name, labels, priority, due

    def get_or_create_project(name: Optional[str]) -> Project:
        if not name:
            return Project.query.filter_by(is_inbox=True).first()
        proj = Project.query.filter(func.lower(Project.name) == name.lower()).first()
        if proj:
            return proj
        proj = Project(name=name, is_inbox=False)
        db.session.add(proj)
        db.session.commit()
        return proj

    def get_or_create_label(name: str) -> Label:
        lbl = Label.query.filter(func.lower(Label.name) == name.lower()).first()
        if lbl:
            return lbl
        lbl = Label(name=name)
        db.session.add(lbl)
        db.session.commit()
        return lbl

    def base_query_filters(query, project: Optional[str], label: Optional[str], q: Optional[str], show_completed: bool):
        if project:
            query = query.join(Project).filter(func.lower(Project.name) == project.lower())
        if label:
            query = query.join(task_labels, Task.id == task_labels.c.task_id).join(Label, Label.id == task_labels.c.label_id).filter(func.lower(Label.name) == label.lower())
        if not show_completed:
            query = query.filter(Task.completed.is_(False))
        if q:
            like = f"%{q}%"
            query = query.filter(Task.content.ilike(like))
        return query

    @app.route("/")
    def index():
        project = request.args.get("project")
        label = request.args.get("label")
        q = request.args.get("q")
        show_completed = request.args.get("completed") == "1"

        tasks_query = Task.query
        tasks_query = base_query_filters(tasks_query, project, label, q, show_completed)
        tasks = (
            tasks_query
            .order_by(Task.completed.asc(), Task.order_index.asc(), Task.priority.desc(), Task.due_date.is_(None).asc(), Task.due_date.asc(), Task.created_at.asc())
            .all()
        )

        projects = Project.query.order_by(Project.is_inbox.desc(), Project.name.asc()).all()
        labels = Label.query.order_by(Label.name.asc()).all()

        if request.headers.get("HX-Request"):
            return render_template("_task_list.html", tasks=tasks)

        return render_template("index.html", tasks=tasks, projects=projects, labels=labels, current_project=project, current_label=label, q=q, show_completed=show_completed)

    @app.post("/tasks")
    def create_task():
        text = request.form.get("quick_add", "").strip()
        if not text:
            return redirect(url_for("index"))
        content, project_name, label_names, priority, due = parse_quick_add(text)
        if not content:
            content = text
        proj = get_or_create_project(project_name)
        max_order = db.session.execute(select(func.coalesce(func.max(Task.order_index), 0))).scalar_one()
        task = Task(content=content, project=proj, priority=priority, due_date=due, order_index=(max_order + 1))
        for ln in label_names:
            task.labels.append(get_or_create_label(ln))
        db.session.add(task)
        db.session.commit()
        # Return updated list for htmx partial swap
        project = request.args.get("project")
        label = request.args.get("label")
        q = request.args.get("q")
        show_completed = request.args.get("completed") == "1"
        tasks_query = base_query_filters(Task.query, project, label, q, show_completed)
        tasks = tasks_query.order_by(Task.completed.asc(), Task.order_index.asc(), Task.priority.desc(), Task.due_date.is_(None).asc(), Task.due_date.asc(), Task.created_at.asc()).all()
        return render_template("_task_list.html", tasks=tasks)

    @app.post("/tasks/<int:task_id>/toggle")
    def toggle_task(task_id: int):
        task = Task.query.get_or_404(task_id)
        task.completed = not task.completed
        db.session.commit()
        return render_template("_task_row.html", task=task)

    @app.post("/tasks/<int:task_id>/delete")
    def delete_task(task_id: int):
        task = Task.query.get_or_404(task_id)
        db.session.delete(task)
        db.session.commit()
        # return an empty row so htmx outerHTML swap removes it
        return ""

    @app.get("/tasks/<int:task_id>/edit")
    def edit_task(task_id: int):
        task = Task.query.get_or_404(task_id)
        projects = Project.query.order_by(Project.is_inbox.desc(), Project.name.asc()).all()
        labels = Label.query.order_by(Label.name.asc()).all()
        return render_template("_task_row.html", task=task, edit_mode=True, projects=projects, labels=labels)

    @app.post("/tasks/<int:task_id>/update")
    def update_task(task_id: int):
        task = Task.query.get_or_404(task_id)
        content = request.form.get("content", "").strip()
        priority = int(request.form.get("priority", task.priority) or task.priority)
        project_name = request.form.get("project")
        due_str = request.form.get("due")
        label_str = request.form.get("labels", "")
        if content:
            task.content = content
        task.priority = max(1, min(4, priority))
        if project_name:
            task.project = get_or_create_project(project_name)
        if due_str:
            try:
                task.due_date = date_parser.parse(due_str).date()
            except Exception:
                task.due_date = None
        else:
            task.due_date = None
        # Update labels
        names = [n.strip() for n in label_str.split(",") if n.strip()]
        task.labels.clear()
        for n in names:
            task.labels.append(get_or_create_label(n))
        db.session.commit()
        return render_template("_task_row.html", task=task)

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)