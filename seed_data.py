import sqlite3
from datetime import datetime, timedelta
import random
from database import get_connection, init_db
from ai_engine import StockAIEngine

def seed():
    init_db()
    conn = get_connection()
    cursor = conn.cursor()

    # Mevcut veriyi kontrol et
    cursor.execute("SELECT COUNT(*) FROM products")
    if cursor.fetchone()[0] > 0:
        print("Veritabanında zaten ürünler kayıtlı. Seed atlandı.")
        conn.close()
        return

    print("Gerçekçi market ürünleri ve barkodları yükleniyor...")
    now = datetime.now()

    sample_products = [
        # (barcode, name, category, price, cost_price, stock, min_stock, optimal_stock, supplier)
        ("8690637010151", "Çaykur Rize Turist Çay 1000g", "Gıda", 185.00, 140.00, 6, 15, 60, "Çaykur Bölge Bayi"),
        ("8690562000104", "Sütaş Tam Yağlı Süt 1L", "Süt & Kahvaltılık", 38.50, 29.00, 4, 20, 80, "Sütaş Dağıtım"),
        ("8690504018082", "Ülker Çikolatalı Gofret 35g", "Atıştırmalık", 12.00, 8.50, 45, 30, 150, "Ülker Toptan"),
        ("5449000000996", "Coca-Cola Orijinal Tat 1L", "İçecek", 45.00, 34.00, 12, 25, 100, "Coca-Cola İçecek A.Ş."),
        ("8690533010019", "Eti Tutku Bisküvi 100g", "Atıştırmalık", 18.00, 13.00, 2, 20, 90, "Eti Gıda Dağıtım"),
        ("8690506000122", "Pınar Klasik Sucuk 225g", "Et & Şarküteri", 210.00, 165.00, 8, 10, 40, "Pınar Dağıtım"),
        ("8690526010019", "Tadım Kavrulmuş Siyah Ay Çekirdeği 180g", "Kuruyemiş", 42.00, 31.00, 28, 15, 60, "Tadım Toptan"),
        ("8690511000123", "Fairy Sıvı Bulaşık Deterjanı 650ml", "Temizlik", 68.00, 50.00, 35, 10, 40, "P&G Toptan Dağıtım"),
        ("8690530000101", "Duru Saf Sabun 4x150g", "Kişisel Bakım", 55.00, 40.00, 5, 15, 50, "Evrensel Kimya Bayi"),
        ("8690777000012", "Ekmek 200g (Somun)", "Fırın", 12.50, 9.00, 15, 30, 120, "Yerel Ekmek Fırını"),
        ("8690123456789", "Lüks İthal Kahve Çekirdeği 500g", "Kahve", 340.00, 260.00, 25, 5, 20, "Kahve Gurme İthalat"),
    ]

    for p in sample_products:
        cursor.execute("""
            INSERT INTO products (barcode, name, category, price, cost_price, stock, min_stock, optimal_stock, supplier, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (*p, now.strftime("%Y-%m-%d %H:%M:%S")))

    # Son 7 güne yayılan örnek geçmiş satış ve iade verisi oluşturalım
    # Böylece AI analiz motoru açıldığı ilk anda zeki tahminler ve anomaliler gösterebilir!
    cursor.execute("SELECT id, barcode, price, name FROM products")
    prods = [dict(r) for r in cursor.fetchall()]

    for days_back in range(7, 0, -1):
        dt = (now - timedelta(days=days_back, hours=random.randint(1, 10))).strftime("%Y-%m-%d %H:%M:%S")
        for p in prods:
            # Süt ve Çay çok satanlar olsun
            if "Süt" in p["name"] or "Çay" in p["name"]:
                sold_qty = random.randint(4, 9)
                cursor.execute("""
                    INSERT INTO transactions (product_id, barcode, transaction_type, quantity, price_per_unit, total_price, timestamp, notes)
                    VALUES (?, ?, 'SALE', ?, ?, ?, ?, 'Kasa Satışı')
                """, (p["id"], p["barcode"], sold_qty, p["price"], round(sold_qty * p["price"], 2), dt))

            # Gofret normal satış
            elif "Gofret" in p["name"] or "Coca-Cola" in p["name"]:
                sold_qty = random.randint(3, 7)
                cursor.execute("""
                    INSERT INTO transactions (product_id, barcode, transaction_type, quantity, price_per_unit, total_price, timestamp, notes)
                    VALUES (?, ?, 'SALE', ?, ?, ?, ?, 'Kasa Satışı')
                """, (p["id"], p["barcode"], sold_qty, p["price"], round(sold_qty * p["price"], 2), dt))

    # Anomali örneği: Sabun için son 2 günde 3 adet iade yapılmış olsun (AI anomaliyi hemen yakalasın!)
    duru = next((p for p in prods if "Duru" in p["name"]), None)
    if duru:
        recent_dt = (now - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO transactions (product_id, barcode, transaction_type, quantity, price_per_unit, total_price, timestamp, notes)
            VALUES (?, ?, 'RETURN', 3, ?, ?, ?, 'Müşteri İadesi - Paket hasarlı')
        """, (duru["id"], duru["barcode"], duru["price"], round(3 * duru["price"], 2), recent_dt))

    conn.commit()
    conn.close()

    # AI motorunu çalıştırıp ilk alarmları ürettir
    ai = StockAIEngine(get_connection)
    alerts = ai.analyze_all()
    print(f"Başlangıç verileri başarıyla yüklendi! AI {len(alerts)} adet tespit yaptı.")

if __name__ == "__main__":
    seed()
