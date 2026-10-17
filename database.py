import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "market_inventory.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Products table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        barcode TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        category TEXT,
        price REAL NOT NULL,
        cost_price REAL NOT NULL DEFAULT 0.0,
        stock INTEGER NOT NULL DEFAULT 0,
        min_stock INTEGER NOT NULL DEFAULT 10,
        optimal_stock INTEGER NOT NULL DEFAULT 50,
        supplier TEXT DEFAULT 'Genel Toptancı',
        expiry_date TEXT, -- YYYY-MM-DD Son Kullanma Tarihi
        created_at TEXT NOT NULL
    )
    """)

    # Migration check for existing databases
    cursor.execute("PRAGMA table_info(products)")
    columns = [col[1] for col in cursor.fetchall()]
    if "expiry_date" not in columns:
        cursor.execute("ALTER TABLE products ADD COLUMN expiry_date TEXT")


    # 2. Transactions table (Sales, Returns, Restocks, Adjustments)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        barcode TEXT NOT NULL,
        transaction_type TEXT NOT NULL, -- 'SALE', 'RETURN', 'RESTOCK'
        quantity INTEGER NOT NULL,
        price_per_unit REAL NOT NULL,
        total_price REAL NOT NULL,
        timestamp TEXT NOT NULL,
        notes TEXT,
        FOREIGN KEY (product_id) REFERENCES products(id)
    )
    """)

    # 3. AI Insights & Alerts table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ai_alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER,
        alert_type TEXT NOT NULL, -- 'RESTOCK', 'ANOMALY', 'DEAD_STOCK', 'TREND'
        severity TEXT NOT NULL,   -- 'DANGER', 'WARNING', 'INFO'
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        suggested_action TEXT,
        status TEXT NOT NULL DEFAULT 'ACTIVE', -- 'ACTIVE', 'DISMISSED'
        created_at TEXT NOT NULL,
        FOREIGN KEY (product_id) REFERENCES products(id)
    )
    """)

    # 4. AI Chat History
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role TEXT NOT NULL,
        message TEXT NOT NULL,
        timestamp TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at:", DB_PATH)
