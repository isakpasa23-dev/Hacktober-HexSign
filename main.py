from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import os

from database import get_connection, init_db
from ai_engine import StockAIEngine

# Uygulama ve Dizin Yapısı
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)

app = FastAPI(title="AI Destekli Market Stok & Kasa Sistemi", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# AI Motoru
ai_engine = StockAIEngine(get_connection)

# Veritabanını başlat
init_db()

# --- Modeller ---
class ScanRequest(BaseModel):
    barcode: str
    mode: str = "SALE"  # 'SALE', 'RETURN', 'RESTOCK'
    quantity: int = 1
    notes: Optional[str] = None

class ProductCreate(BaseModel):
    barcode: str
    name: str
    category: Optional[str] = "Genel"
    price: float
    cost_price: Optional[float] = 0.0
    stock: int = 0
    min_stock: Optional[int] = 10
    optimal_stock: Optional[int] = 50
    supplier: Optional[str] = "Genel Toptancı"
    expiry_date: Optional[str] = None # YYYY-MM-DD Son Kullanma Tarihi

class ChatRequest(BaseModel):
    query: str

# --- API Uç Noktaları ---

@app.get("/api/stats")
def get_stats():
    """Özet gösterge paneli istatistikleri."""
    conn = get_connection()
    cursor = conn.cursor()

    today_str = datetime.now().strftime("%Y-%m-%d")

    # Toplam ürün ve stok adedi
    cursor.execute("SELECT COUNT(*) as sku_count, COALESCE(SUM(stock), 0) as total_units FROM products")
    p_stat = dict(cursor.fetchone())

    # Kritik stok adedi
    cursor.execute("SELECT COUNT(*) as critical_count FROM products WHERE stock <= min_stock")
    critical_stat = cursor.fetchone()["critical_count"]

    # Bugünkü satış ve iadeler
    cursor.execute("""
        SELECT 
            COALESCE(SUM(CASE WHEN transaction_type = 'SALE' THEN total_price ELSE 0 END), 0) as today_sales,
            COALESCE(SUM(CASE WHEN transaction_type = 'RETURN' THEN total_price ELSE 0 END), 0) as today_returns,
            COUNT(CASE WHEN transaction_type = 'SALE' THEN 1 END) as sale_count,
            COUNT(CASE WHEN transaction_type = 'RETURN' THEN 1 END) as return_count
        FROM transactions
        WHERE timestamp LIKE ?
    """, (f"{today_str}%",))
    t_stat = dict(cursor.fetchone())

    # Aktif AI alarmları sayısı
    cursor.execute("SELECT COUNT(*) as alert_count FROM ai_alerts WHERE status = 'ACTIVE'")
    alert_stat = cursor.fetchone()["alert_count"]

    # Yaklaşan veya geçen SKT sayısı
    cursor.execute("""
        SELECT COUNT(*) as exp_count 
        FROM products 
        WHERE expiry_date IS NOT NULL 
          AND expiry_date != '' 
          AND expiry_date <= date('now', '+7 days')
    """)
    exp_stat = cursor.fetchone()["exp_count"]

    conn.close()

    return {
        "sku_count": p_stat["sku_count"],
        "total_units": p_stat["total_units"],
        "critical_count": critical_stat,
        "expiring_count": exp_stat,
        "today_sales": round(t_stat["today_sales"], 2),
        "today_returns": round(t_stat["today_returns"], 2),
        "sale_count": t_stat["sale_count"],
        "return_count": t_stat["return_count"],
        "active_alerts": alert_stat
    }

@app.post("/api/scan")
def process_barcode_scan(payload: ScanRequest):
    """
    Klasik el barkod okuyucusunun okuduğu barkodu anında işler.
    Mod: 'SALE' (Satış), 'RETURN' (İade), 'RESTOCK' (Stok Girişi)
    """
    barcode = payload.barcode.strip()
    mode = payload.mode.upper()
    qty = max(1, payload.quantity)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM products WHERE barcode = ?", (barcode,))
    product = cursor.fetchone()

    if not product:
        conn.close()
        return {
            "success": False,
            "found": False,
            "barcode": barcode,
            "message": f"'{barcode}' barkodlu ürün bulunamadı. Yeni ürün olarak kaydedebilirsiniz."
        }

    product = dict(product)
    p_id = product["id"]
    current_stock = product["stock"]
    price = product["price"]

    # Stok hesaplaması
    if mode == "SALE":
        new_stock = current_stock - qty
        note = payload.notes or "Barkod Satışı"
    elif mode == "RETURN":
        new_stock = current_stock + qty
        note = payload.notes or "Müşteri İadesi"
    elif mode == "RESTOCK":
        new_stock = current_stock + qty
        note = payload.notes or "Mal Kabul / Stok Girişi"
    else:
        conn.close()
        raise HTTPException(status_code=400, detail="Geçersiz işlem modu.")

    total_amount = round(qty * price, 2)

    # 1. Stok güncelle
    cursor.execute("UPDATE products SET stock = ? WHERE id = ?", (new_stock, p_id))

    # 2. İşlem geçmişi yaz
    cursor.execute("""
        INSERT INTO transactions (product_id, barcode, transaction_type, quantity, price_per_unit, total_price, timestamp, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (p_id, barcode, mode, qty, price, total_amount, now_str, note))

    conn.commit()
    conn.close()

    # 3. AI Analizini tetikle (anında stok tükenmesi veya anomali kontrolü)
    alerts = ai_engine.analyze_all()

    # Bu ürüne özel yeni bir kritik durum var mı kontrol et
    product_alert = next((a for a in alerts if a.get("product_id") == p_id), None)

    return {
        "success": True,
        "found": True,
        "mode": mode,
        "product": {
            "id": p_id,
            "name": product["name"],
            "barcode": barcode,
            "price": price,
            "previous_stock": current_stock,
            "current_stock": new_stock,
            "min_stock": product["min_stock"],
            "optimal_stock": product["optimal_stock"]
        },
        "transaction": {
            "quantity": qty,
            "total_price": total_amount,
            "timestamp": now_str,
            "notes": note
        },
        "ai_alert": product_alert,
        "message": f"İşlem başarılı! {product['name']} - Yeni Stok: {new_stock}"
    }

@app.get("/api/products")
def list_products(search: Optional[str] = None, critical_only: bool = False):
    """Tüm ürünleri listeler veya arama yapar."""
    conn = get_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM products WHERE 1=1"
    params = []

    if search:
        query += " AND (name LIKE ? OR barcode LIKE ? OR category LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term])

    if critical_only:
        query += " AND stock <= min_stock"

    query += " ORDER BY id DESC"
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

@app.post("/api/products")
def create_product(product: ProductCreate):
    """Yeni bir ürün tanımlar."""
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        cursor.execute("""
            INSERT INTO products (barcode, name, category, price, cost_price, stock, min_stock, optimal_stock, supplier, expiry_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            product.barcode.strip(),
            product.name.strip(),
            product.category or "Genel",
            product.price,
            product.cost_price or 0.0,
            product.stock,
            product.min_stock or 10,
            product.optimal_stock or 50,
            product.supplier or "Genel Toptancı",
            product.expiry_date.strip() if product.expiry_date else None,
            now_str
        ))
        conn.commit()
        pid = cursor.lastrowid
        conn.close()
        return {"success": True, "id": pid, "message": f"{product.name} başarıyla eklendi."}
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Ürün eklenemedi: {str(e)}")

@app.put("/api/products/{product_id}")
def update_product(product_id: int, product: ProductCreate):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE products 
        SET barcode=?, name=?, category=?, price=?, cost_price=?, stock=?, min_stock=?, optimal_stock=?, supplier=?, expiry_date=?
        WHERE id=?
    """, (
        product.barcode.strip(), product.name.strip(), product.category, product.price,
        product.cost_price, product.stock, product.min_stock, product.optimal_stock, product.supplier,
        product.expiry_date.strip() if product.expiry_date else None,
        product_id
    ))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Ürün güncellendi."}

@app.delete("/api/products/{product_id}")
def delete_product(product_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products WHERE id=?", (product_id,))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Ürün silindi."}

@app.get("/api/transactions")
def list_transactions(limit: int = 50):
    """Son işlemleri (satış, iade, stok girişi) listeler."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.*, p.name as product_name
        FROM transactions t
        LEFT JOIN products p ON t.product_id = p.id
        ORDER BY t.id DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

@app.get("/api/ai/analysis")
def get_ai_analysis():
    """AI Motorunun güncel analiz ve alarmlarını çeker."""
    alerts = ai_engine.analyze_all()
    orders = ai_engine.generate_smart_order_list()
    return {
        "alerts": alerts,
        "smart_orders": orders
    }

@app.post("/api/ai/chat")
def ai_chat(payload: ChatRequest):
    """AI Market Asistanı ile sohbet / soru-cevap."""
    answer = ai_engine.ask_ai_assistant(payload.query)
    return {"answer": answer}

# Statik Arayüz Dosyaları
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def serve_index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    return FileResponse(index_file)
