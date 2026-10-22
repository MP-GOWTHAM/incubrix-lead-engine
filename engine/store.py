"""SQLite state: candidates, parsed feeds, lead verdicts and stable lead IDs across runs."""

import csv
import json
import os
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS candidates (
  key TEXT PRIMARY KEY, feed_url TEXT, data TEXT, first_seen TEXT, last_seen TEXT, hits INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS feeds (
  feed_url TEXT PRIMARY KEY, fetched_at REAL, status TEXT, error TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS leads (
  key TEXT PRIMARY KEY, lead_id TEXT UNIQUE, status TEXT, data TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS searches (
  url TEXT PRIMARY KEY, done_at REAL, results INTEGER);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS registry (key TEXT PRIMARY KEY, lead_id TEXT UNIQUE);
"""


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        self.lock = threading.Lock()

    def close(self):
        self.db.commit()
        self.db.close()

    # candidates ------------------------------------------------------------
    def upsert_candidate(self, c, now_iso):
        """Returns True if new. Repeat sightings of the same show only bump a counter."""
        with self.lock:
            cur = self.db.execute("SELECT 1 FROM candidates WHERE key=?", (c["key"],))
            if cur.fetchone():
                self.db.execute("UPDATE candidates SET last_seen=?, hits=hits+1, data=? WHERE key=?",
                                (now_iso, json.dumps(c), c["key"]))
                return False
            self.db.execute("INSERT INTO candidates(key, feed_url, data, first_seen, last_seen) VALUES(?,?,?,?,?)",
                            (c["key"], c["feedUrl"], json.dumps(c), now_iso, now_iso))
            return True

    def candidates(self):
        return [json.loads(r[0]) for r in self.db.execute("SELECT data FROM candidates ORDER BY first_seen, key")]

    def candidate_count(self):
        return self.db.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]

    # feeds -----------------------------------------------------------------
    def feed(self, url):
        r = self.db.execute("SELECT fetched_at, status, error, data FROM feeds WHERE feed_url=?", (url,)).fetchone()
        if not r:
            return None
        return {"fetched_at": r[0], "status": r[1], "error": r[2], "data": json.loads(r[3]) if r[3] else None}

    def put_feed(self, url, status, data=None, error=None):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO feeds VALUES(?,?,?,?,?)",
                            (url, time.time(), status, error, json.dumps(data) if data else None))

    # leads -----------------------------------------------------------------
    def put_lead(self, lead, now_iso):
        with self.lock:
            prev = self.db.execute("SELECT lead_id FROM leads WHERE key=?", (lead["key"],)).fetchone()
            lid = prev[0] if prev else None
            self.db.execute("INSERT OR REPLACE INTO leads(key, lead_id, status, data, updated_at) VALUES(?,?,?,?,?)",
                            (lead["key"], lid, lead["status"], json.dumps(lead), now_iso))

    def leads(self):
        out = []
        for key, lid, data in self.db.execute("SELECT key, lead_id, data FROM leads"):
            d = json.loads(data)
            d["lead_id"] = lid
            out.append(d)
        return out

    def load_registry(self, path):
        """Seed IDs from the committed registry so a fresh machine reproduces the same lead_ids."""
        if not os.path.exists(path):
            return 0
        with open(path, encoding="utf-8", newline="") as f:
            rows = [(r["stable_creator_id"], r["lead_id"]) for r in csv.DictReader(f)]
        with self.lock:
            self.db.executemany("INSERT OR IGNORE INTO registry VALUES(?,?)", rows)
            top = max((int(l[1:]) for _, l in rows), default=0)
            if int(self.meta("next_lead_num") or 1) <= top:
                self.set_meta("next_lead_num", str(top + 1))
        return len(rows)

    def write_registry(self, path):
        rows = self.db.execute("SELECT key, lead_id FROM leads WHERE lead_id IS NOT NULL "
                               "UNION SELECT key, lead_id FROM registry ORDER BY 2").fetchall()
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["stable_creator_id", "lead_id"])
            w.writerows(rows)
        os.replace(tmp, path)

    def assign_lead_id(self, key):
        """IDs are permanent: once a creator gets L00042 it keeps it on every refresh and every machine."""
        with self.lock:
            r = self.db.execute("SELECT lead_id FROM leads WHERE key=?", (key,)).fetchone()
            if r and r[0]:
                return r[0]
            reg = self.db.execute("SELECT lead_id FROM registry WHERE key=?", (key,)).fetchone()
            if reg:
                self.db.execute("UPDATE leads SET lead_id=? WHERE key=?", (reg[0], key))
                return reg[0]
            n = int(self.meta("next_lead_num") or 1)
            lid = f"L{n:05d}"
            self.db.execute("UPDATE leads SET lead_id=? WHERE key=?", (lid, key))
            self.set_meta("next_lead_num", str(n + 1))
            return lid

    # searches & meta ---------------------------------------------------------
    def search_done(self, url, results):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO searches VALUES(?,?,?)", (url, time.time(), results))

    def meta(self, k):
        r = self.db.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return r[0] if r else None

    def set_meta(self, k, v):
        self.db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (k, v))

    def commit(self):
        with self.lock:
            self.db.commit()
