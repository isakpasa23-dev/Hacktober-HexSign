# HexSign AI Market Stok ve Barkod Kontrol Sistemi 🛒🤖

Klasik market USB barkod okuyucularıyla tam uyumlu çalışan, stok ve tedarik kararlarını otomatik olarak yöneten yapay zeka destekli stok ve kasa sistemi.

---

## 🚀 Hızlı Başlangıç

Sistem şu anda aktif olarak arka planda çalışmaktadır!

1. Tarayıcınızı açın ve adrese gidin:
   👉 **[http://localhost:8000](http://localhost:8000)**

2. İlerleyen zamanlarda sistemi tek tıkla başlatmak için:
   - Klasördeki `baslat.bat` dosyasına çift tıklamanız yeterlidir.

---

## ⚡ Klasik Barkod Okuyucu Entegrasyonu

Marketlerde kullanılan standart USB / Kablosuz el barkod okuyucuları (Honeywell, Datalogic, Zebra, Performa vb.) işletim sistemine **klavye (HID)** olarak bağlanır.

- **Otomatik Yakalama:** Ekranda nereye tıklamış olursanız olun, barkod okuyucu tetiğe basılıp okutulduğunda sistem karakter dizisini ve sonundaki Enter sinyalini anında yakalar.
- **Kasiyer Bip Sesi (Web Audio):** Barkod başarıyla okunduğunda gerçek süpermarket kasası "bip" sesi çalar. Kritik stok veya hata durumunda uyarı tonu verir.

### Kısayol Tuşları (Hızlı Mod Değiştirme)
- **F1 Tuşu:** 🟢 **SATIŞ Modu** (Okutulan ürünün stoku anında düşer, ciro kaydedilir).
- **F2 Tuşu:** 🟠 **İADE Modu** (Müşterinin geri getirdiği ürün stoka eklenir, AI iade anomalilerini denetler).
- **F3 Tuşu:** 🔵 **MAL GİRİŞİ / KABUL Modu** (Toptancıdan gelen ürünler stoka eklenir).

---

## 🧠 Yapay Zeka (AI) Stok Yönetimi Nasıl Çalışır?

Geleneksel yazılımlar sadece sayı düşerken, sistemdeki **StockAIEngine** stokları proaktif olarak yönetir:

1. **Tüketim Hızı & Tükenme Tahmini (Run-rate Velocity):**
   - Son 7 ve 30 günlük satış trendlerini analiz eder.
   - Her ürünün ortalama günlük satış hızını hesaplar ve *"Bu ürünün stoğu X gün sonra tamamen bitecek"* tahmini üretir.
2. **Otomatik Toptancı Sipariş Listesi:**
   - Kritik seviyedeki ve bitecek ürünleri toptancılarına göre gruplar.
   - Önerilen sipariş adetlerini ve toplam maliyetleri hesaplar. Tek tıkla WhatsApp veya e-posta için kopyalanabilir liste sunar.
3. **Şüpheli İade & Anomali Tespiti:**
   - Bir üründe kısa sürede aşırı iade yapıldığında (ör. parti/SKT bozukluğu veya kasiyer suistimali) kırmızı alarm verir.
4. **Durgun / Ölü Stok Alarmı:**
   - 14 gündür rafta kilitli kalan ve satılmayan ürünleri tespit eder, kampanya veya indirim önerir.
5. **Market Copilot (Doğal Dil Asistanı):**
   - Sağ alt panelden AI'a Türkçe sorular sorabilirsiniz:
     - *"En çok satan ürünler neler?"*
     - *"Hangi ürünlerin stoğu kritik?"*
     - *"Son iadeler neler?"*

---

## 📂 Dosya Yapısı

- `main.py`: FastAPI Web & REST API Sunucusu.
- `ai_engine.py`: Yapay zeka tahmin, anomali tespiti ve asistan motoru.
- `database.py`: SQLite veritabanı şeması ve bağlantı yönetimi.
- `seed_data.py`: Gerçek Türkiye barkodları (Çaykur, Sütaş, Ülker vb.) ve örnek satış geçmişi yükleyicisi.
- `static/index.html`: Modern, karanlık temalı kasa ve AI kontrol paneli.
- `static/app.js`: Barkod okuyucu buffer dinleyicisi, Web Audio ses motoru ve arayüz yöneticisi.
- `baslat.bat`: Tek tıkla başlatma betiği.
