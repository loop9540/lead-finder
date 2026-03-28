"""SQLite database layer for lead storage and run history."""

import sqlite3
from config import DB_PATH


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = _conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            domain TEXT DEFAULT '',
            platform TEXT NOT NULL,
            source TEXT NOT NULL,
            run_id INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(company_name, platform)
        );

        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            status TEXT DEFAULT 'pending',
            sources TEXT NOT NULL,
            existing_file TEXT DEFAULT '',
            total_raw INTEGER DEFAULT 0,
            total_deduped INTEGER DEFAULT 0,
            started_at TEXT DEFAULT (datetime('now')),
            finished_at TEXT,
            error_message TEXT DEFAULT '',
            output_file TEXT DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_leads_platform ON leads(platform);
        CREATE INDEX IF NOT EXISTS idx_leads_source ON leads(source);

        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER NOT NULL,
            first_name TEXT DEFAULT '',
            last_name TEXT DEFAULT '',
            title TEXT DEFAULT '',
            email TEXT DEFAULT '',
            email_status TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            linkedin TEXT DEFAULT '',
            company_name_9at TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (lead_id) REFERENCES leads(id)
        );

        CREATE INDEX IF NOT EXISTS idx_contacts_lead_id ON contacts(lead_id);
        CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email);
    """)
    conn.close()


def create_run(sources: list[str], existing_file: str = "") -> int:
    conn = _conn()
    cur = conn.execute(
        "INSERT INTO runs (sources, existing_file) VALUES (?, ?)",
        (",".join(sources), existing_file),
    )
    run_id = cur.lastrowid
    conn.commit()
    conn.close()
    return run_id


def update_run(run_id: int, **kwargs):
    conn = _conn()
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [run_id]
    conn.execute(f"UPDATE runs SET {sets} WHERE id = ?", vals)
    conn.commit()
    conn.close()


def get_run(run_id: int) -> dict | None:
    conn = _conn()
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_runs(limit: int = 20) -> list[dict]:
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def insert_leads(leads: list[dict], run_id: int):
    conn = _conn()
    for lead in leads:
        conn.execute(
            "INSERT OR IGNORE INTO leads (company_name, domain, platform, source, run_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (lead["company_name"], lead.get("domain", ""), lead["platform"], lead["source"], run_id),
        )
    conn.commit()
    conn.close()


def get_leads(platform: str = "", source: str = "", search: str = "",
              admin: str = "",
              page: int = 1, per_page: int = 50) -> tuple[list[dict], int]:
    conn = _conn()
    where = []
    params = []

    if platform:
        where.append("platform = ?")
        params.append(platform)
    if admin:
        where.append("admin = ?")
        params.append(admin)
    if source:
        where.append("source = ?")
        params.append(source)
    if search:
        where.append("company_name LIKE ?")
        params.append(f"%{search}%")

    clause = ("WHERE " + " AND ".join(where)) if where else ""

    total = conn.execute(f"SELECT COUNT(*) FROM leads {clause}", params).fetchone()[0]

    offset = (page - 1) * per_page
    rows = conn.execute(
        f"SELECT * FROM leads {clause} ORDER BY platform, company_name LIMIT ? OFFSET ?",
        params + [per_page, offset],
    ).fetchall()

    conn.close()
    return [dict(r) for r in rows], total


def get_stats() -> dict:
    conn = _conn()
    total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]

    platforms = conn.execute(
        "SELECT platform, COUNT(*) as cnt FROM leads WHERE platform != '' GROUP BY platform ORDER BY cnt DESC"
    ).fetchall()

    admins = conn.execute(
        "SELECT admin, COUNT(*) as cnt FROM leads WHERE admin != '' GROUP BY admin ORDER BY cnt DESC"
    ).fetchall()

    sources = conn.execute(
        "SELECT source, COUNT(*) as cnt FROM leads GROUP BY source ORDER BY cnt DESC"
    ).fetchall()

    conn.close()
    return {
        "total": total,
        "platforms": [dict(r) for r in platforms],
        "admins": [dict(r) for r in admins],
        "sources": [dict(r) for r in sources],
    }


def get_platforms() -> list[str]:
    conn = _conn()
    rows = conn.execute("SELECT DISTINCT platform FROM leads WHERE platform != '' ORDER BY platform").fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_sources() -> list[str]:
    conn = _conn()
    rows = conn.execute("SELECT DISTINCT source FROM leads ORDER BY source").fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_admins() -> list[str]:
    conn = _conn()
    rows = conn.execute("SELECT DISTINCT admin FROM leads WHERE admin != '' ORDER BY admin").fetchall()
    conn.close()
    return [r[0] for r in rows]


# ── Contacts ──────────────────────────────────────────────────────────

def init_contacts_table():
    """Ensure the contacts table exists (safe to call multiple times)."""
    conn = _conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER NOT NULL,
            first_name TEXT DEFAULT '',
            last_name TEXT DEFAULT '',
            title TEXT DEFAULT '',
            email TEXT DEFAULT '',
            email_status TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            linkedin TEXT DEFAULT '',
            company_name_9at TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (lead_id) REFERENCES leads(id)
        );
        CREATE INDEX IF NOT EXISTS idx_contacts_lead_id ON contacts(lead_id);
        CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email);
    """)
    conn.close()


def insert_contacts(contacts: list[dict], lead_id: int):
    """Insert a list of contact dicts for a given lead_id."""
    conn = _conn()
    for c in contacts:
        conn.execute(
            """INSERT INTO contacts
               (lead_id, first_name, last_name, title, email, email_status,
                phone, linkedin, company_name_9at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                lead_id,
                c.get("first_name", ""),
                c.get("last_name", ""),
                c.get("title", ""),
                c.get("email", ""),
                c.get("email_status", ""),
                c.get("phone", ""),
                c.get("linkedin", ""),
                c.get("company_name", ""),
            ),
        )
    conn.commit()
    conn.close()


def get_contacts_for_lead(lead_id: int) -> list[dict]:
    """Return all contacts associated with a specific lead."""
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM contacts WHERE lead_id = ? ORDER BY last_name, first_name",
        (lead_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_contacts(
    page: int = 1, per_page: int = 50, search: str = ""
) -> tuple[list[dict], int]:
    """Paginated contact listing with optional search across name/email/company."""
    conn = _conn()
    where = []
    params = []

    if search:
        where.append(
            "(first_name LIKE ? OR last_name LIKE ? OR email LIKE ? OR company_name_9at LIKE ?)"
        )
        s = f"%{search}%"
        params.extend([s, s, s, s])

    clause = ("WHERE " + " AND ".join(where)) if where else ""

    total = conn.execute(
        f"SELECT COUNT(*) FROM contacts {clause}", params
    ).fetchone()[0]

    offset = (page - 1) * per_page
    rows = conn.execute(
        f"""SELECT c.*, l.company_name as lead_company, l.platform, l.source
            FROM contacts c
            JOIN leads l ON c.lead_id = l.id
            {clause}
            ORDER BY c.company_name_9at, c.last_name
            LIMIT ? OFFSET ?""",
        params + [per_page, offset],
    ).fetchall()

    conn.close()
    return [dict(r) for r in rows], total
