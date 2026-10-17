import sqlite3
from datetime import datetime, timedelta
import math

class StockAIEngine:
    def __init__(self, db_conn_func):
        self.get_db = db_conn_func

    def analyze_all(self):
        """Tüm ürünleri analiz eder, stok tahminlerini yapar ve yeni alarmlar üretir."""
        alerts = []
        alerts.extend(self.check_stockouts_and_depletion())
        alerts.extend(self.check_return_anomalies())
        alerts.extend(self.check_slow_moving_stock())
        alerts.extend(self.check_expiration_dates())
        
        # Alarmları veritabanına kaydet (Mevcut aktif alarmları güncelle)
        self.sync_alerts_to_db(alerts)
        return alerts

    def check_stockouts_and_depletion(self):
        """Her ürünün son 7 ve 30 günlük satış hızına bakarak kaç günde tükeneceğini hesaplar."""
        conn = self.get_db()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM products")
        products = [dict(row) for row in cursor.fetchall()]
        
        alerts = []
        now = datetime.now()
        seven_days_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

        for p in products:
            p_id = p["id"]
            current_stock = p["stock"]
            min_stock = p["min_stock"]
            optimal_stock = p["optimal_stock"]

            # Son 7 günlük net satış miktarını bul
            cursor.execute("""
                SELECT 
                    COALESCE(SUM(CASE WHEN transaction_type = 'SALE' THEN quantity ELSE 0 END), 0) -
                    COALESCE(SUM(CASE WHEN transaction_type = 'RETURN' THEN quantity ELSE 0 END), 0) as net_sold
                FROM transactions 
                WHERE product_id = ? AND timestamp >= ?
            """, (p_id, seven_days_ago))
            
            row = cursor.fetchone()
            net_sold = row["net_sold"] if row and row["net_sold"] > 0 else 0
            daily_velocity = net_sold / 7.0 # Günlük ortalama satış hızı

            # Eğer hiç satış yoksa ama stok min_stock altındaysa
            if current_stock <= 0:
                suggested_order = optimal_stock
                alerts.append({
                    "product_id": p_id,
                    "alert_type": "RESTOCK",
                    "severity": "DANGER",
                    "title": f"TÜKENDİ: {p['name']}",
                    "message": f"{p['name']} tamamen tükendi! Rafta ürün kalmadı.",
                    "suggested_action": f"{p['supplier']} tedarikçisine derhal {suggested_order} adet sipariş geçilmeli."
                })
            elif daily_velocity > 0:
                days_left = current_stock / daily_velocity
                if days_left <= 2 or current_stock <= min_stock:
                    # Kritik stok eşiği
                    suggested_order = max(optimal_stock - current_stock, int(daily_velocity * 10))
                    severity = "DANGER" if days_left <= 2 else "WARNING"
                    alerts.append({
                        "product_id": p_id,
                        "alert_type": "RESTOCK",
                        "severity": severity,
                        "title": f"Stok Tükenme Riski: {p['name']}",
                        "message": f"Mevcut stok ({current_stock} adet), mevcut satış hızıyla (~{daily_velocity:.1f} adet/gün) yaklaşık {math.ceil(days_left)} gün içinde bitecek.",
                        "suggested_action": f"{p['supplier']} tedarikçisinden {suggested_order} adet yeni sipariş oluşturun."
                    })
            elif current_stock <= min_stock:
                suggested_order = optimal_stock - current_stock
                alerts.append({
                    "product_id": p_id,
                    "alert_type": "RESTOCK",
                    "severity": "WARNING",
                    "title": f"Kritik Eşik: {p['name']}",
                    "message": f"Stok miktarı ({current_stock} adet) belirlenen asgari sınırın ({min_stock}) altında.",
                    "suggested_action": f"{suggested_order} adet sipariş verilmesi önerilir."
                })

        conn.close()
        return alerts

    def check_return_anomalies(self):
        """Son 48 saatteki iade oranlarını inceleyerek anormal iadeleri tespit eder."""
        conn = self.get_db()
        cursor = conn.cursor()
        
        two_days_ago = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
            SELECT 
                p.id as product_id,
                p.name,
                COALESCE(SUM(CASE WHEN t.transaction_type = 'SALE' THEN t.quantity ELSE 0 END), 0) as total_sales,
                COALESCE(SUM(CASE WHEN t.transaction_type = 'RETURN' THEN t.quantity ELSE 0 END), 0) as total_returns
            FROM products p
            LEFT JOIN transactions t ON p.id = t.product_id AND t.timestamp >= ?
            GROUP BY p.id
            HAVING total_returns > 0
        """, (two_days_ago,))
        
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()

        alerts = []
        for r in rows:
            sales = r["total_sales"]
            returns = r["total_returns"]
            
            # Eğer son 2 günde iade sayısı 2'den fazla ve satışın %30'undan fazlaysa
            if returns >= 2 and (sales == 0 or (returns / max(1, sales)) >= 0.3):
                alerts.append({
                    "product_id": r["product_id"],
                    "alert_type": "ANOMALY",
                    "severity": "DANGER",
                    "title": f"Şüpheli İade Anomalisi: {r['name']}",
                    "message": f"Son 48 saatte {returns} adet iade yapıldı (Satış: {sales} adet). İade oranı anormal derecede yüksek!",
                    "suggested_action": "Parti/lot numarasını, son kullanma tarihini kontrol edin. Üründe bozukluk veya kasanızda suistimal şüphesi olabilir."
                })
        return alerts

    def check_slow_moving_stock(self):
        """Rafta çok olan ama 14 gündür neredeyse hiç satılmayan 'ölü stokları' tespit eder."""
        conn = self.get_db()
        cursor = conn.cursor()
        
        fourteen_days_ago = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
            SELECT 
                p.id as product_id,
                p.name,
                p.stock,
                p.price,
                COALESCE(SUM(CASE WHEN t.transaction_type = 'SALE' THEN t.quantity ELSE 0 END), 0) as sold_count
            FROM products p
            LEFT JOIN transactions t ON p.id = t.product_id AND t.timestamp >= ?
            WHERE p.stock >= 20
            GROUP BY p.id
            HAVING sold_count <= 1
        """, (fourteen_days_ago,))
        
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()

        alerts = []
        for r in rows:
            alerts.append({
                "product_id": r["product_id"],
                "alert_type": "DEAD_STOCK",
                "severity": "INFO",
                "title": f"Durgun / Yavaş Satılan Stok: {r['name']}",
                "message": f"Rafta {r['stock']} adet bulunmasına rağmen son 14 günde sadece {r['sold_count']} adet satıldı. Sermaye rafta kilitli.",
                "suggested_action": f"Fiyatı %15-20 indirmeyi veya '2 Al 1 Öde' gibi bir kasa önü kampanyası düzenlemeyi düşünün."
            })
        return alerts

    def check_expiration_dates(self):
        """Ürünlerin Son Kullanma Tarihlerini (SKT) denetler ve yaklaşan/geçenleri raporlar."""
        conn = self.get_db()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, name, barcode, stock, expiry_date FROM products WHERE expiry_date IS NOT NULL AND expiry_date != ''")
        products = [dict(r) for r in cursor.fetchall()]
        conn.close()

        alerts = []
        today = datetime.now().date()

        for p in products:
            try:
                exp_date = datetime.strptime(p["expiry_date"], "%Y-%m-%d").date()
                days_left = (exp_date - today).days

                if days_left < 0:
                    alerts.append({
                        "product_id": p["id"],
                        "alert_type": "EXPIRY",
                        "severity": "DANGER",
                        "title": f"🛑 SKT GEÇMİŞ: {p['name']}",
                        "message": f"Bu ürünün son kullanma tarihi ({p['expiry_date']}) {abs(days_left)} gün önce dolmuş! Rafta {p['stock']} adet var.",
                        "suggested_action": "Ürünü derhal raftan ve kasadan toplayın, satışını durdurun!"
                    })
                elif days_left <= 7:
                    alerts.append({
                        "product_id": p["id"],
                        "alert_type": "EXPIRY",
                        "severity": "WARNING" if days_left > 2 else "DANGER",
                        "title": f"⏳ SKT Yaklaştı: {p['name']} ({days_left} gün kaldı)",
                        "message": f"Son kullanma tarihine ({p['expiry_date']}) sadece {days_left} gün kaldı. Raftaki miktar: {p['stock']} adet.",
                        "suggested_action": "Kasa önüne taşıyın veya %30-%50 'Günü Yaklaşan Ürün' indirimi uygulayın."
                    })
            except Exception:
                continue

        return alerts

    def sync_alerts_to_db(self, alerts):
        """Tespit edilen alarmları veritabanına ekler (mükerrer kayıtları engeller)."""
        conn = self.get_db()
        cursor = conn.cursor()
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Mevcut aktif alarmları temizleyip güncel olanları yazalım
        cursor.execute("DELETE FROM ai_alerts WHERE status = 'ACTIVE'")
        
        for a in alerts:
            cursor.execute("""
                INSERT INTO ai_alerts (product_id, alert_type, severity, title, message, suggested_action, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE', ?)
            """, (a.get("product_id"), a["alert_type"], a["severity"], a["title"], a["message"], a.get("suggested_action"), now))

        conn.commit()
        conn.close()

    def generate_smart_order_list(self):
        """Toptancılara gönderilebilecek akıllı sipariş listesini oluşturur."""
        conn = self.get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT p.*,
                COALESCE(SUM(CASE WHEN t.transaction_type = 'SALE' THEN t.quantity ELSE 0 END), 0) / 7.0 as daily_velocity
            FROM products p
            LEFT JOIN transactions t ON p.id = t.product_id 
                AND t.timestamp >= datetime('now', '-7 days')
            GROUP BY p.id
        """)
        products = [dict(r) for r in cursor.fetchall()]
        conn.close()

        orders_by_supplier = {}
        for p in products:
            stock = p["stock"]
            min_stock = p["min_stock"]
            optimal = p["optimal_stock"]
            velocity = p["daily_velocity"] or 0

            # Eğer stok kritik seviyede ise
            if stock <= min_stock or (velocity > 0 and (stock / velocity) <= 3):
                needed = max(optimal - stock, 10)
                sup = p["supplier"] or "Genel Dağıtım"
                if sup not in orders_by_supplier:
                    orders_by_supplier[sup] = []

                cost = round(needed * p["cost_price"], 2)
                orders_by_supplier[sup].append({
                    "product_id": p["id"],
                    "barcode": p["barcode"],
                    "name": p["name"],
                    "current_stock": stock,
                    "recommended_order": needed,
                    "unit_cost": p["cost_price"],
                    "total_cost": cost,
                    "reason": "Tükendi" if stock == 0 else f"{int(stock / max(velocity, 0.1))} gün kaldı"
                })

        return orders_by_supplier

    def ask_ai_assistant(self, user_query: str) -> str:
        """Kullanıcının Türkçe sorularına market verilerini analiz ederek yanıt verir."""
        conn = self.get_db()
        cursor = conn.cursor()

        q = user_query.lower()

        # 1. En çok satanlar
        if "çok satan" in q or "popüler" in q or "en fazla satan" in q:
            cursor.execute("""
                SELECT p.name, SUM(t.quantity) as total_qty, SUM(t.total_price) as revenue
                FROM transactions t
                JOIN products p ON t.product_id = p.id
                WHERE t.transaction_type = 'SALE'
                GROUP BY p.id
                ORDER BY total_qty DESC
                LIMIT 5
            """)
            rows = cursor.fetchall()
            conn.close()
            if not rows:
                return "Henüz yeterli satış verisi bulunmamaktadır."
            res = "📊 **En Çok Satan Ürünler:**\n"
            for idx, r in enumerate(rows, 1):
                res += f"{idx}. **{r['name']}** - {r['total_qty']} adet satıldı (Ciro: {r['revenue']:.2f} TL)\n"
            return res

        # 2. Stok durumu / Kritik stoklar / Ne sipariş etmeliyim
        if "kritik" in q or "tüken" in q or "sipariş" in q or "bitecek" in q or "azalan" in q:
            cursor.execute("""
                SELECT name, stock, min_stock, supplier FROM products WHERE stock <= min_stock ORDER BY stock ASC
            """)
            rows = cursor.fetchall()
            conn.close()
            if not rows:
                return "✅ Harika haber! Şu an kritik eşiğin altına inmiş hiçbir ürününüz yok. Stok durumunuz güvenli."
            res = f"⚠️ **Dikkat: {len(rows)} adet ürün kritik stok seviyesinde veya tükendi:**\n"
            for r in rows:
                status = "🛑 TÜKENDİ" if r['stock'] == 0 else f"⚠️ Kalan: {r['stock']} adet (Kritik Eşik: {r['min_stock']})"
                res += f"- **{r['name']}**: {status} (Tedarikçi: {r['supplier']})\n"
            res += "\n💡 *Öneri: 'Sipariş Listesi Oluştur' butonunu kullanarak toptancınıza tek tıkla sipariş geçebilirsiniz.*"
            return res

        # 3. İadeler / Anomali sorgusu
        if "iade" in q or "sorun" in q or "anomali" in q:
            cursor.execute("""
                SELECT p.name, COUNT(t.id) as return_times, SUM(t.quantity) as return_qty
                FROM transactions t
                JOIN products p ON t.product_id = p.id
                WHERE t.transaction_type = 'RETURN'
                GROUP BY p.id
                ORDER BY return_qty DESC
                LIMIT 5
            """)
            rows = cursor.fetchall()
            conn.close()
            if not rows:
                return "✅ Son dönemde herhangi bir iade işlemi gerçekleşmedi."
            res = "🔄 **İade Yapılan Ürünler:**\n"
            for r in rows:
                res += f"- **{r['name']}**: Toplam {r['return_qty']} adet iade ({r['return_times']} işlem)\n"
            return res

        # 4. Son Kullanma Tarihi (SKT) / Bozulma sorgusu
        if "skt" in q or "tarih" in q or "bozul" in q or "son kullanma" in q:
            today = datetime.now().date()
            cursor.execute("SELECT name, stock, expiry_date FROM products WHERE expiry_date IS NOT NULL AND expiry_date != ''")
            items = [dict(r) for r in cursor.fetchall()]
            conn.close()

            expired = []
            expiring_soon = []

            for item in items:
                try:
                    exp = datetime.strptime(item["expiry_date"], "%Y-%m-%d").date()
                    diff = (exp - today).days
                    if diff < 0:
                        expired.append((item, abs(diff)))
                    elif diff <= 7:
                        expiring_soon.append((item, diff))
                except Exception:
                    continue

            if not expired and not expiring_soon:
                return "✅ Tüm ürünlerin son kullanma tarihleri güvenli! Yakın zamanda tarihi geçecek ürün bulunmuyor."

            res = "📅 **Son Kullanma Tarihi (SKT) Durumu:**\n"
            if expired:
                res += "🛑 **TARİHİ GEÇMİŞ ÜRÜNLER (Acil Toplanmalı):**\n"
                for item, days in expired:
                    res += f"- **{item['name']}**: {days} gün önce doldu! (Rafta: {item['stock']} adet, SKT: {item['expiry_date']})\n"
            if expiring_soon:
                res += "\n⏳ **GÜNÜ YAKLAŞANLAR (1 Hafta İçinde Bitecekler):**\n"
                for item, days in expiring_soon:
                    res += f"- **{item['name']}**: {days} gün kaldı (Rafta: {item['stock']} adet, SKT: {item['expiry_date']})\n"
                res += "\n💡 *Öneri: Günü yaklaşan ürünleri kasa önüne alıp %30 indirim etiketi basabilirsiniz.*"
            return res

        # 4. Toplam durum / Ciro / Genel Özet
        cursor.execute("SELECT COUNT(*) as total_prod, SUM(stock) as total_items FROM products")
        p_stat = cursor.fetchone()
        
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN transaction_type = 'SALE' THEN total_price ELSE 0 END), 0) as total_rev,
                COALESCE(SUM(CASE WHEN transaction_type = 'RETURN' THEN total_price ELSE 0 END), 0) as total_refund,
                COUNT(*) as total_trans
            FROM transactions
        """)
        t_stat = cursor.fetchone()
        conn.close()

        net_rev = t_stat['total_rev'] - t_stat['total_refund']
        return (
            f"🤖 **Market AI Asistanı Özeti:**\n"
            f"- Toplam Ürün Çeşidi: **{p_stat['total_prod']} çeşit**\n"
            f"- Depo ve Raftaki Toplam Adet: **{p_stat['total_items']} adet**\n"
            f"- Toplam Net Satış Hacmi: **{net_rev:.2f} TL**\n"
            f"- Gerçekleşen İşlem Sayısı: **{t_stat['total_trans']} işlem**\n\n"
            f"Bana şunları sorabilirsiniz:\n"
            f"• *'En çok hangi ürünler sattı?'*\n"
            f"• *'Hangi ürünlerin stoğu kritik veya tükendi?'*\n"
            f"• *'Son zamanlarda hangi ürünler iade edildi?'*"
        )
