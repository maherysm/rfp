"""SQLite storage. List values (requirements, routes, ...) are stored as JSON text."""

import json
import os
import sqlite3

DB_PATH = os.environ.get("RFP_DB", os.path.join(os.path.dirname(__file__), "rfp.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS rfps (
    id INTEGER PRIMARY KEY, customer_email TEXT, status TEXT, quote TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS lanes (
    id INTEGER PRIMARY KEY, rfp_id INTEGER, origin TEXT, destination TEXT, tons REAL,
    max_days REAL, email TEXT, requirements TEXT DEFAULT '[]', route TEXT DEFAULT '[]',
    transit_days REAL, met TEXT DEFAULT '[]', unmet TEXT DEFAULT '[]', issue TEXT, price REAL);
CREATE TABLE IF NOT EXISTS emails (
    id INTEGER PRIMARY KEY, rfp_id INTEGER, direction TEXT, party TEXT, subject TEXT,
    body TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY, rfp_id INTEGER, agent TEXT, message TEXT,
    needs_human INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS proposals (
    id INTEGER PRIMARY KEY, rfp_id INTEGER, customer_email TEXT, lane_count INTEGER,
    total_tons REAL, total_value REAL, details TEXT, accepted_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS meetings (
    id INTEGER PRIMARY KEY, rfp_id INTEGER, title TEXT, starts_at TEXT, attendees TEXT);
"""

JSON_COLUMNS = {"requirements", "route", "met", "unmet", "details", "attendees"}


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init():
    conn = connect()
    conn.executescript(SCHEMA)
    conn.close()


def execute(sql, params=()):
    """Run one write statement; return (new row id, number of rows changed)."""
    conn = connect()
    try:
        cursor = conn.execute(sql, params)
        conn.commit()
        return cursor.lastrowid, cursor.rowcount
    finally:
        conn.close()


def query(sql, params=()):
    conn = connect()
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    result = []
    for row in rows:
        item = dict(row)
        for column in JSON_COLUMNS & item.keys():
            item[column] = json.loads(item[column]) if item[column] else []
        result.append(item)
    return result


def encode(value):
    return json.dumps(value) if isinstance(value, (list, dict)) else value


# Table and column names below always come from our code; user input only goes into `?` values.
def insert(table, **values):
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    row_id, _ = execute(
        f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
        [encode(v) for v in values.values()],
    )
    return row_id


def update(table, row_id, **values):
    assignments = ", ".join(f"{column} = ?" for column in values)
    execute(
        f"UPDATE {table} SET {assignments} WHERE id = ?",
        [encode(v) for v in values.values()] + [row_id],
    )
