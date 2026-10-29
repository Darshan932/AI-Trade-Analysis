"""Tiny database layer that works with SQLite (default) and MySQL (PyMySQL).

Queries are written with '?' placeholders and converted for MySQL.  Each call opens a
short-lived connection, which keeps it safe under Flask's threaded dev server.
"""
import json
import sqlite3
from urllib.parse import urlparse, unquote


class Database:
    def __init__(self, url: str):
        self.url = url
        u = urlparse(url)
        self.dialect = "mysql" if u.scheme.startswith("mysql") else "sqlite"
        if self.dialect == "sqlite":
            self.path = url.replace("sqlite:///", "", 1)
        else:
            self.cfg = dict(host=u.hostname or "localhost", port=u.port or 3306, user=unquote(u.username or "root"),
                            password=unquote(u.password or ""), database=(u.path or "/").lstrip("/"), charset="utf8mb4")
        self.init()

    # ---------- connection ----------
    def _conn(self):
        if self.dialect == "sqlite":
            c = sqlite3.connect(self.path, check_same_thread=False)
            c.row_factory = sqlite3.Row
            return c
        import pymysql  # pip install pymysql
        return pymysql.connect(cursorclass=pymysql.cursors.DictCursor, autocommit=False, **self.cfg)

    def _sql(self, q):
        return q.replace("?", "%s") if self.dialect == "mysql" else q

    def _run(self, q, args=(), fetch=None, commit=False):
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute(self._sql(q), args)
            out = None
            if fetch == "all":
                out = [dict(r) for r in cur.fetchall()]
            elif fetch == "one":
                r = cur.fetchone()
                out = dict(r) if r else None
            last = cur.lastrowid
            if commit:
                conn.commit()
            return out if fetch else last
        finally:
            conn.close()

    # ---------- schema ----------
    def init(self):
        if self.dialect == "sqlite":
            ddl = """CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, timeframe TEXT, signal TEXT,
                confidence INTEGER, price REAL, source TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                result_json TEXT)"""
        else:
            ddl = """CREATE TABLE IF NOT EXISTS analyses (
                id INT AUTO_INCREMENT PRIMARY KEY, symbol VARCHAR(30), timeframe VARCHAR(10), signal_type VARCHAR(10),
                confidence INT, price DOUBLE, source VARCHAR(20), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                result_json LONGTEXT) CHARACTER SET utf8mb4"""
        self._run(ddl, commit=True)

    @property
    def _sig(self):  # "signal" is fine in SQLite; avoid reserved-word issues in MySQL
        return "signal_type" if self.dialect == "mysql" else "signal"

    # ---------- operations ----------
    def insert_analysis(self, symbol, timeframe, signal, confidence, price, source, result):
        return self._run(
            f"INSERT INTO analyses (symbol, timeframe, {self._sig}, confidence, price, source, result_json) VALUES (?,?,?,?,?,?,?)",
            (symbol, timeframe, signal, confidence, price, source, json.dumps(result)), commit=True)

    def list_analyses(self, limit=25):
        rows = self._run(
            f"SELECT id, symbol, timeframe, {self._sig} AS signal, confidence, price, source, created_at "
            f"FROM analyses ORDER BY id DESC LIMIT {int(limit)}", fetch="all")
        for r in rows:
            r["created_at"] = str(r["created_at"])
        return rows

    def get_analysis(self, aid):
        r = self._run("SELECT id, symbol, timeframe, created_at, result_json FROM analyses WHERE id = ?", (aid,), fetch="one")
        if not r:
            return None
        r["result"] = json.loads(r.pop("result_json"))
        r["created_at"] = str(r["created_at"])
        return r

    def delete_analysis(self, aid):
        self._run("DELETE FROM analyses WHERE id = ?", (aid,), commit=True)
