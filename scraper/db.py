"""
SQLite database for properties and auctions. Each record is stored as soon as it's fetched.
Scrapers write incrementally; no need to hold full dataset in memory.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "banglprop.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS properties (
        url TEXT PRIMARY KEY,
        id TEXT,
        source TEXT,
        status TEXT,
        name TEXT,
        builder TEXT,
        locality TEXT,
        price_min_lakhs REAL,
        price_max_lakhs REAL,
        price_display TEXT,
        handover TEXT,
        handover_year INTEGER,
        bhk TEXT,
        updated_at TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_properties_source ON properties(source);
    CREATE INDEX IF NOT EXISTS idx_properties_status ON properties(status);
    CREATE INDEX IF NOT EXISTS idx_properties_price ON properties(price_min_lakhs, price_max_lakhs);

    CREATE TABLE IF NOT EXISTS auctions (
        url TEXT PRIMARY KEY,
        id TEXT,
        name TEXT,
        description TEXT,
        price_display TEXT,
        price_lakhs REAL,
        emd_display TEXT,
        emd_lakhs REAL,
        sq_ft TEXT,
        bank_name TEXT,
        branch_name TEXT,
        contact TEXT,
        contact_person TEXT,
        contact_mobile TEXT,
        address TEXT,
        auction_start TEXT,
        auction_end TEXT,
        auction_datetime TEXT,
        category TEXT,
        source TEXT,
        updated_at TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_auctions_category ON auctions(category);
    CREATE INDEX IF NOT EXISTS idx_auctions_price ON auctions(price_lakhs);
    CREATE INDEX IF NOT EXISTS idx_auctions_bank ON auctions(bank_name);
    """)


def insert_property(conn: sqlite3.Connection, r: dict) -> None:
    init_schema(conn)
    conn.execute("""
    INSERT OR REPLACE INTO properties (
        url, id, source, status, name, builder, locality,
        price_min_lakhs, price_max_lakhs, price_display, handover, handover_year, bhk
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        (r.get("url") or "").strip() or None,
        (r.get("id") or "").strip() or None,
        (r.get("source") or "").strip() or None,
        (r.get("status") or "").strip() or None,
        (r.get("name") or "").strip()[:200] or None,
        (r.get("builder") or "").strip()[:100] or None,
        (r.get("locality") or "").strip()[:150] or None,
        r.get("price_min_lakhs"),
        r.get("price_max_lakhs"),
        (r.get("price_display") or "").strip()[:80] or None,
        (r.get("handover") or "").strip()[:50] or None,
        r.get("handover_year"),
        (r.get("bhk") or "").strip()[:30] or None,
    ))
    conn.commit()


def update_property(conn: sqlite3.Connection, url: str, r: dict) -> None:
    """Update existing property row by url with enriched fields."""
    if not url:
        return
    updates = []
    args = []
    for key in ("name", "builder", "locality", "price_min_lakhs", "price_max_lakhs", "price_display",
               "handover", "handover_year", "bhk", "status"):
        if key in r and r[key] is not None and r[key] != "":
            updates.append(f"{key} = ?")
            val = r[key]
            if key in ("name", "builder", "locality") and isinstance(val, str):
                val = val[:200] if key == "name" else val[:100] if key == "builder" else val[:150]
            args.append(val)
    if not updates:
        return
    args.append(url)
    conn.execute(
        "UPDATE properties SET " + ", ".join(updates) + ", updated_at = datetime('now') WHERE url = ?",
        args
    )
    conn.commit()


def get_property_urls_by_source(conn: sqlite3.Connection, source: str) -> list[str]:
    cur = conn.execute("SELECT url FROM properties WHERE source = ?", (source,))
    return [row[0] for row in cur.fetchall() if row[0]]


def insert_auction(conn: sqlite3.Connection, r: dict) -> None:
    init_schema(conn)
    conn.execute("""
    INSERT OR REPLACE INTO auctions (
        url, id, name, description, price_display, price_lakhs, emd_display, emd_lakhs,
        sq_ft, bank_name, branch_name, contact, contact_person, contact_mobile, address,
        auction_start, auction_end, auction_datetime, category, source
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        (r.get("url") or "").strip() or None,
        str(r.get("id") or "").strip() or None,
        (r.get("name") or "").strip()[:250] or None,
        (r.get("description") or "").strip()[:3000] or None,
        (r.get("price_display") or "").strip()[:80] or None,
        r.get("price_lakhs"),
        (r.get("emd_display") or "").strip()[:80] or None,
        r.get("emd_lakhs"),
        (r.get("sq_ft") or "").strip()[:50] or None,
        (r.get("bank_name") or "").strip()[:120] or None,
        (r.get("branch_name") or "").strip()[:120] or None,
        (r.get("contact") or "").strip()[:100] or None,
        (r.get("contact_person") or "").strip()[:80] or None,
        (r.get("contact_mobile") or "").strip()[:20] or None,
        (r.get("address") or "").strip()[:250] or None,
        (r.get("auction_start") or "").strip()[:50] or None,
        (r.get("auction_end") or "").strip()[:50] or None,
        (r.get("auction_datetime") or "").strip()[:50] or None,
        (r.get("category") or "").strip()[:50] or None,
        (r.get("source") or "").strip() or None,
    ))
    conn.commit()


def property_row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "url": row["url"],
        "id": row["id"],
        "source": row["source"],
        "status": row["status"],
        "name": row["name"],
        "builder": row["builder"],
        "locality": row["locality"],
        "price_min_lakhs": row["price_min_lakhs"],
        "price_max_lakhs": row["price_max_lakhs"],
        "price_display": row["price_display"],
        "handover": row["handover"],
        "handover_year": row["handover_year"],
        "bhk": row["bhk"],
    }


def auction_row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "url": row["url"],
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "price_display": row["price_display"],
        "price_lakhs": row["price_lakhs"],
        "emd_display": row["emd_display"],
        "emd_lakhs": row["emd_lakhs"],
        "sq_ft": row["sq_ft"],
        "bank_name": row["bank_name"],
        "branch_name": row["branch_name"],
        "contact": row["contact"],
        "contact_person": row["contact_person"],
        "contact_mobile": row["contact_mobile"],
        "address": row["address"],
        "auction_start": row["auction_start"],
        "auction_end": row["auction_end"],
        "auction_datetime": row["auction_datetime"],
        "category": row["category"],
        "source": row["source"],
    }
