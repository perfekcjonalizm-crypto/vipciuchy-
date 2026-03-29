"""
db.py — inicjalizacja SQLite i helpery
"""
import sqlite3
import os

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "rzeczy.db"))


def get_db():
    """Zwraca połączenie z bazą; row_factory = dict."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db():
    """Tworzy tabele jeśli nie istnieją."""
    conn = get_db()
    cur = conn.cursor()

    cur.executescript("""
    -- ── UŻYTKOWNICY ─────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS users (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        username      TEXT    UNIQUE NOT NULL,
        email         TEXT    UNIQUE NOT NULL,
        password_hash TEXT    NOT NULL,
        avatar        TEXT    DEFAULT '',
        created_at    TEXT    DEFAULT (datetime('now','localtime'))
    );

    -- ── PRODUKTY ─────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS products (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT    NOT NULL,
        brand       TEXT    NOT NULL,
        price       REAL    NOT NULL,
        size        TEXT    NOT NULL DEFAULT '—',
        condition   TEXT    NOT NULL DEFAULT 'Dobry',
        emoji       TEXT    DEFAULT '👗',
        description TEXT    DEFAULT '',
        images      TEXT    DEFAULT '[]',
        seller_id   INTEGER REFERENCES users(id) ON DELETE SET NULL,
        is_sold     INTEGER DEFAULT 0,
        created_at  TEXT    DEFAULT (datetime('now','localtime'))
    );

    -- ── ULUBIONE ──────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS favorites (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL REFERENCES users(id)    ON DELETE CASCADE,
        product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
        created_at TEXT    DEFAULT (datetime('now','localtime')),
        UNIQUE(user_id, product_id)
    );

    -- ── ZAMÓWIENIA ────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS orders (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id     INTEGER REFERENCES products(id) ON DELETE SET NULL,
        buyer_id       INTEGER REFERENCES users(id)   ON DELETE SET NULL,
        seller_id      INTEGER REFERENCES users(id)   ON DELETE SET NULL,
        amount         REAL    NOT NULL,
        platform_fee   REAL    NOT NULL,
        seller_amount  REAL    NOT NULL,
        payment_method TEXT    DEFAULT 'blik',
        status         TEXT    DEFAULT 'pending',
        created_at     TEXT    DEFAULT (datetime('now','localtime'))
    );

    -- ── WIADOMOŚCI ────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS messages (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        from_user_id INTEGER REFERENCES users(id)    ON DELETE SET NULL,
        to_user_id   INTEGER REFERENCES users(id)    ON DELETE SET NULL,
        product_id   INTEGER REFERENCES products(id) ON DELETE SET NULL,
        content      TEXT    NOT NULL,
        created_at   TEXT    DEFAULT (datetime('now','localtime'))
    );

    -- ── TOKENY WERYFIKACYJNE ──────────────────────────────────────
    CREATE TABLE IF NOT EXISTS verification_tokens (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        type       TEXT    NOT NULL,  -- 'email' lub 'phone'
        code       TEXT    NOT NULL,
        expires_at TEXT    NOT NULL,
        used       INTEGER DEFAULT 0
    );

    -- ── ZGŁOSZENIA ────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS reports (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        reporter_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        target_type TEXT    NOT NULL CHECK(target_type IN ('product','user')),
        target_id   INTEGER NOT NULL,
        reason      TEXT    NOT NULL,
        status      TEXT    DEFAULT 'pending' CHECK(status IN ('pending','reviewed','dismissed')),
        created_at  TEXT    DEFAULT (datetime('now','localtime'))
    );

    -- ── PRÓBY LOGOWANIA ───────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS login_attempts (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        ip         TEXT,
        username   TEXT,
        success    INTEGER DEFAULT 0,
        created_at TEXT    DEFAULT (datetime('now','localtime'))
    );

    -- ── OCENY ─────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS reviews (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        reviewer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        reviewed_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        order_id    INTEGER REFERENCES orders(id) ON DELETE SET NULL,
        rating      INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
        comment     TEXT    DEFAULT '',
        created_at  TEXT    DEFAULT (datetime('now','localtime')),
        UNIQUE(reviewer_id, order_id)
    );

    -- ── INDEKSY ───────────────────────────────────────────────────
    CREATE INDEX IF NOT EXISTS idx_reviews_reviewed ON reviews(reviewed_id);
    CREATE INDEX IF NOT EXISTS idx_products_seller  ON products(seller_id);
    CREATE INDEX IF NOT EXISTS idx_products_sold    ON products(is_sold);
    CREATE INDEX IF NOT EXISTS idx_messages_product ON messages(product_id);
    CREATE INDEX IF NOT EXISTS idx_messages_users   ON messages(from_user_id, to_user_id);
    CREATE INDEX IF NOT EXISTS idx_verify_user      ON verification_tokens(user_id, type);
    CREATE INDEX IF NOT EXISTS idx_orders_buyer     ON orders(buyer_id);
    CREATE INDEX IF NOT EXISTS idx_orders_seller    ON orders(seller_id);
    CREATE INDEX IF NOT EXISTS idx_favorites_product ON favorites(product_id);
    CREATE INDEX IF NOT EXISTS idx_reports_target   ON reports(target_type, target_id);
    CREATE INDEX IF NOT EXISTS idx_reports_status   ON reports(status);
    CREATE INDEX IF NOT EXISTS idx_login_ip         ON login_attempts(ip, created_at);
    """)

    conn.commit()

    # Migracje — dodaj kolumny jeśli brakuje (istniejąca baza)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "phone"          not in cols: conn.execute("ALTER TABLE users ADD COLUMN phone TEXT DEFAULT ''")
    if "email_verified" not in cols: conn.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER DEFAULT 0")
    if "phone_verified" not in cols: conn.execute("ALTER TABLE users ADD COLUMN phone_verified INTEGER DEFAULT 0")
    if "is_active"      not in cols: conn.execute("ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1")
    if "is_admin"       not in cols: conn.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
    if "is_banned"      not in cols: conn.execute("ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0")
    if "failed_logins"  not in cols: conn.execute("ALTER TABLE users ADD COLUMN failed_logins INTEGER DEFAULT 0")
    if "locked_until"   not in cols: conn.execute("ALTER TABLE users ADD COLUMN locked_until TEXT")
    if "bio"         not in cols: conn.execute("ALTER TABLE users ADD COLUMN bio TEXT DEFAULT ''")
    if "city"        not in cols: conn.execute("ALTER TABLE users ADD COLUMN city TEXT DEFAULT ''")
    if "address"     not in cols: conn.execute("ALTER TABLE users ADD COLUMN address TEXT DEFAULT ''")
    if "postal_code" not in cols: conn.execute("ALTER TABLE users ADD COLUMN postal_code TEXT DEFAULT ''")
    if "avatar_url"  not in cols: conn.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT DEFAULT ''")
    if "stripe_account_id" not in cols: conn.execute("ALTER TABLE users ADD COLUMN stripe_account_id TEXT DEFAULT ''")
    if "stripe_connected"  not in cols: conn.execute("ALTER TABLE users ADD COLUMN stripe_connected INTEGER DEFAULT 0")
    conn.commit()

    prod_cols = [r[1] for r in conn.execute("PRAGMA table_info(products)").fetchall()]
    if "is_flagged"  not in prod_cols: conn.execute("ALTER TABLE products ADD COLUMN is_flagged INTEGER DEFAULT 0")
    if "flag_reason" not in prod_cols: conn.execute("ALTER TABLE products ADD COLUMN flag_reason TEXT DEFAULT ''")
    if "status"    not in prod_cols: conn.execute("ALTER TABLE products ADD COLUMN status TEXT DEFAULT 'available'")
    if "is_hidden" not in prod_cols: conn.execute("ALTER TABLE products ADD COLUMN is_hidden INTEGER DEFAULT 0")
    if "category"  not in prod_cols: conn.execute("ALTER TABLE products ADD COLUMN category TEXT DEFAULT ''")
    conn.commit()

    msg_cols = [r[1] for r in conn.execute("PRAGMA table_info(messages)").fetchall()]
    if "is_read"   not in msg_cols: conn.execute("ALTER TABLE messages ADD COLUMN is_read INTEGER DEFAULT 0")
    if "msg_type"  not in msg_cols: conn.execute("ALTER TABLE messages ADD COLUMN msg_type TEXT DEFAULT 'text'")
    # product_id może być NULL gdy wiadomość jest ogólna (nie do konkretnej oferty)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_thread
        ON messages(from_user_id, to_user_id, created_at)
    """)
    conn.commit()

    # Migracje orders — escrow
    order_cols = [r[1] for r in conn.execute("PRAGMA table_info(orders)").fetchall()]
    if "escrow_status"             not in order_cols: conn.execute("ALTER TABLE orders ADD COLUMN escrow_status TEXT DEFAULT 'paid_held'")
    if "stripe_payment_intent_id"  not in order_cols: conn.execute("ALTER TABLE orders ADD COLUMN stripe_payment_intent_id TEXT DEFAULT ''")
    if "tracking_number"           not in order_cols: conn.execute("ALTER TABLE orders ADD COLUMN tracking_number TEXT DEFAULT ''")
    if "shipped_at"                not in order_cols: conn.execute("ALTER TABLE orders ADD COLUMN shipped_at TEXT")
    if "delivered_at"              not in order_cols: conn.execute("ALTER TABLE orders ADD COLUMN delivered_at TEXT")
    if "payout_at"                 not in order_cols: conn.execute("ALTER TABLE orders ADD COLUMN payout_at TEXT")
    if "auto_release_at"           not in order_cols: conn.execute("ALTER TABLE orders ADD COLUMN auto_release_at TEXT")
    if "shipping_carrier"   not in order_cols: conn.execute("ALTER TABLE orders ADD COLUMN shipping_carrier TEXT DEFAULT ''")
    if "shipping_service"   not in order_cols: conn.execute("ALTER TABLE orders ADD COLUMN shipping_service TEXT DEFAULT ''")
    if "shipping_point_id"  not in order_cols: conn.execute("ALTER TABLE orders ADD COLUMN shipping_point_id TEXT DEFAULT ''")
    if "shipping_amount"    not in order_cols: conn.execute("ALTER TABLE orders ADD COLUMN shipping_amount REAL DEFAULT 0")
    if "shipping_recipient" not in order_cols: conn.execute("ALTER TABLE orders ADD COLUMN shipping_recipient TEXT DEFAULT ''")
    conn.commit()

    # Tabela disputes
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS disputes (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id    INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
        reporter_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        reason      TEXT NOT NULL,
        description TEXT DEFAULT '',
        status      TEXT DEFAULT 'open' CHECK(status IN ('open','resolved_release','resolved_refund','closed')),
        admin_note  TEXT DEFAULT '',
        created_at  TEXT DEFAULT (datetime('now','localtime'))
    );
    CREATE INDEX IF NOT EXISTS idx_disputes_order  ON disputes(order_id);
    CREATE INDEX IF NOT EXISTS idx_disputes_status ON disputes(status);
    """)
    conn.commit()

    # Tabela przesyłek
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS shipments (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id            INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
        carrier             TEXT NOT NULL,
        service             TEXT DEFAULT '',
        sender_name         TEXT DEFAULT '',
        sender_phone        TEXT DEFAULT '',
        sender_address      TEXT DEFAULT '',
        recipient_name      TEXT DEFAULT '',
        recipient_phone     TEXT DEFAULT '',
        recipient_address   TEXT DEFAULT '',
        point_id            TEXT DEFAULT '',
        parcel_size         TEXT DEFAULT 'small',
        weight              REAL DEFAULT 1.0,
        price               REAL DEFAULT 0,
        external_id         TEXT DEFAULT '',
        label_url           TEXT DEFAULT '',
        tracking_number     TEXT DEFAULT '',
        tracking_status     TEXT DEFAULT 'created',
        tracking_events     TEXT DEFAULT '[]',
        tracking_updated_at TEXT,
        created_at          TEXT DEFAULT (datetime('now','localtime'))
    );
    CREATE INDEX IF NOT EXISTS idx_shipments_order   ON shipments(order_id);
    CREATE INDEX IF NOT EXISTS idx_shipments_tracking ON shipments(tracking_number);
    """)
    conn.commit()

    # Tabela historii statusów zamówień
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS order_status_history (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id   INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
        actor_id   INTEGER REFERENCES users(id) ON DELETE SET NULL,
        actor_role TEXT    NOT NULL CHECK(actor_role IN ('buyer','seller','system','admin')),
        from_status TEXT   NOT NULL,
        to_status   TEXT   NOT NULL,
        note        TEXT   DEFAULT '',
        created_at  TEXT   DEFAULT (datetime('now','localtime'))
    );
    CREATE INDEX IF NOT EXISTS idx_osh_order ON order_status_history(order_id);
    """)
    conn.commit()

    conn.close()
    print(f"[db] Baza danych gotowa: {DB_PATH}")
