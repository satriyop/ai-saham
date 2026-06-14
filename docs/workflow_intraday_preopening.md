# Workflow Pre-Opening Intraday Trading
## Panduan Operasional Step-by-Step

> Dokumen ini adalah **playbook harian** — fokus pada apa yang kamu lakukan dan kapan, bukan teori. Untuk penjelasan indikator dan konsep, lihat [`how_to_intraday_trading.md`](how_to_intraday_trading.md).

---

## Daftar Isi

1. [Prasyarat](#1-prasyarat)
2. [Peta Waktu Pagi Hari](#2-peta-waktu-pagi-hari)
3. [Malam Sebelumnya — Refresh Data](#3-malam-sebelumnya--refresh-data)
4. [08:00 — Cek Status Sesi Stockbit](#4-0800--cek-status-sesi-stockbit)
5. [08:45 — Jalankan Pre-Open Screener](#5-0845--jalankan-pre-open-screener)
6. [08:50 — Baca dan Evaluasi Output](#6-0850--baca-dan-evaluasi-output)
7. [08:55 — Siapkan Watchlist dan Order Plan](#7-0855--siapkan-watchlist-dan-order-plan)
8. [09:00 — Pasar Buka, Konfirmasi Entry](#8-0900--pasar-buka-konfirmasi-entry)
9. [09:00–09:05 — Eksekusi](#9-090009-05--eksekusi)
10. [Setelah Sesi — Catat dan Evaluasi](#10-setelah-sesi--catat-dan-evaluasi)
11. [Quick Reference Card](#11-quick-reference-card)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Prasyarat

### Setup Satu Kali (tidak perlu diulang tiap hari)

```bash
# Login Stockbit — simpan sesi browser di .stockbit_profile/
saham stockbit login
```

```bash
# Optional: intercept Stockbit API calls for debugging endpoint changes.
# Ini bukan prasyarat harian untuk pre-open screener.
saham stockbit spy
```

Browser akan terbuka. Login seperti biasa (termasuk 2FA). Setelah berhasil, tutup browser — sesi sudah tersimpan.

### Data Saham di Database Lokal

Screener butuh data historis (ATR, RSI, broker flow) untuk menghasilkan sinyal. Tanpa data ini, saham akan muncul dengan warning `No cached data`.

```bash
# Satu kali untuk universe LQ45 (±5 menit pertama kali)
saham update --universe lq45

# Tambah saham spesifik yang sering muncul di movers
saham update BUMI BBRI BBCA BMRI TLKM GOTO ASII --days 365
```

---

## 2. Peta Waktu Pagi Hari

```
WAKTU        AKTIVITAS                                  TOOL
─────────────────────────────────────────────────────────────────────
Malam        Refresh data / gap-fill lokal                saham update
08:00        Cek sesi Stockbit masih valid                saham stockbit status
08:45        ★ JALANKAN PRE-OPEN SCREENER ★              saham intraday pre-open
08:50        Baca output, pilih kandidat
08:55        Siapkan watchlist + mental order plan
09:00        Pasar buka — lihat opening price aktual
09:00–09:05  ★ KONFIRMASI ENTRY ★                        saham intraday confirm-open
09:05+       Eksekusi order (di Stockbit/broker kamu)
Siang        Catat outcome kalau ada posisi               saham intraday outcome
Sore         Log sesi ke journal                          saham intraday log
```

**Dua momen paling kritis:** 08:45 (pre-open screener) dan 09:00–09:05 (confirm-open).

---

## 3. Malam Sebelumnya — Refresh Data

> Opsional, tapi sangat direkomendasikan. Tanpa data fresh, sinyal ACCUM dan FVWAP tidak akurat.

```bash
saham update --universe lq45
```

Perintah ini mengunduh data harga + broker flow untuk semua saham LQ45. Kalau cache belum mencapai tanggal hari ini, `saham update` akan mencoba mengisi gap ke provider. Output `cached-current` berarti cache sudah sampai hari ini, `+Nd` berarti ada baris baru, dan `provider-no-new-data(latest=YYYY-MM-DD)` berarti provider sudah dicek tetapi belum punya data trading lebih baru.

Kalau ada saham non-LQ45 yang sering muncul di movers (misalnya BUMI, BREN, GOTO), tambahkan manual:

```bash
saham update BUMI BREN GOTO --days 365
```

---

## 4. 08:00 — Cek Status Sesi Stockbit

```bash
saham stockbit status
```

Output yang diharapkan (sesi masih fresh):
```
Stockbit Session Status
========================================
  Type   : persistent browser profile (recommended)
  Profile: .stockbit_profile
  Saved  : 2.1h ago
  Status : likely valid
```

Output kalau sesi sudah expired (> 8 jam):
```
Stockbit Session Status
========================================
  Type   : persistent browser profile (recommended)
  Profile: .stockbit_profile
  Saved  : 13.4h ago
  Status : possibly expired — re-run login

Run: saham stockbit login
```

**Kalau status `possibly expired`:** jalankan `saham stockbit login` sekarang. Tool akan otomatis warm-up token setelah login — tidak perlu langkah ekstra.

---

## 5. 08:45 — Jalankan Pre-Open Screener

Pilih satu cara berdasarkan situasi:

---

### Cara A — Autonomous, Satu Perintah (Paling Praktis)

```bash
saham intraday pre-open --top 5
```

Tool otomatis:
1. Cek umur sesi — kalau > 8 jam, langsung error dan minta re-login (tidak buang waktu buka browser)
2. Buka browser dengan sesi tersimpan
3. Fetch IEV movers dari Exodus API (semua board: main + special monitoring)
4. Tampilkan semua movers yang masuk sebelum filter top-N
5. Fetch orderbook untuk top 5 ticker
6. Jalankan screener dan tampilkan hasil

Durasi: ~20–30 detik.

---

### Cara B — Lihat Raw Data Dulu, Baru Screener

Berguna kalau mau verifikasi data IEV + orderbook sebelum diproses:

```bash
# Langkah 1 — lihat top 10 IEV beserta best bid/offer
saham stockbit fetch-top5 --top 10
```

Contoh output:
```
  #    TICKER            IEV     BEST BID     LOTS   BEST OFFER     LOTS
  -----------------------------------------------------------------------
  1    BUMI          972,420          157   409,437          158   303,382
  2    BNBR          428,497          109    32,009          110   102,408
  3    BBRI          373,423        2,850   219,024        2,860     2,772
  4    BBCA          297,068        5,875    33,568        5,900       502
  5    CUAN          281,822          715     2,923          720    21,487
  6    BMRI          260,407        4,260    45,100        4,270     8,330
  7    TLKM          246,162        2,570    78,200        2,580     5,100
  8    DSSA          245,512       48,000     1,200       48,100       850
  9    ASPR          201,720          610    90,100          612    45,200
 10    TPIA          166,584        8,500    12,400        8,525     6,800
```

```bash
# Langkah 2 — jalankan screener dengan data top 5
saham intraday pre-open \
  --movers-json '[
    {"ticker":"BUMI","iev":972420},
    {"ticker":"BNBR","iev":428497},
    {"ticker":"BBRI","iev":373423},
    {"ticker":"BBCA","iev":297068},
    {"ticker":"CUAN","iev":281822}
  ]' \
  --order-books-json '{
    "BUMI":{"price":157,"volume":409437},
    "BNBR":{"price":109,"volume":32009},
    "BBRI":{"price":2850,"volume":219024},
    "BBCA":{"price":5875,"volume":33568},
    "CUAN":{"price":715,"volume":2923}
  }'
```

---

### Cara C — Fast Mode (Tanpa Orderbook, ~15 Detik)

Kalau sesi Stockbit bermasalah atau mau cepat tanpa data orderbook:

```bash
saham intraday pre-open \
  --movers-json '[{"ticker":"BBCA","iev":450000},{"ticker":"BMRI","iev":320000}]' \
  --fast
```

Data IEV diambil manual dari Stockbit web: Movers overlay → tab **IEP/IEV** → catat Symbol dan IEV.

---

### Parameter Penting

| Parameter | Default | Kapan Diubah |
|-----------|---------|-------------|
| `--top N` | dari config | Mau fokus lebih sedikit kandidat |
| `--iev-min N` | 100,000 | Hari sepi: turunkan ke 50,000 |
| `--max-gap 0.05` | dari config | Hari berita: naikkan ke 5% |
| `--atr-mult 1.5` | 1.0 | Mau stop lebih longgar |
| `--fast` | off | Tidak ada data orderbook |
| `--allow-non-trading-day` | off | Dry-run/backfill di weekend atau hari non-bursa |
| `--config PATH` | `config/pre_open_screener.yaml` | Pakai policy screener lain |
| `--with-regime` | off | Tampilkan konteks market regime deterministik |
| `--regime-universe NAME` | `idx80` | Universe untuk breadth regime |
| `--benchmark TICKER` | `^JKSE` | Benchmark regime, biasanya IHSG |

Secara default, `saham intraday pre-open` menolak run di weekend agar journal tidak
terisi sesi palsu. Kalau kamu memang sedang latihan atau backfill, pakai
`--allow-non-trading-day`; output akan tetap menampilkan warning dan tanggal data.

Konfigurasi default ada di `config/pre_open_screener.yaml`. File ini adalah policy
screener, bukan strategy package untuk `saham backtest --strategy`.

Untuk hari scalping long, tambahkan market regime agar output memberi konteks risiko
pasar luas:

```bash
saham intraday pre-open --top 5 --with-regime
```

Baris `REGIME` memakai logic yang sama dengan `saham regime`: benchmark 20d,
breadth di atas SMA20, dan foreign-flow breadth. Regime tidak mengubah verdict
`PRIME` / `WATCH` / `SKIP` secara diam-diam; kalau regime `WEAK` atau `RISK_OFF`,
output menambahkan warning agar entry confirmation lebih ketat atau size dikurangi.

---

## 6. 08:50 — Baca dan Evaluasi Output

### Contoh Output Lengkap

Output sekarang dimulai dengan ringkasan semua movers yang difetch — berguna untuk melihat
saham di luar top 5 yang mungkin menarik keesokan harinya (misalnya untuk `saham update`).

```
Playwright session found — running autonomously...

Fetched 16 movers from Stockbit (top 5 screened):
  BUMI 972K  |  BNBR 428K  |  BBRI 373K  |  BBCA 297K  |  CUAN 282K  |  BMRI 260K  |  TLKM 246K  |  DSSA 246K  |  ASPR 202K  |  TPIA 167K
  DEWA 150K  |  PPRO 146K  |  BIPI 140K  |  BRMS 126K  |  ELTY 122K  |  KLBF 113K

==========================================================================================
PRE-OPEN SCREENER RESULTS
==========================================================================================
Date: 2026-06-13   IEV filter: >= 100,000
Movers evaluated: 16   Candidates: 5

VERDICT    TICKER      IEV    GAP%       ENTRY-RANGE   STOP%   RSI  SIGNAL
------------------------------------------------------------------------------------------
★ PRIME   BNBR    428,497   -0.9%           104–116   -7.2%    43  BACKED×3d  +8.8% floor  PH:114
◉ WATCH   BUMI    972,420   -0.6%           149–165   -7.0%    42  UNCONFIR×2d  +0.8% floor  PH:162
✗ SKIP    BBRI    373,423   -1.0%       2,768–2,992   -3.9%    44  DISTRIBU  +2.3% floor  PH:2,910
✗ SKIP    BBCA    297,068  +15.1%       4,892–5,408   -5.7%    17  DISTRIBU  -11.1% sell  PH:5,150
✗ SKIP    CUAN    281,822   -0.7%           684–756   -7.0%    46  DISTRIBU  -9.8% sell  PH:735
------------------------------------------------------------------------------------------

WARNINGS
  ! BBCA: Gap +15.0% exceeds ±5.0% ATR band

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 WATCHLIST  ★ BNBR  ◉ BUMI
 SKIP       BBRI  BBCA  CUAN

 At 09:00, fill opening prices and run:
   saham intraday confirm-open \
     --opening-json '{"BNBR":___,"BUMI":___}'
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
==========================================================================================
```

Output dimulai dengan baris `Fetched 16 movers` — universe penuh dari Stockbit.
Saham di luar top 5 (PPRO, ELTY, dll.) adalah kandidat untuk `saham update` malam ini.

**VERDICT** sudah mensintesis semua sinyal — kamu tidak perlu membaca setiap kolom secara manual.

---

### Cara Baca Output — Lihat VERDICT, Bukan Setiap Kolom

VERDICT sudah mensintesis semua sinyal. Cukup baca kolom pertama:

| VERDICT | Artinya | Aksi |
|---------|---------|------|
| `★ PRIME` | BULLISH + BACKED + FVWAP floor + range valid | Masuk WATCHLIST prioritas |
| `◉ WATCH` | BULLISH tapi belum semua sinyal hijau | Masuk WATCHLIST, konfirmasi di 09:00 |
| `✗ SKIP` | BEARISH atau DISTRIBUTING atau gap di luar range | Tidak masuk, tidak dipikirkan lagi |
| `? NO_DATA` | Tidak ada data ATR lokal | Skip hari ini, `saham update TICKER --days 365` malam ini |

Kolom lain berguna untuk context, bukan untuk keputusan utama:
- **GAP%** dan **ENTRY-RANGE** → dikonfirmasi oleh confirm-open di 09:00
- **STOP%** → posisi sizing, baca saat buat order plan
- **SIGNAL** → ringkasan ACCUM + FVWAP + Prev High dalam satu string

---

### Tabel Evaluasi Cepat

| VERDICT | Penilaian | Aksi |
|---------|-----------|------|
| `★ PRIME` | Semua sinyal selaras | Watchlist prioritas, sizing penuh |
| `◉ WATCH` | Bullish tapi perlu konfirmasi | Watchlist, sizing lebih kecil |
| `✗ SKIP` | Distributing/Bearish | Tidak masuk |
| `? NO_DATA` | Tidak ada data historis | `saham update TICKER --days 365` malam ini |

---

### Contoh Evaluasi Output di Atas

```
★ PRIME  BNBR  → Masuk WATCHLIST — semua sinyal hijau (BACKED, floor, BULLISH)
◉ WATCH  BUMI  → Masuk WATCHLIST — bullish tapi ACCUM belum kuat (UNCONFIRMED)
✗ SKIP   BBRI  → Skip — DISTRIBUTING (asing net-jual)
✗ SKIP   BBCA  → Skip — BEARISH + gap jauh di atas range
✗ SKIP   CUAN  → Skip — DISTRIBUTING + FVWAP sell risk
```

**Hasil:** BNBR dan BUMI masuk watchlist. Confirm-open command sudah otomatis di-generate di bawah tabel — isi harga pembukaan saat 09:00.

---

## 7. 08:55 — Siapkan Watchlist dan Order Plan

Sebelum pasar buka, siapkan mental order plan untuk setiap kandidat di watchlist.

### Template Per Saham

Ambil data dari output screener — kolom ENTRY-RANGE dan STOP%:

```
TICKER: BNBR  (★ PRIME)
────────────────────────────────────────
Entry Range : 104 – 116          (dari ENTRY-RANGE)
Stop%       : -7.2%              (dari STOP%)
Prev H      : 114                (dari SIGNAL: PH:114)

Skenario kalau open DALAM range (104–116):
  → confirm-open akan output ENTER
  → Pasang limit buy di harga yang ditampilkan confirm-open
  → Set stop segera setelah terisi
  → Target awal: Prev H 114

Skenario kalau open DI ATAS 116:
  → confirm-open akan output SKIP (gap up)

Skenario kalau open DI BAWAH 104:
  → confirm-open akan output SKIP (gap down)
────────────────────────────────────────
```

> **Catatan:** Kamu tidak perlu hitung SUGGEST atau ATR-STOP manual lagi —
> confirm-open langsung menampilkan "Limit BUY X | Stop Y" setelah kamu input opening price.

### Hitung Position Size

Aturan dasar: maksimal loss per trade = 2% total modal.

```
Total modal    : Rp 10,000,000
Maks loss      : Rp 200,000

BBRI entry 2,900 | stop 2,788
Risk per saham = 2,900 - 2,788 = 112
Max lot        = 200,000 / (112 × 100) = 17.8 → ambil 17 lot
Nilai posisi   = 17 × 100 × 2,900 = Rp 4,930,000
```

Batas aman: tidak lebih dari 2 posisi simultaan.

---

## 8. 09:00 — Pasar Buka, Konfirmasi Entry

Tepat saat pasar buka (09:00 WIB), lihat opening price aktual di Stockbit untuk setiap kandidat di watchlist. Tunggu 1–2 menit agar harga stabil.

Masukkan opening prices ke tool:

```bash
saham intraday confirm-open \
  --opening-json '{"BBRI": 2870}'
```

---

### Contoh Output Confirm-Open

Output sekarang dikelompokkan per aksi — tidak perlu membaca tabel:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 2026-06-13  INTRADAY CONFIRMATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 ▶ ENTER  (act now)
   BNBR    open 110  in range 104–116
   → Limit BUY 110  |  Stop 103 (-6.4%)  |  Target: Prev H 114
   BUMI    open 158  in range 149–165
   → Limit BUY 158  |  Stop 147 (-7.0%)  |  Target: Prev H 162

 ✗ SKIP  (do not enter)
   BBRI    broker context is DISTRIBUTING
   BBCA    pre-open trend is BEARISH
   CUAN    broker context is DISTRIBUTING

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  saham intraday log   (record this session)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Harga limit buy dan stop sudah dihitung otomatis.** Kamu hanya perlu:
1. Buka aplikasi broker
2. Pasang limit buy di harga yang tertera
3. Set stop segera setelah terisi

---

### Keputusan dan Aksi

| Group | Artinya | Yang Kamu Lakukan |
|-------|---------|------------------|
| `▶ ENTER` | Semua gate pass | Pasang limit buy di harga ENTER, set stop segera setelah terisi |
| `◎ WAIT` | Opening dalam range tapi trend NEUTRAL | Pantau 15 menit. Masuk hanya kalau harga holds above range_low dengan volume. |
| `✗ SKIP` | Berbagai alasan (distributing, bearish, gap, stop terlalu wide) | Tidak masuk — alasan ditampilkan per ticker |

**Aturan keras:**
- Kalau output `✗ SKIP` → tidak ada pengecualian
- Kalau `◎ WAIT` dan tidak ada konfirmasi dalam 15 menit → skip
- Jangan masuk setelah 09:30 untuk strategi pre-open ini

---

## 9. 09:00–09:05 — Eksekusi

Untuk saham dengan keputusan `ENTER`:

```
1. Buka aplikasi broker kamu (Stockbit Sekuritas / RTI / lainnya)
2. Pasang limit buy di harga ENTRY (dari confirm-open output)
3. Begitu order terisi → LANGSUNG pasang stop-loss di harga STOP
4. Set target awal di Prev High
```

**Jangan tunda pasang stop.** Setiap menit tanpa stop adalah risiko unlimited.

### Manajemen Setelah Entry

```
Harga naik ke Prev High (2,910):
  → Jual 50% posisi (lock profit sebagian)
  → Geser stop ke breakeven (harga entry)
  → Sisanya biarkan jalan dengan trailing stop

Harga langsung turun ke stop (2,788):
  → Cut loss, keluar. Tidak ada averaging down.
  → Catat di journal.

Harga sidewalk 30+ menit:
  → Pertimbangkan keluar di harga entry (flat)
  → Modal terikat lebih baik dilepas
```

---

## 10. Setelah Sesi — Catat dan Evaluasi

### Log Sesi ke Journal

```bash
# Log hasil pre-open screening
saham intraday pre-open-log

# Log hasil confirm-open (termasuk semua keputusan)
saham intraday log
```

`saham intraday log` adalah alias dari `saham intraday confirm-log`. Keduanya
mencatat hasil `confirm-open` terakhir ke `journals/intraday-confirmations.csv`.

### Catat Outcome Aktual

Setelah posisi ditutup (profit atau loss):

```bash
saham intraday outcome BBRI \
  --entry 2900 \
  --exit 2955 \
  --notes "keluar jam 09:45, tembus Prev H 2910, trailing sampai 2955"
```

```bash
saham intraday outcome BBRI \
  --entry 2900 \
  --exit 2788 \
  --notes "stop kena jam 09:12, gap down lanjut"
```

### Evaluasi Berkala (setiap 20–30 sesi)

```bash
# Akurasi entry range (berapa % opening masuk range?)
saham intraday pre-open-review --horizon 5

# Akurasi keputusan (win rate per decision type)
saham intraday review
```

`saham intraday review` adalah alias dari `saham intraday confirm-review`. Review
confirmation memakai manual outcome jika sudah dicatat dengan `saham intraday outcome`;
jika belum ada, tool memakai daily OHLC lokal sebagai proxy, bukan urutan tick intraday.

Contoh output review yang berguna:
```
DECISION BREAKDOWN:
  ENTER  : 18 total, 12 win (66.7%)
  WAIT   :  8 total,  4 win (50.0%)
  SKIP_* : 11 total (tidak dieksekusi)

CONTEXT (untuk ENTER):
  BACKED + FVWAP floor : 10 entries, 8 win (80.0%)
  UNCONFIRMED          :  5 entries, 3 win (60.0%)
  DISTRIBUTING         :  3 entries, 1 win (33.3%)  ← seharusnya tidak masuk
```

---

## 11. Quick Reference Card

Potong dan tempel di terminal kamu.

```
┌─────────────────────────────────────────────────────────────┐
│  PRE-OPEN INTRADAY — QUICK REFERENCE                        │
├─────────────────────────────────────────────────────────────┤
│  SETUP (sekali)                                             │
│    saham stockbit login                                     │
│    saham update --universe lq45                             │
├─────────────────────────────────────────────────────────────┤
│  08:00  Cek sesi (> 8 jam → possibly expired → login dulu)  │
│    saham stockbit status                                    │
│    saham stockbit login   ← kalau expired, warm-up otomatis │
├─────────────────────────────────────────────────────────────┤
│  08:45  Pre-open screener                                   │
│    saham intraday pre-open --top 5          ← autonomous    │
│    saham stockbit fetch-top5                ← lihat data    │
│    saham intraday pre-open --fast           ← manual/cepat  │
├─────────────────────────────────────────────────────────────┤
│  08:50  Baca VERDICT (kolom pertama)                        │
│    ★ PRIME   → watchlist prioritas                          │
│    ◉ WATCH   → watchlist, konfirmasi di 09:00               │
│    ✗ SKIP    → tidak masuk, tidak dipikirkan lagi           │
│    ? NO_DATA → saham update TICKER --days 365 malam ini                 │
├─────────────────────────────────────────────────────────────┤
│  09:00  Isi opening prices dari WATCHLIST template          │
│    saham intraday confirm-open \                            │
│      --opening-json '{"BNBR":___,"BUMI":___}'              │
├─────────────────────────────────────────────────────────────┤
│  09:00–09:05  Eksekusi dari output confirm-open             │
│    ▶ ENTER → limit buy & stop sudah tertera, pasang langsung│
│    ◎ WAIT  → pantau 15 menit, entry kalau holds above range │
│    ✗ SKIP  → tidak masuk, tanpa pengecualian                │
├─────────────────────────────────────────────────────────────┤
│  Setelah sesi                                               │
│    saham intraday log                                       │
│    saham intraday outcome TICKER --entry X --exit Y         │
└─────────────────────────────────────────────────────────────┘
```

---

## 12. Troubleshooting

### Pre-Open Ditolak Karena Weekend / Non-Trading Day

```
Pre-open guard: 2026-06-13 is a weekend in Asia/Jakarta.
Use --allow-non-trading-day only for dry-runs/backfills.
```

Untuk workflow live: jangan lanjut, tunggu hari bursa berikutnya.

Untuk latihan/backfill:

```bash
saham intraday pre-open --movers-json '...' --fast --allow-non-trading-day
```

Output akan menampilkan baris `DATA`:

```
DATA: Analysis date 2026-06-13   Candles through 2026-06-12   Broker flow through 2026-06-12
```

Kalau `Candles through` atau `Broker flow through` tertinggal dari `Analysis date`,
anggap hasil sebagai dry-run, bukan sinyal live.

### Sesi Stockbit Expired

`saham stockbit status` sekarang mendeteksi sesi > 8 jam otomatis:
```
  Status : possibly expired — re-run login

Run: saham stockbit login
```

Dan kalau langsung jalankan `pre-open` dengan sesi yang sudah tua, tool langsung fail
**sebelum** membuka browser (tidak perlu tunggu 15–20 detik):
```
Screener failed: Stockbit session is 13.4h old — likely expired.
Run: saham stockbit login
```

```bash
saham stockbit login   # login ulang, ~2 menit + warm-up otomatis
```

Setelah login, tool otomatis warm-up token (navigasi headless ke orderbook page).
`saham intraday pre-open` langsung bisa dijalankan — tidak perlu `saham stockbit spy` dulu.

### Saham Muncul dengan "No cached data"

```
! BUMI: No cached data — run 'saham update BUMI --days 365' first
```

Untuk hari ini: skip saham itu, gunakan kandidat lain yang punya data.
Untuk hari berikutnya:

```bash
saham update BUMI --days 365
```

### Pre-Open Screener Tidak Ada Kandidat yang Muncul

Kemungkinan:
1. `--iev-min` terlalu tinggi untuk kondisi pasar hari ini — coba `--iev-min 50000`
2. Semua movers tidak punya data lokal — jalankan `saham update --universe lq45`
3. Pasar sedang sepi (libur mendekati, sentimen negatif)

### Semua Kandidat SKIP atau NEUTRAL

Normal terjadi di hari dengan kondisi berikut:
- Semua saham gap terlalu besar (setelah berita kuat semalam)
- Semua ACCUM DISTRIBUTING (distribusi masif asing)
- Tidak ada sinyal BULLISH yang jelas

Keputusan terbaik: **tidak trading hari itu**. Preserving capital adalah strategi valid.

### Confirm-Open Lambat (> 2 menit)

Jangan tunggu tool kalau pasar sudah buka dan harga bergerak cepat. Di 09:00, opening window hanya beberapa menit. Kalau tool lambat:

1. Evaluasi manual berdasarkan output pre-open yang sudah ada
2. Cek apakah opening price masuk entry range
3. Ikuti aturan sederhana: dalam range + BULLISH = masuk, di luar range = skip

---

## Catatan Penting

- Workflow ini dirancang untuk **pre-open session (08:45–09:00)** dan **opening window (09:00–09:05)**
- Jangan eksekusi berdasarkan pre-open output setelah 09:30 — konteks sudah berubah
- Tool memberikan analisis deterministik, bukan jaminan profit
- Paper trade minimal 20 sesi sebelum menggunakan uang sungguhan
- Gunakan `saham intraday review` secara berkala untuk validasi apakah sinyal-sinyal ini bekerja di kondisi pasar saat ini

---

*Untuk penjelasan lengkap setiap indikator dan sinyal, lihat [`how_to_intraday_trading.md`](how_to_intraday_trading.md).*
