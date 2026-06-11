# Panduan Intraday Trading dengan ai-saham
## Untuk Pemula — Lengkap dari Persiapan sampai Eksekusi

---

## Daftar Isi

1. [Apa itu Intraday Trading?](#1-apa-itu-intraday-trading)
2. [Jam Bursa IDX yang Wajib Kamu Tahu](#2-jam-bursa-idx-yang-wajib-kamu-tahu)
3. [Konsep Penting Sebelum Mulai](#3-konsep-penting-sebelum-mulai)
4. [Cara Kerja Pre-Open Screener](#4-cara-kerja-pre-open-screener)
5. [Memahami Setiap Indikator](#5-memahami-setiap-indikator)
6. [Workflow Harian Step-by-Step](#6-workflow-harian-step-by-step)
7. [Membaca Output Screener](#7-membaca-output-screener)
8. [Kapan Harus Masuk, Kapan Harus Lewat](#8-kapan-harus-masuk-kapan-harus-lewat)
9. [Manajemen Risiko](#9-manajemen-risiko)
10. [Paper Trade Journal — Validasi Sebelum Uang Sungguhan](#10-paper-trade-journal)
11. [Kesalahan Umum Pemula](#11-kesalahan-umum-pemula)
12. [Glosarium](#12-glosarium)

---

## 1. Apa itu Intraday Trading?

Intraday trading berarti kamu membuka dan menutup posisi di **hari yang sama**. Tidak ada posisi yang dibawa bermalam. Keuntungan (dan kerugian) ditentukan sepenuhnya oleh pergerakan harga dalam satu sesi perdagangan.

**Mengapa orang memilih intraday?**
- Tidak terekspos risiko berita malam hari (laporan keuangan, geopolitik)
- Modal bisa diputar lebih cepat
- Tidak perlu menahan saham yang turun berhari-hari

**Mengapa intraday lebih sulit dari swing trading?**
- Waktu keputusan sangat sempit
- Biaya transaksi (komisi + pajak) memakan margin lebih besar secara proporsional
- Psikologi lebih berat — harga bergerak setiap detik

**Tool ini membantu kamu dengan:** identifikasi kandidat sebelum pasar buka, menentukan di harga berapa masuk, dan di harga berapa keluar rugi. Tool ini **tidak** mengeksekusi order — kamu tetap yang memutuskan.

---

## 2. Jam Bursa IDX yang Wajib Kamu Tahu

```
08:45 – 09:00  PRE-OPEN AUCTION       ← Kamu bekerja di sini
09:00          PASAR BUKA (Regular Market)
09:00 – 11:30  SESI 1
11:30 – 13:30  ISTIRAHAT (Jumat: 11:30 – 14:00)
13:30 – 15:49  SESI 2
15:50 – 16:00  PRE-CLOSE AUCTION
16:00          HARGA PENUTUPAN RESMI
```

### Memahami Pre-Open Auction (08:45–09:00)

Ini bagian **paling penting** untuk intraday trader.

Selama 15 menit ini, investor memasukkan order beli/jual tapi **tidak ada matching yang terjadi**. Bursa hanya mengumpulkan semua order. Pada tepat 09:00, sistem menemukan satu harga yang memaksimalkan volume yang bisa dieksekusi — inilah harga pembukaan (opening price).

**Implikasinya untuk kamu:**
- Kamu tidak bisa "lihat bid terbaik lalu masuk 1 tick di atas" — bid yang kamu lihat pukul 08:52 belum tentu menjadi opening price
- Opening price bisa lebih tinggi ATAU lebih rendah dari bid manapun yang terlihat sebelum 09:00
- Strategi yang tepat: identifikasi kandidat saham dulu, lalu setelah 09:00 dan opening price diketahui, baru putuskan masuk atau tidak

---

## 3. Konsep Penting Sebelum Mulai

### IEV — Intraday Expected Volume

IEV adalah estimasi volume (dalam lot) yang akan ditransaksikan saat opening, dihitung dari order-order yang masuk selama pre-open auction.

**Cara membacanya:**
- IEV tinggi = banyak pihak (institusi + ritel) yang sudah antri order → saham ini akan ramai diperdagangkan
- IEV rendah = sedikit minat → spread lebar, susah keluar kalau salah arah

**Contoh nyata:**
```
BBCA  IEV: 450,000 lots  ← banyak order, likuid
ABCD  IEV:   8,000 lots  ← sepi, hindari untuk intraday
```

**Threshold default tool ini: IEV ≥ 100,000 lots.** Artinya hanya saham dengan aktivitas pre-open yang signifikan yang masuk daftar.

**Peringatan:** IEV tinggi tidak berarti harga pasti naik. Ia hanya mengatakan saham ini akan aktif dan punya likuiditas — syarat *minimal* untuk intraday, bukan sinyal arah.

### Mengapa Liquiditas Penting untuk Intraday?

Bayangkan kamu beli 10 lot ABCD tapi ternyata salah arah dan ingin jual. Kalau bid-nya tipis (sedikit pembeli), kamu bisa terjebak di harga yang jauh lebih rendah dari yang kamu inginkan. Saham dengan IEV tinggi punya banyak pembeli dan penjual aktif — kamu bisa masuk dan keluar mendekati harga yang kamu inginkan.

---

## 4. Cara Kerja Pre-Open Screener

Tool ini mengerjakan hal berikut secara otomatis:

```
1. Ambil daftar saham dengan IEV tertinggi dari Stockbit (pre-open)
2. Ambil top 5 (default) berdasarkan IEV
3. Untuk setiap saham:
   a. Hitung ATR(14) — ukuran volatilitas harian normal
   b. Hitung RSI(14) — apakah saham sudah overbought?
   c. Ambil harga penutupan kemarin (prev_close)
   d. Hitung entry range: prev_close ± 3%
   e. Hitung stop-loss berdasarkan ATR
   f. Kalau tersedia: cek gap% dari pre-open bid vs prev_close
4. Tampilkan hasil + prev High/Low sebagai referensi S/R
```

**Mengapa menggunakan prev_close sebagai acuan, bukan bid pre-open?**

Karena pre-open bid berubah terus selama 08:45–09:00 dan tidak mencerminkan clearing price. Prev_close adalah harga terakhir yang disepakati pasar — ini titik referensi yang stabil dan objektif.

---

## 5. Memahami Setiap Indikator

### 5.1 ATR — Average True Range

**Apa itu:** ATR mengukur seberapa jauh rata-rata harga bergerak per hari, dengan mempertimbangkan gap antar sesi. Dihitung dari 14 hari terakhir.

**Rumusnya (versi sederhana):**
```
True Range = max(High-Low, |High-PrevClose|, |Low-PrevClose|)
ATR(14)    = rata-rata bergerak dari 14 True Range terakhir
```

**Contoh konkret:**
```
BBCA close kemarin: 9,000
BBCA ATR(14): 150

Artinya: dalam 14 hari terakhir, BBCA rata-rata bergerak 150 poin per hari
(naik 150 atau turun 150 dari high ke low, secara rata-rata)
```

**Bagaimana tool ini menggunakannya:**
```
Stop-loss = entry_price - (1.0 × ATR)
         = 9,050 - (1.0 × 150)
         = 8,900

Kalau ATR menghasilkan stop yang terlalu jauh (> 7% dari entry),
tool ini otomatis memotong di batas 7%.
```

**Mengapa ATR lebih baik dari stop tetap 20%?**

Setiap saham punya "karakter" volatilitas berbeda:
- BBCA: ATR ~150 poin → intraday wajar bergerak 100-200 poin
- GOTO: ATR ~8 poin → intraday wajar bergerak 5-15 poin

Stop 20% untuk BBCA = 1,800 poin — jauh sekali, tidak masuk akal untuk intraday. Stop berbasis ATR menyesuaikan dengan karakter masing-masing saham.

**Apa yang perlu diwaspadai:**
- ATR dihitung dari data HARIAN, bukan menit. Ini masih kasar untuk intraday — tapi jauh lebih baik dari stop tetap
- Saat saham baru habis corporate action (stock split, rights issue), ATR lama tidak relevan
- Kalau ATR sangat kecil (< 0.5% dari harga), saham mungkin sedang konsolidasi ketat — bisa breakout besar

---

### 5.2 RSI — Relative Strength Index

**Apa itu:** RSI mengukur kecepatan dan besarnya perubahan harga dalam 14 hari terakhir. Nilainya antara 0–100.

**Cara membaca RSI:**
```
RSI > 75   : OVERBOUGHT — saham sudah naik terlalu cepat, risiko koreksi tinggi
RSI 65–75  : Panas, tapi belum ekstrem — waspada
RSI 30–65  : Zona ideal untuk long intraday (ada ruang naik)
RSI 25–30  : OVERSOLD — saham turun terlalu cepat, potensi rebound
RSI < 25   : Sangat oversold — tapi bisa terus turun (jangan catch the knife)
```

**Mengapa tool ini menggunakan RSI > 75 sebagai gate BEARISH:**

Kalau kamu masuk long di saham dengan RSI 85, artinya saham ini sudah naik signifikan 14 hari terakhir. Peluang saham bisa naik lagi hari ini masih ada, tapi odds-nya tidak menguntungkan — terlalu banyak profit-taker yang menunggu.

**Peringatan penting:**
- RSI dihitung dari data HARIAN 14 hari — ini memberikan konteks tren, bukan sinyal masuk intraday
- RSI 40 bukan berarti "pasti naik hari ini" — hanya berarti ruang naik lebih terbuka dibanding RSI 80
- Saham dengan RSI sangat rendah (< 25) bisa dalam downtrend kuat — jangan masuk hanya karena "murah"

**Contoh penggunaan:**
```
BBRI RSI: 52 → Zona ideal, lanjut evaluasi
TLKM RSI: 79 → Overbought, tool tandai BEARISH, lewati

BBCA RSI: 38, IEV tinggi → Menarik: likuid + ada ruang naik
```

---

### 5.3 Gap% — Kesenjangan Harga Pre-Open

**Apa itu:** Gap% mengukur seberapa jauh harga pre-open (dari order book Stockbit) menyimpang dari harga penutupan kemarin.

**Rumus:**
```
Gap% = (harga_pre_open_bid - prev_close) / prev_close × 100
```

**Cara membaca:**
```
Gap% = +0.5%  : Buka sedikit di atas kemarin — normal, aman
Gap% = +2.0%  : Buka 2% di atas — mulai waspada, sudah "lebih mahal" dari kemarin
Gap% = +4.5%  : GAP UP BESAR — terlalu mahal di open, risiko langsung koreksi
Gap% = -3.0%  : GAP DOWN — sentimen negatif, hindari long kecuali ada katalis kuat
```

**Mengapa tool ini menggunakan batas ±3%:**

Secara historis, saham yang gap lebih dari 3% saat open cenderung mengalami "gap fill" — harga kembali ke arah kemarin setelah euforia/panik opening mereda. Kalau kamu masuk long saat gap +5%, kamu beli di harga yang sudah +5% lebih mahal dari orang yang masuk kemarin. Ini mengurangi upside dan memperbesar risiko.

**Catatan:**
- Gap% dalam tool ini hanya tersedia kalau order book diambil (bukan --fast mode)
- Di fast mode, gap% ditampilkan sebagai "—"

---

### 5.4 Entry Range — Rentang Harga Masuk yang Aman

**Apa itu:** Range harga di mana kamu sebaiknya masuk, berdasarkan harga kemarin ± toleransi gap.

**Rumus:**
```
Entry Range Low  = prev_close × (1 - 0.03) = prev_close × 0.97
Entry Range High = prev_close × (1 + 0.03) = prev_close × 1.03
```

**Cara menggunakannya:**

Tunggu sampai pasar buka (09:00). Lihat di mana opening price-nya. Kemudian:

```
Kalau opening price DALAM range → pertimbangkan masuk
Kalau opening price LUAR range  → lewati, tunggu hari lain
```

**Contoh:**
```
BBCA prev_close: 9,000
Entry Range: 8,730 – 9,270

Skenario 1: Opening price 9,100 → DALAM range → evaluasi masuk
Skenario 2: Opening price 9,400 → LUAR range (gap +4.4%) → LEWATI
Skenario 3: Opening price 8,600 → LUAR range (gap -4.4%) → LEWATI
```

**Mengapa tidak selalu masuk meski di luar range?**

Kalau opening terlalu tinggi: kamu beli di titik yang sudah banyak orang profit. Penjual lebih banyak dari pembeli. Probabilitas turun lebih besar.

Kalau opening terlalu rendah: ada sesuatu yang buruk terjadi (berita negatif, aksi jual institusi). Jangan melawan arus besar.

---

### 5.5 Suggested Entry — Harga Limit Order yang Disarankan

**Apa itu:** Harga limit order yang disarankan untuk dipasang setelah opening price diketahui.

**Rumus:**
```
Suggested Entry = prev_close × 1.005
```

Ini adalah titik awal — 0.5% di atas harga penutupan kemarin. Bukan angka sakral. Kamu bisa adjust berdasarkan di mana opening price terjadi.

**Cara menggunakannya:**
1. Tunggu opening price (09:00–09:05)
2. Kalau opening dalam entry range, pasang limit order di harga Suggested Entry atau sedikit di bawah opening price
3. Kalau terisi, pasang stop-loss di ATR Stop

---

### 5.6 ATR Stop — Harga Stop-Loss

**Apa itu:** Harga di mana kamu harus keluar jika harga bergerak berlawanan dengan posisimu.

**Rumus:**
```
ATR Stop = entry_price - (1.0 × ATR14)
         Tapi tidak boleh lebih dari 7% di bawah entry
```

**Cara menggunakannya:**

Segera setelah order beli terisi, pasang stop-loss di harga ini. Jangan ubah stop ke bawah karena "sayang". Stop ada untuk melindungi modal kamu dari kerugian besar.

**Contoh:**
```
BBCA entry: 9,050
ATR(14): 150
ATR Stop: 9,050 - 150 = 8,900
Stop%: -1.66%

Artinya: kalau BBCA turun ke 8,900, kamu keluar dengan rugi 1.66%
Ini jauh lebih baik daripada menahan turun 10–20%
```

---

### 5.7 Prev High / Prev Low — Level Support/Resistance Kemarin

**Apa itu:** Harga tertinggi (High) dan terendah (Low) dari hari kemarin.

**Mengapa penting untuk intraday:**

Trader lain juga memperhatikan level ini. High kemarin sering menjadi resistance (hambatan naik) dan Low kemarin sering menjadi support (lantai harga).

**Cara menggunakannya:**
```
Kalau kamu masuk long di 9,050 dan Prev High kemarin 9,200:
→ Target pertama: 9,200 (resistance kemarin)
→ Kalau tembus 9,200, target berikutnya: 9,200 + ATR = 9,350

Kalau Prev Low kemarin 8,900 dan kamu masuk di 9,050:
→ Stop tambahan: kalau break di bawah 8,900, ada masalah serius
```

**Output di terminal:**
```
BBCA     Prev H:9,200  L:8,900  (yesterday's intraday S/R levels)
```

---

## 6. Workflow Harian Step-by-Step

### Malam Sebelumnya (opsional, 10 menit)

Update data supaya pagi tidak perlu waktu lama:

```bash
saham update --universe lq45 --days 30
```

Ini mengambil data harga + data broker flow untuk 45 saham LQ45. Kalau data sudah fresh (< 5 hari), otomatis di-skip.

---

### Pagi Hari (08:30–08:45) — Persiapan

**Step 1: Buka Stockbit di browser**

Login ke Stockbit. Navigasi ke Screener → Movers.

**Step 2: Ambil data IEV movers**

Cari saham dengan IEV tertinggi. Catat ticker dan nilai IEV-nya dalam format JSON:

```json
[
  {"ticker": "BBCA", "iev": 450000},
  {"ticker": "BMRI", "iev": 320000},
  {"ticker": "BBRI", "iev": 280000},
  {"ticker": "TLKM", "iev": 195000},
  {"ticker": "ASII", "iev": 167000}
]
```

**Step 3 (opsional, untuk mode normal): Ambil data order book**

Untuk setiap ticker, buka halaman order book Stockbit dan catat best bid:

```json
{
  "BBCA": {"price": 9025, "volume": 25000},
  "BMRI": {"price": 5875, "volume": 18000}
}
```

---

### Pagi Hari (08:45–08:55) — Jalankan Screener

**Mode Cepat (fast, ~15 detik, tidak perlu order book):**

```bash
saham screen pre-open \
  --movers-json '[{"ticker":"BBCA","iev":450000},{"ticker":"BMRI","iev":320000}]' \
  --fast
```

**Mode Normal (dengan order book, ~45–90 detik):**

```bash
saham screen pre-open \
  --movers-json '[{"ticker":"BBCA","iev":450000},{"ticker":"BMRI","iev":320000}]' \
  --order-books-json '{"BBCA":{"price":9025,"volume":25000},"BMRI":{"price":5875,"volume":18000}}'
```

---

### Jam 09:00 — Pasar Buka, Ambil Keputusan

Ini momen paling kritis. Dalam 5 menit pertama setelah pasar buka:

1. **Lihat opening price** untuk setiap kandidat dari screener
2. **Bandingkan dengan entry range** dari output screener
3. **Putuskan: masuk atau lewati**

> Jangan terburu-buru. Lebih baik lewati 5 peluang daripada masuk di harga yang salah.

---

### Setelah Trading — Catat di Journal

```bash
saham screen log
```

Perintah ini membaca hasil screener terakhir dan menyimpannya ke `journals/pre-open.csv`. Data aktual (opening price, close 1 hari kemudian, close 5 hari kemudian) akan diisi otomatis dari database lokal saat kamu jalankan `review`.

---

### Setelah 20 Sesi — Evaluasi

```bash
saham screen review --horizon 5
```

Output contoh:

```
=======================================================
PAPER TRADE JOURNAL REVIEW
=======================================================
Total logged entries :  87
Entries with DB data :  72
Entry range hit rate : 74.3%
  (% of sessions where opening price fell within entry range)
Direction accuracy 1d: 58.2%
Direction accuracy 5d: 61.4%

Per-trend breakdown:
  TREND      TOTAL  IN_RANGE  UP_1D
  -------  -------  --------  -----
  BULLISH       45        35     26
  BEARISH       18        12      7
  NEUTRAL        9         6      4
=======================================================
```

**Cara membaca hasil:**
- **Hit rate 74%**: 74% dari saham yang masuk kandidat, opening price-nya memang dalam range ±3% dari kemarin → entry range model kita cukup akurat
- **Direction accuracy 58%**: dari kandidat BULLISH, 58% naik hari itu → sedikit lebih baik dari coin flip, perlu ditingkatkan
- Kalau hit rate < 50%: pertimbangkan perlebar range atau naikkan IEV threshold
- Kalau direction accuracy < 52%: sinyal BULLISH/BEARISH kita tidak lebih baik dari random → perlu ditinjau ulang

---

## 7. Membaca Output Screener

Contoh output lengkap:

```
==========================================================================================
PRE-OPEN SCREENER RESULTS
==========================================================================================
Date: 2026-06-12   IEV filter: >= 100,000
Movers evaluated: 12   Candidates: 5

TICKER      IEV   GAP%        ENTRY-RANGE    SUGGEST   ATR-STOP   STOP%    RSI  TREND
BBCA    450000  +0.6%  8,720 – 9,270       9,050    8,900     -1.7%     52  BULLISH
  Prev H:9,200  L:8,750  (yesterday's intraday S/R levels)
BMRI    320000  +0.3%  5,693 – 6,057       5,887    5,712     -3.0%     44  BULLISH
  Prev H:6,050  L:5,750  (yesterday's intraday S/R levels)
TLKM    195000    —    3,087 – 3,273       3,177    3,050     -4.0%     38  BULLISH
  Prev H:3,300  L:3,100  (yesterday's intraday S/R levels)
BBRI    167000  +1.2%  5,105 – 5,427       5,259    5,050     -4.0%     61  NEUTRAL
  Prev H:5,400  L:5,200  (yesterday's intraday S/R levels)
GOTO     155000  +4.2%    228 – 242           235      221     -6.0%     73  BEARISH
  Prev H:248  L:232  (yesterday's intraday S/R levels)
```

**Penjelasan kolom per kolom:**

| Kolom | Penjelasan |
|-------|-----------|
| `TICKER` | Kode saham IDX |
| `IEV` | Volume expected di opening. Makin tinggi = makin likuid |
| `GAP%` | Selisih pre-open bid vs kemarin. `—` = fast mode, tidak ada data order book |
| `ENTRY-RANGE` | Rentang harga aman untuk masuk. Cek opening price masuk sini atau tidak |
| `SUGGEST` | Harga limit order yang disarankan (prev_close + 0.5%) |
| `ATR-STOP` | Harga stop-loss. Pasang ini segera setelah order beli terisi |
| `STOP%` | Seberapa jauh stop dari entry. Di sini -1.7% sampai -6% |
| `RSI` | 0–100. Di atas 75 = overbought (hindari long) |
| `TREND` | BULLISH/BEARISH/NEUTRAL berdasarkan RSI + gap% |
| `Prev H/L` | High dan Low kemarin. Gunakan sebagai target (H) dan level warning (L) |

**Analisis contoh di atas:**

- **BBCA**: IEV tertinggi, gap kecil (+0.6%), RSI ideal (52), BULLISH → kandidat terkuat. Entry range 8,720–9,270, stop di 8,900
- **BMRI**: Juga bagus. Gap kecil, RSI oke. Perhatikan Prev H di 6,050 — kalau opening di 5,990, resistance tinggal 60 poin
- **TLKM**: Fast mode (GAP% = —), tapi RSI 38 menarik — ada ruang naik, dan RSI hampir oversold
- **BBRI**: RSI 61 mendekati batas 65, trend NEUTRAL. Bisa masuk tapi dengan ekspektasi lebih konservatif
- **GOTO**: **SKIP**. Gap +4.2% sudah keluar batas (>3%), RSI 73 hampir overbought, trend BEARISH. Risiko masuk di harga tinggi lalu langsung koreksi

---

## 8. Kapan Harus Masuk, Kapan Harus Lewati

### Checklist Sebelum Masuk (semua harus terpenuhi)

```
□ Opening price ada di dalam ENTRY-RANGE
□ TREND bukan BEARISH
□ RSI < 75
□ Gap% < 3% (atau N/A karena fast mode — masih bisa masuk, tapi lebih waspada)
□ Kamu tahu di mana stop-loss kamu (ATR-STOP)
□ Modal untuk 1 trade tidak lebih dari 10% total modal kamu
```

### Langsung Lewati Kalau:

- **Opening price di atas ENTRY-RANGE HIGH**: saham buka terlalu tinggi, sudah ada gap-up. Terlambat masuk di sini
- **Opening price di bawah ENTRY-RANGE LOW**: ada sesuatu yang negatif, gap-down besar. Tunggu konfirmasi arah
- **TREND = BEARISH**: RSI terlalu tinggi atau gap terlalu besar
- **Tidak ada data historis di database**: jalankan `saham fetch TICKER` dulu
- **Kamu belum pasang stop-loss**: jangan masuk tanpa tahu kapan kamu keluar rugi

### Situasi Khusus yang Perlu Diwaspadai

**Berita setelah tutup pasar kemarin:**

Earnings release, aksi korporasi, berita macro — semua bisa menyebabkan gap besar yang tidak bisa diprediksi oleh tool ini. Kalau ada berita besar untuk suatu saham, pertimbangkan skip meskipun indikator bagus.

**Hari Senin dan setelah libur panjang:**

Gap lebih sering terjadi karena ada akumulasi berita selama weekend/libur. Pertimbangkan perlebar tolerance atau skip lebih banyak di hari-hari ini.

**30 menit pertama (09:00–09:30):**

Volume sangat tinggi, spread bisa lebar, harga bergerak cepat. Ini bukan waktu yang baik untuk pemula. Lebih aman tunggu 09:30–10:00 ketika harga sudah lebih stabil dan arah lebih jelas.

---

## 9. Manajemen Risiko

### Aturan Dasar yang Tidak Boleh Dilanggar

**1. Maksimal loss per trade: 2% dari total modal**

```
Total modal: Rp 10,000,000
Maksimal loss per trade: Rp 200,000

Kalau stop-loss di -2% dan modal per trade Rp 3,000,000:
Maksimal loss = 3,000,000 × 2% = Rp 60,000 ← aman

Kalau kamu terlalu besar posisi:
Modal per trade Rp 8,000,000, stop -2%:
Maksimal loss = 8,000,000 × 2% = Rp 160,000 ← mendekati batas
```

**2. Jangan trading lebih dari 3 saham sekaligus**

Lebih banyak posisi = lebih sulit dipantau. Fokus pada 1–2 kandidat terkuat dari screener.

**3. Stop-loss tidak boleh digeser ke bawah**

Kalau kamu pasang stop di 8,900 dan saham turun ke 8,920, sangat menggoda untuk turunkan stop ke 8,850. Jangan. Stop ada karena kamu sudah menentukan di titik mana tesis kamu terbukti salah.

**4. Ambil profit secara bertahap**

Jangan tunggu target penuh lalu turun lagi. Pertimbangkan jual 50% di target pertama (Prev High), sisanya di target kedua.

### Position Sizing

Tool ini menampilkan `SUGGEST` (harga entry) dan `ATR-STOP`. Dari sini, hitung berapa lot yang bisa kamu beli:

```
Modal per trade    : Rp 3,000,000
Entry price (BBCA) : 9,050
ATR Stop           : 8,900
Risk per saham     : 9,050 - 8,900 = 150 poin

Maksimal loss yang kamu toleransi: 2% × total modal = Rp 200,000

Jumlah saham yang bisa dibeli:
  200,000 / 150 = 1,333 saham = 13 lot (1 lot = 100 saham)

Cek: 13 lot × 100 × 9,050 = Rp 11,765,000
Kalau total modal Rp 10 juta, ini terlalu besar.
Pakai 10 lot saja: 10 × 100 × 9,050 = Rp 9,050,000
```

---

## 10. Paper Trade Journal

### Mengapa Paper Trade Dulu?

Tool ini memberikan kandidat, entry range, dan stop-loss — tapi kita belum tahu apakah sinyalnya akurat untuk kondisi pasar IDX hari ini. Setelah 20–30 sesi trading, kamu punya data nyata.

**Paper trade = tracking hasil tanpa uang sungguhan.** Kamu "berpura-pura" masuk di harga suggested, lalu lihat apa yang terjadi.

### Alur Paper Trade

```bash
# Setelah menjalankan screener dan mencatat "keputusan" kamu:
saham screen log

# Lihat hasilnya setelah beberapa hari:
saham screen review --horizon 1   # evaluasi 1 hari kemudian
saham screen review --horizon 5   # evaluasi 5 hari kemudian
```

### Apa yang Perlu Dievaluasi

Dari `saham screen review`, perhatikan:

1. **Hit rate entry range > 70%?** Kalau tidak, artinya model ±3% terlalu sempit untuk kondisi pasar saat ini. Coba `--max-gap 0.05` (5%)

2. **Direction accuracy BULLISH > 55%?** Kalau tidak, sinyal BULLISH kita tidak bermakna. Perlu ditambahkan filter

3. **Ada pola di BEARISH yang benar?** Kalau BEARISH direction accuracy < 50% (artinya saham yang ditandai BEARISH malah naik), mungkin gate RSI terlalu sensitif

4. **Apakah ada saham yang selalu gagal?** Mungkin ada karakteristik saham tertentu yang tidak cocok dengan model ini

---

## 11. Kesalahan Umum Pemula

### Kesalahan 1: FOMO — Masuk Karena Takut Ketinggalan

Screener menampilkan 5 kandidat. Kamu lihat BBCA sudah naik 2% dari opening. Kamu pikir "aduh, sudah naik, cepat masuk sebelum lebih tinggi."

**Jangan.** Kalau harga sudah keluar dari entry range, peluangnya sudah berubah. Hari ini ada kandidat, besok ada kandidat lain. Disiplin lebih penting dari tidak ingin rugi.

### Kesalahan 2: Tidak Pasang Stop-Loss

"Nanti kalau turun saya cut manual." Tapi saat harga turun, otak membujuk: "Sebentar lagi balik naik." Dan terus turun.

Stop-loss bukan kekalahan. Ini adalah biaya operasional dari trading.

### Kesalahan 3: Terlalu Banyak Saham Sekaligus

3 posisi terbuka saat pasar buka jam 09:00 → kamu tidak bisa memantau semuanya dengan baik. Fokus pada 1–2 kandidat terkuat.

### Kesalahan 4: Trading Saham yang Tidak Ada di Database

Kalau `saham screen pre-open` menampilkan "No cached data — run saham fetch TICKER first", artinya tidak ada data historis untuk menghitung ATR dan RSI. Jangan masuk tanpa data ini — kamu tidak punya referensi volatilitas.

### Kesalahan 5: Mengabaikan Konteks Makro

Tool ini tidak membaca berita. Kalau BI baru naikkan suku bunga, atau ada krisis global — sinyal teknikal dari screener ini kurang relevan. Selalu cek berita besar sebelum trading.

### Kesalahan 6: Averaging Down Posisi Rugi

Kamu beli BBCA di 9,050, stop di 8,900. Harga turun ke 8,950. Kamu beli lagi karena "lebih murah." Ini melanggar aturan stop-loss. Keluar di 8,900, bukan tambah posisi.

---

## 12. Glosarium

| Istilah | Penjelasan |
|---------|-----------|
| **ATR** | Average True Range. Ukuran volatilitas harian rata-rata dalam 14 hari terakhir |
| **Call Auction** | Sistem matching IDX di mana semua order dikumpulkan dulu, baru dieksekusi sekaligus di satu harga (08:45–09:00 dan 15:50–16:00) |
| **Clearing Price** | Harga yang ditemukan call auction untuk memaksimalkan volume yang bisa dieksekusi |
| **Entry Range** | Rentang harga aman untuk masuk, berdasarkan prev_close ± max_gap_pct |
| **Fast Mode** | Mode screener tanpa mengambil data order book. Lebih cepat tapi tidak ada Gap% |
| **Gap%** | Selisih persentase antara harga pre-open dan harga penutupan kemarin |
| **IEV** | Intraday Expected Volume. Estimasi volume yang akan ditransaksikan saat opening |
| **Lot** | Satuan pembelian saham di IDX. 1 lot = 100 saham |
| **Overbought** | RSI > 75. Saham sudah naik terlalu cepat, risiko koreksi meningkat |
| **Oversold** | RSI < 25. Saham sudah turun terlalu cepat, potensi rebound |
| **Prev Close** | Harga penutupan hari kemarin. Referensi utama untuk entry range |
| **Prev High/Low** | Harga tertinggi/terendah hari kemarin. Digunakan sebagai level S/R intraday |
| **RSI** | Relative Strength Index. Ukuran momentum 0–100 |
| **S/R** | Support dan Resistance. Level harga di mana saham cenderung berhenti atau berbalik |
| **Stop-Loss** | Harga di mana kamu keluar dengan kerugian terbatas. Wajib dipasang setelah order beli terisi |
| **Suggested Entry** | Harga limit order yang disarankan, dihitung sebagai prev_close × 1.005 |
| **Swing Trade** | Trading yang ditahan beberapa hari hingga beberapa minggu (beda dengan intraday) |
| **Tick** | Unit pergerakan harga terkecil di IDX. Besarnya tergantung range harga saham |

### Tick Size IDX (Referensi)

| Harga Saham | Tick |
|-------------|------|
| < Rp 200 | Rp 1 |
| Rp 200 – < Rp 500 | Rp 2 |
| Rp 500 – < Rp 2.000 | Rp 5 |
| Rp 2.000 – < Rp 5.000 | Rp 10 |
| ≥ Rp 5.000 | Rp 25 |

---

## Penutup

Tool ini memberikan kamu struktur dan data — tapi keputusan tetap di tangan kamu. Tidak ada screener yang bisa menjamin profit. Yang bisa dilakukan adalah meningkatkan probabilitas dengan menggunakan data yang lebih baik, dan melindungi modal dengan stop-loss yang disiplin.

**Mulai dengan paper trade selama 20–30 sesi sebelum menggunakan uang sungguhan.** Data dari `saham screen review` akan memberi tahu kamu apakah setup ini bekerja untuk gaya trading kamu, sebelum kamu menemukan hal itu dengan cara yang mahal.

> "Preserve capital first. Profits will follow discipline."

---

*Dokumen ini menjelaskan cara menggunakan tool ai-saham untuk analisis pre-open. Ini bukan saran investasi atau trading. Seluruh keputusan trading adalah tanggung jawab pribadi kamu.*
