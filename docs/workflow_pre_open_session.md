# Workflow Pre-Opening Intraday Trading

**Operator runbook:** [runbook_pre_open.md](runbook_pre_open.md).
## Panduan Operasional Step-by-Step

> Dokumen ini adalah **playbook harian** — fokus pada apa yang kamu lakukan dan
> kapan, bukan teori. Untuk penjelasan indikator dan konsep, lihat
> [`pre_open_trading_design_notes.md`](pre_open_trading_design_notes.md).

---

## Daftar Isi

1. [Prasyarat](#1-prasyarat)
2. [Peta Waktu Pagi Hari](#2-peta-waktu-pagi-hari)
3. [Malam Sebelumnya — Refresh Data](#3-malam-sebelumnya--refresh-data)
4. [08:00 — Cek Status Sesi Stockbit](#4-0800--cek-status-sesi-stockbit)
5. [08:45 — Jalankan Collect-IEV](#5-0845--jalankan-fetch iev)
6. [08:47 — Jalankan Pre-Open Screener](#6-0847--jalankan-pre-open-screener)
7. [08:52 — Baca dan Evaluasi Output](#7-0852--baca-dan-evaluasi-output)
8. [08:55 — Siapkan Watchlist dan Order Plan](#8-0855--siapkan-watchlist-dan-order-plan)
9. [09:00 — Pasar Buka, Konfirmasi Entry](#9-0900--pasar-buka-konfirmasi-entry)
10. [09:00–09:05 — Eksekusi](#10-090009-05--eksekusi)
11. [Setelah Sesi — Catat dan Evaluasi](#11-setelah-sesi--catat-dan-evaluasi)
12. [Quick Reference Card](#12-quick-reference-card)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. Prasyarat

### Setup Satu Kali (tidak perlu diulang tiap hari)

```bash
# Login Stockbit — simpan sesi browser di .stockbit_profile/
saham fetch stockbit login
```

```bash
# Optional: intercept Stockbit API calls for debugging endpoint changes.
# Ini bukan prasyarat harian untuk pre-open screener.
saham fetch stockbit spy
```

Browser akan terbuka. Login seperti biasa (termasuk 2FA). Setelah berhasil, tutup browser — sesi sudah tersimpan.

### Data Saham di Database Lokal

Screener butuh data historis (ATR, RSI, broker flow) untuk menghasilkan sinyal. Tanpa data ini, saham akan muncul dengan warning `No cached data`.

```bash
# Satu kali untuk universe LQ45 (±5 menit pertama kali)
saham fetch market --universe lq45

# Tambah saham spesifik yang sering muncul di movers
saham fetch market BUMI BBRI BBCA BMRI TLKM GOTO ASII --days 365
```

### Config Screener (Optional)

Semua threshold screener ada di `config/pre_open_screener.yaml`:

| Section | Key | Default | Fungsi |
|---------|-----|---------|--------|
| `filters.exclude_suffix_pattern` | `-(W\|R\|L)$` | Skip warrant/rights/bond |
| `filters.min_history_days` | `20` | Skip IPO < 20 hari (ATR/RSI meaningless) |
| `screener.iev_min` | `100000` | Minimum IEV |
| `screener.top_n` | `5` | Proses top N movers |
| `entry.max_gap_pct` | `0.03` | Max gap dari prev close |
| `risk.tick_friction_gate` | `true` | Gate IDX tick-size (Kep-00196/BEI/12-2024) |
| `risk.min_target_ticks` | `3` | Target minimal 3 ticks |
| `risk.min_stop_ticks` | `2` | Stop minimal 2 ticks |
| `analysis.iev_intensity_enabled` | `true` | Flag unusual volume via IEV/ADV |
| `regime_gate.enabled` | `true` | Ketatkan entry di WEAK/RISK_OFF |

File lengkap: `config/pre_open_screener.yaml` — semua bisa diubah tanpa kode.

### Cek Kesehatan Data

```bash
saham fetch status
```

Menampilkan tanggal data terbaru untuk setiap provider (IDX, Yahoo, Stockbit),
jumlah baris di tiap tabel database, dan peringatan data kadaluarsa.

---

## 2. Peta Waktu Pagi Hari

```
WAKTU        AKTIVITAS                                  TOOL
─────────────────────────────────────────────────────────────────────
Malam        Refresh data / gap-fill lokal                saham fetch market
08:00        Cek sesi Stockbit masih valid                saham fetch stockbit status
08:45        ★ CAPTURE IEV SNAPSHOT ★                    saham fetch iev
08:47        ★ JALANKAN PRE-OPEN SCREENER ★              saham screen pre-open
08:52        Baca output, pilih kandidat
08:55        Siapkan watchlist + mental order plan
08:56        Capture locked-input IEV baseline             saham fetch iev
08:57        Capture keputusan kanonis                     saham research pre-open capture
08:58–09:00  Pre-opening matching — bukan window keputusan produksi
09:00        Pasar buka — track sample                     saham research pre-open track
09:00+       ★ POST-OPEN ASSESS ★                          saham assess pre-open
09:05+       Eksekusi order (di Stockbit/broker kamu)
Siang        Catat outcome kalau ada posisi               saham trade pre-open outcome
Sore         Log sesi ke journal                          saham trade pre-open log
```

**Tiga momen paling kritis:** multi-tick IEV, 08:57 capture, dan post-open `assess pre-open` setelah track.

---

## 3. Malam Sebelumnya — Refresh Data

> Opsional, tapi sangat direkomendasikan. Tanpa data fresh, sinyal ACCUM dan FVWAP tidak akurat.

```bash
saham fetch market --universe lq45
```

Perintah ini mengunduh data harga + broker flow untuk semua saham LQ45. Kalau cache belum mencapai tanggal hari ini, `saham fetch market` akan mencoba mengisi gap ke provider. Output `cached-current` berarti cache sudah sampai hari ini, `+Nd` berarti ada baris baru, dan `provider-no-new-data(latest=YYYY-MM-DD)` berarti provider sudah dicek tetapi belum punya data trading lebih baru.

Kalau ada saham non-LQ45 yang sering muncul di movers (misalnya BUMI, BREN, GOTO), tambahkan manual:

```bash
saham fetch market BUMI BREN GOTO --days 365
```

---

## 4. 08:00 — Cek Status Sesi Stockbit

```bash
saham fetch stockbit status
```

Output yang diharapkan (token masih valid secara lokal):
```
  Browser login   : 20.1h ago (informational only)
  Token state     : valid
  Token expires   : 2026-07-11T09:26:39+00:00  (source: jwt_exp)
```

Output kalau token lokal sudah kedaluwarsa:
```
  Browser login   : 42.4h ago (informational only)
  Token state     : expired
  Token expires   : 2026-07-10T09:26:39+00:00  (source: jwt_exp)
```

Umur profil browser tidak memblokir request. Pada request API berikutnya, tool
akan mencoba satu kali mengambil JWT RS256 baru dari profil tersebut. Jalankan
login manual hanya jika refresh itu gagal atau server tetap menjawab HTTP 401.

Untuk inspeksi manual sesi (browser interaktif):
```bash
saham fetch stockbit browse
```
Membuka browser headed dengan sesi yang sudah login — berguna untuk debugging
endpoint atau melihat data mentah langsung di Stockbit.

`browse` dapat menyimpan JWT RS256 yang lebih baru jika token tersebut terlihat
pada request Exodus normal. Berhasil membuka halaman saja bukan bukti bahwa API
sudah menerima autentikasi.

---

## 5. 08:45 — Jalankan Collect-IEV

> Ini langkah baru! Sebelum pre-open screener, capture IEV snapshot dulu untuk membangun dataset historis dan melihat ΔIEV.

```bash
saham fetch iev
```

Output:
```
Fetching IEV snapshot (top 50 movers)...
Saved 32 movers for 2026-06-17 to data.db (IEP captured: 28/32)
  Captured at 08:45:30 WIB  [PRE-NCP]

  RANK  TICKER          IEV       IEP
  ----  --------  ----------  --------
     1  BUMI         972,420      157
     2  BNBR         428,497      109
     3  BBRI         373,423    2,850
     4  BBCA         297,068    5,875
     5  CUAN         281,822      715
   ...  (up to 20 displayed, all stored in db)

  Movers with IEP >= 50: 28/32

IEV/IEP history: 47 days (2026-04-01 → 2026-06-17), avg 28 movers/day, IEP fill 86%
```

**Kapan pakai:**
- Setiap hari trading, jalankan antara 08:45–08:50 WIB
- Data disimpan ke `iev_snapshot_history` dengan timestamp dan flag NCP
- Snapshot 08:56–08:57:59 berlabel `[NCP LOCKED INPUT]`
- Snapshot mulai 08:58 adalah matching-period diagnostic, bukan baseline sinyal

**Manfaat jangka panjang:**
- Setelah 3+ bulan, `# retired: retired trade backtest-intraday` bisa filter by IEV rank (match live behavior)
- ΔIEV harian di output bersifat diagnostic; sinyal memakai IEV final 08:57
  dikurangi baseline locked-input 08:56

---

## 6. 08:47 — Jalankan Pre-Open Screener

Pilih satu cara berdasarkan situasi:

---

### Cara A — Autonomous, Satu Perintah (Paling Praktis)

```bash
saham screen pre-open --top 5
```

Tool otomatis:
1. Cek umur sesi — kalau > 8 jam, langsung error dan minta re-login (tidak buang waktu buka browser)
2. Buka browser dengan sesi tersimpan
3. Fetch IEV movers dari Exodus API (semua board: main + special monitoring)
4. Tampilkan semua movers yang masuk sebelum filter top-N
5. Fetch orderbook untuk top 5 ticker (termasuk offer side untuk spread%)
6. Filter: speculative symbols (-W, -R, -L) + min 20 days history
7. Filter optional: `--iep-min 50` (drop penny stocks — lihat IEP dari fetch iev)
8. Jalankan screener dan tampilkan hasil

Durasi: ~20–30 detik.

---

### Cara B — Dengan Market Regime Context

```bash
saham screen pre-open --top 5
```

Baris `REGIME` memakai logic yang sama dengan `saham inspect regime`: benchmark 20d, breadth di atas SMA20, dan foreign-flow breadth.

Di regime `WEAK` atau `RISK_OFF`, entry band dipersempit 50% (`gap_pct_tightening_factor: 0.5` di config) dan hanya kandidat `BACKED` yang lanjut ke WATCHLIST. Ini melindungi dari BBCA/BBRI/BMRI/BBNI anchor effect — saat IHSG turun tajam, bid second-liner menguap.

---

### Cara C — Dengan Strategy Signal Column

```bash
saham screen pre-open --top 5 --signal-strategy williams-r-bounce
```

Menambahkan kolom `STRAT` di output — signal real-time dari salah satu dari 15 strategi yang sudah di-backtest:
- `↑` = LOW_RISK (entry signal, hijau)
- `~` = MODERATE (hold, redup)
- `↓` = HIGH_RISK (exit signal, merah)

Tidak mengubah verdict PRIME/WATCH/SKIP — hanya tambahan konteks.

---

### Cara D — Lihat Raw Data Dulu, Baru Screener

Berguna kalau mau verifikasi data IEV + orderbook sebelum diproses:

```bash
# Langkah 1 — lihat top 10 IEV beserta best bid/offer
saham fetch stockbit fetch-top5 --top 10
```

Contoh output:
```
  #    TICKER            IEV     BEST BID     LOTS   BEST OFFER     LOTS
  -----------------------------------------------------------------------
  1    BUMI          972,420          157   409,437          158   303,382
  2    BNBR          428,497          109    32,009          110   102,408
  3    BBRI          373,423        2,850   219,024        2,860     2,772
  4    BBCA          297,068        5,875    33,568        5,900       502
```

```bash
# Langkah 2 — jalankan screener dengan data top 5
saham screen pre-open \
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

### Cara E — Fast Mode (Tanpa Orderbook, ~15 Detik)

Kalau sesi Stockbit bermasalah atau mau cepat tanpa data orderbook:

```bash
saham screen pre-open \
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
| `--iep-min N` | tidak aktif | Filter penny stock (lihat IEP output fetch iev) |
| `--max-gap 0.05` | dari config | Hari berita: naikkan ke 5% |
| `--atr-mult 1.5` | 1.0 | Mau stop lebih longgar |
| `--signal-strategy NAME` | tidak aktif | Tambah kolom sinyal dari strategi (contoh: `williams-r-bounce`, `macd-cross`) |
| `--fast` | off | Tidak ada data orderbook |
| `--allow-non-trading-day` | off | Dry-run/backfill di weekend atau hari non-bursa |
| `--config PATH` | `config/pre_open_screener.yaml` | Pakai policy screener lain |
| (regime + risk) | **always-on** | Konteks market regime + default-gate risk (non-blocking); opt-out: `--no-regime` / `--no-risk` |
| `--regime-universe NAME` | `idx80` | Universe untuk breadth regime |
| `--benchmark TICKER` | `^JKSE` | Benchmark regime, biasanya IHSG |

Secara default, `saham screen pre-open` menolak run di weekend agar journal tidak terisi sesi palsu. Kalau kamu memang sedang latihan atau backfill, pakai `--allow-non-trading-day`; output akan tetap menampilkan warning dan tanggal data.

Konfigurasi default ada di `config/pre_open_screener.yaml`. File ini adalah policy screener, bukan strategy package untuk `saham strategy backtest --strategy`.

---

## 7. 08:52 — Baca dan Evaluasi Output

### Contoh Output Lengkap

Output dimulai dengan ringkasan semua movers yang difetch:

```
Playwright session found — running autonomously...

Fetched 16 movers from Stockbit (top 5 screened):
  BUMI 972K  |  BNBR 428K  |  BBRI 373K  |  BBCA 297K  |  CUAN 282K  |  BMRI 260K  |  TLKM 246K  |  DSSA 246K  |  ASPR 202K  |  TPIA 167K
  DEWA 150K  |  PPRO 146K  |  BIPI 140K  |  BRMS 126K  |  ELTY 122K  |  KLBF 113K

==========================================================================================
PRE-OPEN SCREENER RESULTS
==========================================================================================
Date: 2026-06-17   IEV filter: >= 100,000
Movers evaluated: 16   Candidates: 5

VERDICT    TICKER      IEV    GAP%   SPRD%     ENTRY-RANGE   STOP%   RSI  SIGNAL
------------------------------------------------------------------------------------------
★ PRIME   BNBR    428,497   -0.9%    0.9%         104–116   -7.2%    43  BACKED×3d  +8.8% floor  PH:114
◉ WATCH   BUMI    972,420   -0.6%    0.6%         149–165   -7.0%    42  UNCONFIR×2d  +0.8% floor  PH:162
✗ SKIP    BBRI    373,423   -1.0%    0.4%     2,768–2,992   -3.9%    44  DISTRIBU  +2.3% floor  PH:2,910
✗ SKIP    BBCA    297,068  +15.1%    0.4%     4,892–5,408   -5.7%    17  DISTRIBU  -11.1% sell  PH:5,150
✗ SKIP    CUAN    281,822   -0.7%    0.8%         684–756   -7.0%    46  DISTRIBU  -9.8% sell  PH:735
------------------------------------------------------------------------------------------

  ! BBCA: Gap +15.0% exceeds ±5.0% ATR band
  ! BUMI: UNUSUAL_VOLUME (IEV intensity 8.3x)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 WATCHLIST  ★ BNBR  ◉ BUMI
 SKIP       BBRI  BBCA  CUAN

 At 09:00, fill opening prices and run:
   saham assess pre-open \
     --opening-json '{"BNBR":___,"BUMI":___}'
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
==========================================================================================
```

**Apa yang baru:**
- **SPRD%** — bid/offer spread (semakin kecil semakin likuid)
- **UNUSUAL_VOLUME** — IEV > 5x ADV_20d / 78 (minat tidak biasa, informasional bukan gating)
- **IEP filter** — kalau pakai `--iep-min`, movers di bawah threshold tidak muncul
- WARNING speculative symbol atau < 20 days history (tidak jadi candidate)

---

### Cara Baca Output — Lihat VERDICT, Bukan Setiap Kolom

VERDICT sudah mensintesis semua sinyal. Cukup baca kolom pertama:

| VERDICT | Artinya | Aksi |
|---------|---------|------|
| `★ PRIME` | BULLISH + BACKED + FVWAP floor + range valid | Masuk WATCHLIST prioritas |
| `◉ WATCH` | BULLISH tapi belum semua sinyal hijau | Masuk WATCHLIST, konfirmasi di 09:00 |
| `✗ SKIP` | BEARISH atau DISTRIBUTING atau gap di luar range | Tidak masuk, tidak dipikirkan lagi |
| `? NO_DATA` | Tidak ada data ATR lokal | Skip hari ini, `saham fetch market TICKER --days 365` malam ini |

Kolom lain berguna untuk context, bukan untuk keputusan utama:
- **GAP%** dan **ENTRY-RANGE** → dikonfirmasi oleh assess pre-open setelah track (09:00+)
- **SPRD%** → likuiditas (0.5–1.5% normal, > 3% tidak likuid)
- **STOP%** → posisi sizing, baca saat buat order plan
- **SIGNAL** → ringkasan ACCUM + FVWAP + Prev High + IEV_INTENSITY dalam satu string

---

### Tabel Evaluasi Cepat

| VERDICT | Penilaian | Aksi |
|---------|-----------|------|
| `★ PRIME` | Semua sinyal selaras | Watchlist prioritas, sizing penuh |
| `◉ WATCH` | Bullish tapi perlu konfirmasi | Watchlist, sizing lebih kecil |
| `✗ SKIP` | Distributing/Bearish/Regime-gate | Tidak masuk |
| `? NO_DATA` | Tidak ada data historis | `saham fetch market TICKER --days 365` malam ini |

---

## 8. 08:55 — Siapkan Watchlist dan Order Plan

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
  → assess pre-open akan output ENTER
  → Pasang limit buy di harga yang ditampilkan assess pre-open
  → Set stop segera setelah terisi
  → Target awal: Prev H 114

Skenario kalau open DI ATAS 116:
  → assess pre-open akan output SKIP (gap up)

Skenario kalau open DI BAWAH 104:
  → assess pre-open akan output SKIP (gap down)
────────────────────────────────────────
```

> **Catatan:** Kamu tidak perlu hitung SUGGEST atau ATR-STOP manual lagi —
> assess pre-open menampilkan "Limit BUY X | Stop Y" setelah kamu input opening price.

> **Locked input 08:56–08:57:59; matching 08:58–08:59:59:** Order lama
> dibatasi untuk amend/withdraw setelah 08:56, sementara order baru masih dapat
> masuk. Sinyal kanonis harus selesai sebelum matching pukul 08:58.

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

## 9. 09:00 — Pasar Buka, Konfirmasi Entry

Tepat saat pasar buka (09:00 WIB), tool otomatis mengambil opening price aktual dari Stockbit untuk setiap kandidat. Tidak perlu input manual lagi.

```bash
# Auto-resolve — baca opening price dari Stockbit running trade + order book
saham assess pre-open
```

Kalau mau override harga tertentu (misalnya karena delay data):
```bash
# Manual override untuk ticker tertentu, sisanya auto-resolve
saham assess pre-open \
  --opening-json '{"BUMI": 158}'
```

### Regime-Gate dan Tick-Friction Gate

Confirm-open sekarang punya dua gate baru yang jalan otomatis:

1. **Regime gate** (aktif di WEAK/RISK_OFF):
   - Entry band dipersempit 50%
   - Hanya kandidat BACKED yang lanjut ke ENTER
   - Informasi "regime WEAK: entry band tightened to X–Y" ditampilkan

2. **Tick-friction gate** (Kep-00196/BEI/12-2024):
   - Hitung implied 1:1 target = opening + (opening - stop)
   - Hitung ticks antara stop→entry dan entry→target
   - Kalau stop < 2 ticks atau target < 3 ticks → SKIP_LOW_VOLATILITY
   - Biaya round-trip IDX: 0.41% (Stockbit) — 0.65% (IPOT) incl. 0.10% PPh

Keduanya bisa dimatikan di `config/pre_open_screener.yaml`:
```yaml
risk:
  tick_friction_gate: false   # matikan tick-friction gate
regime_gate:
  regime_gate_enabled: false  # matikan regime gate
```

---

### Contoh Output Opening Confirmation

Output dikelompokkan per aksi:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 2026-06-17  INTRADAY CONFIRMATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 ▶ ENTER  (act now)
   BNBR    open 110  in range 104–116
   → Limit BUY 110  |  Stop 103 (-6.4%)  |  Target: Prev H 114
   BUMI    open 158  in range 149–165
   → Limit BUY 158  |  Stop 147 (-7.0%)  |  Target: Prev H 162

 ✗ SKIP  (do not enter)
   BBCA    pre-open trend is BEARISH
   CUAN    broker context is DISTRIBUTING
   BBRI    regime WEAK: BACKED accumulation required (got DISTRIBUTING)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 saham trade pre-open log   (record this session)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Harga limit buy dan stop sudah dihitung otomatis.** Kamu hanya perlu:
1. Buka aplikasi broker
2. Pasang limit buy di harga yang tertera
3. Set stop segera setelah terisi

### Keputusan dan Aksi

| Group | Artinya | Yang Kamu Lakukan |
|-------|---------|------------------|
| `▶ ENTER` | Semua gate pass | Pasang limit buy di harga ENTER, set stop segera setelah terisi |
| `◎ WAIT` | Opening dalam range tapi trend NEUTRAL | Pantau 15 menit. Masuk hanya kalau harga holds above range_low dengan volume. |
| `✗ SKIP` | Berbagai alasan | Tidak masuk — alasan ditampilkan per ticker |
| `SKIP_LOW_VOLATILITY` | Tick-friction gate: stop/target terlalu sempit | Tidak masuk — risiko tidak sebanding biaya transaksi |

**Aturan keras:**
- Kalau output `✗ SKIP` → tidak ada pengecualian
- Kalau `◎ WAIT` dan tidak ada konfirmasi dalam 15 menit → skip
- Jangan masuk setelah 09:30 untuk strategi pre-open ini

---

## 10. 09:00–09:05 — Eksekusi

Untuk saham dengan keputusan `ENTER`:

```
1. Buka aplikasi broker kamu (Stockbit Sekuritas / RTI / lainnya)
2. Pasang limit buy di harga ENTRY (dari output assess pre-open)
3. Begitu order terisi → LANGSUNG pasang stop-loss di harga STOP
4. Set target awal di Prev High
```

**Jangan tunda pasang stop.** Setiap menit tanpa stop adalah risiko unlimited.

> **Istirahat 11:30–13:30:** Posisi yang kamu masuk di 09:00–09:05 akan memasuki
> jeda 2 jam saat bursa tutup untuk istirahat. Stop-loss yang kamu pasang tidak
> bisa melindungi dari gap saat sesi 2 dibuka (13:30). Pertimbangkan: (1) gunakan
> stop yang lebih lebar, (2) ukuran posisi lebih kecil, atau (3) tutup posisi
> sebelum istirahat kalau profit sudah cukup.

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

## 11. Setelah Sesi — Catat dan Evaluasi

### Log Sesi ke Journal

```bash
# Log paper notebook (setelah analyze, pakai ID immutable)
saham trade pre-open log
```

Perintah ini mencatat hasil assess yang diikat observation_id + opening_snapshot_id ke `journals/pre_open_paper.csv`.

### Catat Outcome Aktual

Setelah posisi ditutup (profit atau loss):

```bash
saham trade pre-open outcome BBRI \
  --entry 2900 \
  --exit 2955 \
  --notes "keluar jam 09:45, tembus Prev H 2910, trailing sampai 2955"
```

```bash
saham trade pre-open outcome BBRI \
  --entry 2900 \
  --exit 2788 \
  --notes "stop kena jam 09:12, gap down lanjut"
```

### Evaluasi Berkala (setiap 20–30 sesi)

```bash
# Akurasi prediksi pre-open
saham research pre-open evaluate

# Akurasi keputusan (win rate per decision type)
saham trade pre-open review
```

`saham trade pre-open review` menganalisis paper journal post-open assess. Review memakai manual outcome jika sudah dicatat dengan `saham trade pre-open outcome`; jika belum ada, tool memakai daily OHLC lokal sebagai proxy, bukan urutan tick intraday.

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

### Backtest (setelah 3+ bulan data IEV)

Kalau sudah mengumpulkan data IEV harian via `saham fetch iev`:

```bash
# Walk-forward backtest — filter top 5 oleh IEV rank
# retired: retired trade backtest-intraday --iev-top-n 5 --days 90
```

Menggunakan data IEV asli dari Stockbit + candle OHLC lokal. Entry/exit pakai open/high/low/close, semua posisi keluar di hari yang sama. Tanpa data IEV, backtest jalan dengan universe penuh (warning ditampilkan).

---

## 12. Quick Reference Card

Potong dan tempel di terminal kamu.

```
┌──────────────────────────────────────────────────────────────┐
│  PRE-OPEN INTRADAY — QUICK REFERENCE                         │
├──────────────────────────────────────────────────────────────┤
│  SETUP (sekali)                                              │
│    saham fetch stockbit login                                 │
│    saham fetch market --universe lq45                         │
├──────────────────────────────────────────────────────────────┤
│  08:00  Cek sesi (> 8 jam → possibly expired → login dulu)   │
│    saham fetch stockbit status                                │
│    saham fetch stockbit login   ← kalau expired               │
├──────────────────────────────────────────────────────────────┤
│  08:45  Capture IEV snapshot (build history dataset)         │
│    saham fetch iev                          │
├──────────────────────────────────────────────────────────────┤
│  08:47  Pre-open screener                                    │
│    saham screen pre-open --top 5          ← default  │
│    saham screen pre-open                   ← regime+risk always-on │
│    saham screen pre-open --signal-strategy NAME      │
│    saham screen pre-open --iep-min 50     ← anti penny│
├──────────────────────────────────────────────────────────────┤
│  08:52  Baca VERDICT (kolom pertama)                         │
│    ★ PRIME   → watchlist prioritas                           │
│    ◉ WATCH   → watchlist, konfirmasi di 09:00                │
│    ✗ SKIP    → tidak masuk, tidak dipikirkan lagi            │
│    ? NO_DATA → saham fetch market TICKER --days 365 malam ini │
├──────────────────────────────────────────────────────────────┤
│  09:00  Isi opening prices dari WATCHLIST template           │
│    saham assess pre-open \                       │
│      --opening-json '{"BNBR":___,"BUMI":___}'  │
├──────────────────────────────────────────────────────────────┤
│  09:00–09:05  Eksekusi dari output assess pre-open              │
│    ▶ ENTER → limit buy & stop sudah tertera, pasang langsung │
│    ◎ WAIT  → pantau 15 menit, entry kalau holds above range  │
│    ✗ SKIP  → tidak masuk, tanpa pengecualian                 │
├──────────────────────────────────────────────────────────────┤
│  Setelah sesi                                                │
│    saham trade pre-open log                                  │
│    saham trade pre-open outcome TICKER --entry X --exit Y    │
│    # retired: retired trade backtest-intraday (setelah 3+ bulan data)     │
└──────────────────────────────────────────────────────────────┘
```

---

## 13. Troubleshooting

### Pre-Open Ditolak Karena Weekend / Non-Trading Day

```
Pre-open guard: 2026-06-13 is a weekend in Asia/Jakarta.
Use --allow-non-trading-day only for dry-runs/backfills.
```

Untuk workflow live: jangan lanjut, tunggu hari bursa berikutnya.

Untuk latihan/backfill:

```bash
saham screen pre-open --movers-json '...' --fast --allow-non-trading-day
```

Output akan menampilkan baris `DATA`:

```
DATA: Analysis date 2026-06-13   Candles through 2026-06-12   Broker flow through 2026-06-12
```

Kalau `Candles through` atau `Broker flow through` tertinggal dari `Analysis date`, anggap hasil sebagai dry-run, bukan sinyal live.

### Sesi Stockbit Expired

`saham fetch stockbit status` sekarang mendeteksi sesi > 8 jam otomatis:

```
  Status : possibly expired — re-run login

Run: saham fetch stockbit login
```

Kalau langsung jalankan `pre-open` dengan sesi yang sudah tua, tool langsung fail **sebelum** membuka browser (tidak perlu tunggu 15–20 detik):

```
Screener failed: Stockbit session is 13.4h old — likely expired.
Run: saham fetch stockbit login
```

```bash
saham fetch stockbit login   # login ulang, ~2 menit + warm-up otomatis
```

Setelah login, tool otomatis warm-up token (navigasi headless ke orderbook page). `saham screen pre-open` langsung bisa dijalankan — tidak perlu `saham fetch stockbit spy` dulu.

### Pembatasan Order Setelah 08:56

Ini bukan error tool — ini aturan BEI. Non-Cancellation Period (NCP) berlaku sejak Desember 2025:

1. 08:56–08:57:59: order terbuka tidak dapat amend/withdraw; order baru masih dapat masuk
2. 08:58–08:59:59: pre-opening matching; bukan window keputusan sinyal produksi
3. 09:00: sesi reguler dimulai

**Cara menghindari masalah:**
- Selesaikan review output pre-open sebelum 08:55
- Submit order sebelum 08:56 kalau sudah yakin
- Gunakan limit order, bukan market order

### Saham Muncul dengan "No cached data" atau SKIP_SPECULATIVE

```
! BUMI: No cached data — run 'saham fetch market BUMI --days 365' first
```

Untuk hari ini: skip saham itu, gunakan kandidat lain yang punya data. Untuk hari berikutnya:

```bash
saham fetch market BUMI --days 365
```

**SKIP_SPECULATIVE** — saham ditolak karena:
- Suffix `-W` (warrant), `-R` (rights/HMETD), atau `-L` (bond) — jangan trading instrumen ini dengan strategi pre-open
- History < 20 hari (IPO baru) — ATR dan RSI meaningless, sering ARA/ARB 35%

### Pre-Open Screener Tidak Ada Kandidat yang Muncul

Kemungkinan:
1. `--iev-min` terlalu tinggi untuk kondisi pasar hari ini — coba `--iev-min 50000`
2. Semua movers tidak punya data lokal — jalankan `saham fetch market --universe lq45`
3. Semua movers kena speculative filter (warrant/rights/IPO baru)
4. Pasar sedang sepi (libur mendekati, sentimen negatif)

### Semua Kandidat SKIP

Normal terjadi di hari dengan kondisi berikut:
- Semua saham gap terlalu besar (setelah berita kuat semalam)
- Semua ACCUM DISTRIBUTING (distribusi masif asing)
- Tidak ada sinyal BULLISH yang jelas
- Regime WEAK/RISK_OFF dan tidak ada kandidat BACKED

Keputusan terbaik: **tidak trading hari itu**. Preserving capital adalah strategi valid.

### Opening Confirmation Lambat (> 2 menit)

Jangan tunggu tool kalau pasar sudah buka dan harga bergerak cepat. Di 09:00, opening window hanya beberapa menit. Kalau tool lambat:

1. Evaluasi manual berdasarkan output pre-open yang sudah ada
2. Cek apakah opening price masuk entry range
3. Ikuti aturan sederhana: dalam range + BULLISH = masuk, di luar range = skip

### Collect-IEV Tidak Jalan atau Tidak Ada Data

```bash
saham fetch iev --no-headless   # lihat browser untuk debug
```

Kalau output "No movers returned":
- Sesi Stockbit expired → `saham fetch stockbit login`
- Di luar jam pre-open (IEV hanya available 08:45–09:00)

Tanpa data IEV: `# retired: retired trade backtest-intraday` tetap bisa jalan dengan universe penuh, tapi ada warning.

---

## Catatan Penting

- Workflow ini dirancang untuk **pre-open session (08:45–09:00)** dan **opening window (09:00–09:05)**
- Jangan eksekusi berdasarkan pre-open output setelah 09:30 — konteks sudah berubah
- Tool memberikan analisis deterministik, bukan jaminan profit
- Paper trade minimal 20 sesi sebelum menggunakan uang sungguhan
- Gunakan `saham trade pre-open review` secara berkala untuk validasi apakah sinyal-sinyal ini bekerja di kondisi pasar saat ini
- Kumpulkan data IEV tiap hari via `saham fetch iev` — setelah 3+ bulan, backtest jadi lebih akurat

---

*Untuk penjelasan lengkap setiap indikator dan sinyal, lihat
[`pre_open_trading_design_notes.md`](pre_open_trading_design_notes.md).*
