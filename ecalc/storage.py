"""Local SQLite storage: projects, saved calculations, AI usage log, PVGIS cache and
document index. One file (data/ecalc.db), excluded from git."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, client TEXT, location TEXT, notes TEXT,
    is_demo INTEGER DEFAULT 0, created TEXT, updated TEXT);
CREATE TABLE IF NOT EXISTS calculations (
    id INTEGER PRIMARY KEY, project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    kind TEXT, title TEXT, result_json TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS ai_usage (
    id INTEGER PRIMARY KEY, ts TEXT, provider TEXT, model TEXT, purpose TEXT,
    input_tokens INTEGER, output_tokens INTEGER, cost_usd REAL, ok INTEGER, error TEXT, duration_s REAL);
CREATE TABLE IF NOT EXISTS pvgis_cache (key TEXT PRIMARY KEY, response_json TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY, filename TEXT, sha256 TEXT UNIQUE, pages INTEGER, chars INTEGER, created TEXT);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY, doc_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    page INTEGER, text TEXT);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path | str | None = None):
        if path is None:
            config.ensure_data_dir()
            path = config.DB_PATH
        self.path = str(path)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)

    # ---- projects -------------------------------------------------------------------
    def create_project(self, name: str, client: str = "", location: str = "", notes: str = "",
                       is_demo: bool = False) -> int:
        if not name.strip():
            raise ValueError("Project name is required.")
        cur = self.conn.execute(
            "INSERT INTO projects(name, client, location, notes, is_demo, created, updated) VALUES (?,?,?,?,?,?,?)",
            (name.strip(), client, location, notes, int(is_demo), _now(), _now()))
        self.conn.commit()
        return cur.lastrowid

    def update_project(self, pid: int, client: str = "", location: str = "", notes: str = "") -> None:
        self.conn.execute("UPDATE projects SET client = ?, location = ?, notes = ?, updated = ? WHERE id = ?",
                          (client, location, notes, _now(), pid))
        self.conn.commit()

    def list_projects(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT p.*, COUNT(c.id) AS n_calcs FROM projects p LEFT JOIN calculations c ON c.project_id = p.id "
            "GROUP BY p.id ORDER BY p.updated DESC").fetchall()
        return [dict(r) for r in rows]

    def get_project(self, pid: int) -> dict | None:
        r = self.conn.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
        return dict(r) if r else None

    def delete_project(self, pid: int) -> None:
        self.conn.execute("DELETE FROM projects WHERE id = ?", (pid,))
        self.conn.commit()

    # ---- calculations ---------------------------------------------------------------
    def save_calculation(self, project_id: int, kind: str, title: str, result: dict[str, Any]) -> int:
        cur = self.conn.execute(
            "INSERT INTO calculations(project_id, kind, title, result_json, created) VALUES (?,?,?,?,?)",
            (project_id, kind, title, json.dumps(result), _now()))
        self.conn.execute("UPDATE projects SET updated = ? WHERE id = ?", (_now(), project_id))
        self.conn.commit()
        return cur.lastrowid

    def list_calculations(self, project_id: int | None = None) -> list[dict]:
        q = ("SELECT c.id, c.project_id, c.kind, c.title, c.created, p.name AS project FROM calculations c "
             "JOIN projects p ON p.id = c.project_id")
        args: tuple = ()
        if project_id is not None:
            q += " WHERE c.project_id = ?"
            args = (project_id,)
        return [dict(r) for r in self.conn.execute(q + " ORDER BY c.created DESC, c.id DESC", args)]

    def get_calculation(self, cid: int) -> dict | None:
        r = self.conn.execute("SELECT * FROM calculations WHERE id = ?", (cid,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["result"] = json.loads(d.pop("result_json"))
        return d

    def delete_calculation(self, cid: int) -> None:
        self.conn.execute("DELETE FROM calculations WHERE id = ?", (cid,))
        self.conn.commit()

    # ---- AI usage -------------------------------------------------------------------
    def log_usage(self, provider: str, model: str, purpose: str, input_tokens: int, output_tokens: int,
                  cost_usd: float, ok: bool, error: str = "", duration_s: float = 0.0) -> None:
        self.conn.execute(
            "INSERT INTO ai_usage(ts, provider, model, purpose, input_tokens, output_tokens, cost_usd, ok, error, "
            "duration_s) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (_now(), provider, model, purpose, input_tokens, output_tokens, cost_usd, int(ok), error[:300], duration_s))
        self.conn.commit()

    def month_spend_usd(self, month: str | None = None) -> float:
        month = month or datetime.now(timezone.utc).strftime("%Y-%m")
        r = self.conn.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM ai_usage WHERE substr(ts, 1, 7) = ?",
                              (month,)).fetchone()
        return float(r[0])

    def usage_rows(self, limit: int = 500) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM ai_usage ORDER BY id DESC LIMIT ?", (limit,))]

    # ---- PVGIS cache ----------------------------------------------------------------
    def get_pvgis(self, key: str) -> dict | None:
        r = self.conn.execute("SELECT response_json FROM pvgis_cache WHERE key = ?", (key,)).fetchone()
        return json.loads(r[0]) if r else None

    def put_pvgis(self, key: str, data: dict) -> None:
        self.conn.execute("INSERT OR REPLACE INTO pvgis_cache VALUES (?,?,?)", (key, json.dumps(data), _now()))
        self.conn.commit()

    # ---- documents ------------------------------------------------------------------
    def add_document(self, filename: str, sha256: str, pages: list[tuple[int, str]]) -> int:
        if self.conn.execute("SELECT 1 FROM documents WHERE sha256 = ?", (sha256,)).fetchone():
            raise ValueError("This document has already been uploaded.")
        cur = self.conn.execute("INSERT INTO documents(filename, sha256, pages, chars, created) VALUES (?,?,?,?,?)",
                                (filename, sha256, len(pages), sum(len(t) for _, t in pages), _now()))
        did = cur.lastrowid
        self.conn.executemany("INSERT INTO chunks(doc_id, page, text) VALUES (?,?,?)",
                              [(did, p, t) for p, t in pages])
        self.conn.commit()
        return did

    def list_documents(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM documents ORDER BY id DESC")]

    def all_chunks(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT c.id, c.doc_id, c.page, c.text, d.filename FROM chunks c JOIN documents d ON d.id = c.doc_id")]

    def delete_document(self, doc_id: int) -> None:
        self.conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        self.conn.commit()
