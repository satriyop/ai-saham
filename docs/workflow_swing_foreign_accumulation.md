# Workflow Swing Trade — Foreign Accumulation
## Panduan Operasional Lengkap

> Playbook untuk strategi swing trading berbasis akumulasi asing. Fokus pada identifikasi saham yang sedang dikumpulkan institusi asing, entry saat momentum dimulai, dan exit sebelum distribusi.
>
> Untuk konsep dasar indikator, lihat [`how_to_intraday_trading.md`](how_to_intraday_trading.md).

---

## Daftar Isi

1. [Filosofi Strategi](#1-filosofi-strategi)
2. [Prasyarat](#2-prasyarat)
3. [Peta Waktu Workflow](#3-peta-waktu-workflow)
4. [Pahami Skor Akumulasi](#4-pahami-skor-akumulasi)
5. [Langkah 1 — Cek Regime Pasar](#5-langkah-1--cek-regime-pasar)
6. [Langkah 2 — Jalankan Screener Akumulasi](#6-langkah-2--jalankan-screener-akumulasi)
7. [Langkah 3 — Analisis Kandidat Terpilih](#7-langkah-3--analisis-kandidat-terpilih)
8. [Langkah 4 — Sizing dan Order Plan](#8-langkah-4--sizing-dan-order-plan)
9. [Langkah 5 — Eksekusi dan Manajemen Posisi](#9-langkah-5--eksekusi-dan-manajemen-posisi)
10. [Langkah 6 — Log dan Review](#10-langkah-6--log-dan-review)
11. [Validasi Strategi dengan Backtest](#11-validasi-strategi-dengan-backtest)
12. [Quick Reference Card](#12-quick-reference-card)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. Filosofi Strategi

Strategi ini bertumpu pada satu premis: **institusi asing yang terus membeli selama beberapa hari adalah sinyal leading, bukan lagging**.

Ketika asing net-beli 4 dari 5 hari terakhir, ada dua kemungkinan:
1. Mereka sedang membangun posisi sebelum katalis yang belum publik tahu
2. Mereka meng-average-down posisi yang sudah ada

Dalam kedua kasus, ada **price floor** alami — mereka tidak akan jual sebelum balik modal (atau bahkan untung). FVWAP Discount mengukur seberapa jauh mereka masih underwater.

**Kombinasi ideal:**
```
Asing net-beli konsisten (streak ≥ 3d)
+ Mereka masih underwater (VWAP Discount > 0%)
+ Harga dalam range, bukan trending kuat (TREND = SIDE)
+ Volatilitas rendah, siap breakout (BB Width ≤ 20th percentile)
+ RSI sekitar 40 (momentum tapi tidak overbought)
```

Ini bukan strategi breakout (beli setelah harga naik). Ini **buy-before-the-move** — masuk saat asing masih mengumpulkan, keluar saat momentum mulai terlihat di chart.

---

## 2. Prasyarat

### Data Lokal (Wajib)

Screener menghitung skor dari data broker flow yang tersimpan lokal. Tanpa ini, skor tidak bisa dihitung.

```bash
# Pertama kali — unduh data universe + broker flow
saham update --universe lq45        # harga + broker flow LQ45 (~5 menit)

# Saham di luar LQ45 yang ingin di-screen
saham fetch BUMI GOTO BREN --days 365
saham broker fetch BUMI GOTO BREN --days 90
```

### Seberapa Sering Refresh?

| Kapan | Perintah |
|-------|---------|
| Setiap hari sebelum screen | `saham update --universe lq45` |
| Mingguan untuk universe lebih luas | `saham update --universe idx80` |
| Kalau ada saham baru masuk radar | `saham broker fetch TICKER --days 90` |

Data yang sudah fresh (< 5 hari) otomatis di-skip — tidak ada download ulang.

---

## 3. Peta Waktu Workflow

```
FREKUENSI        AKTIVITAS                           PERINTAH
─────────────────────────────────────────────────────────────────────────
Setiap hari      Refresh data harga + broker flow    saham update --universe lq45
Setiap hari      Cek regime pasar                    saham regime
Setiap hari      Jalankan screener                   saham swing screen --universe lq45 --multi
Per kandidat     Analisis detail + sizing            saham swing analyze TICKER --preset foreign-bounce
Saat entry       Log ke journal                      saham swing log --ticker TICKER
Saat exit        Catat outcome                       (manual di journal)
Mingguan         Review hit rate                     saham swing review --horizon 10
Bulanan          Validasi dengan backtest             saham swing backtest --universe lq45 --start ...
```

**Estimasi waktu harian: 15–20 menit** (update + screen + 2–3 analisis detail).

---

## 4. Pahami Skor Akumulasi

Sebelum menggunakan screener, pahami apa yang diukur tiap komponen skor.

### Komponen Skor (Total Maks ~120, Soft Cap)

| Komponen | Maks Poin | Formula | Artinya |
|----------|-----------|---------|---------|
| **Konsistensi** | 40 pts | `net_buy_ratio × 40` | Berapa hari asing net-beli dari total window |
| **Streak** | 30 pts | `30 × (1 − e^(−streak/7))` | Berapa hari beruntun net-beli terakhir |
| **VWAP Discount** | 20 pts | Linear: 0% → 0 pts, ≥10% → 20 pts | Seberapa jauh asing masih underwater |
| **RSI Headroom** | 10 pts | Puncak di RSI=40, nol di ≤25 atau ≥75 | Momentum tapi ada ruang naik |
| **Flow Ratio** | 10 pts | Linear: 0% → 0 pts, ≥20% → 10 pts | Dominansi volume asing vs total |
| **BB Squeeze** | 10 pts | Bottom 20%ile: 5–10 pts; bottom 40%ile: 0–5 pts | Volatilitas rendah, siap breakout |
| **Broker Institusional** | 5 pts | Bonus kalau ada broker institusional di top buyer | UBS, JP Morgan, dll. ada di sisi beli |

### Interpretasi Skor

| Range | Arti | Aksi |
|-------|------|------|
| **≥ 70** | Sinyal kuat — beberapa komponen selaras | Analisis detail, pertimbangkan entry |
| **40–69** | Sinyal sedang — ada akumulasi tapi belum penuh | Monitor, perlu konfirmasi tambahan |
| **< 40** | Sinyal lemah | Lewati untuk saat ini |

### Kolom Output Screener Lengkap

| Kolom | Contoh | Artinya |
|-------|--------|---------|
| `SCORE` | 72.4 | Skor komposit 0–120 |
| `STREAK` | 4d | Hari beruntun net-beli terakhir |
| `NET_DAYS` | 4/7 | 4 hari net-beli dari 7 hari window |
| `NET_VALUE` | +19.4B | Kumulatif net IDR asing di window |
| `FLOW%` | +24.8 | % volume harian yang merupakan net asing |
| `VWAP_DISC` | +3.2% | Positif = asing underwater (bullish floor) |
| `RSI` | 42.5 | RSI 14-hari; ideal ~40 |
| `BB%ILE` | 15% | Persentil BB Width vs 60 hari; ≤20% = coiled spring |
| `TREND` | SIDE | UP / DOWN / SIDE vs SMA20 |

---

## 5. Langkah 1 — Cek Regime Pasar

Sebelum screening, tahu dulu sedang di regime apa. Sinyal akumulasi yang sama **jauh lebih reliable di SIDEWAYS dibanding RISK_OFF**.

```bash
saham regime
```

Contoh output:
```
MARKET REGIME — 2026-06-13
═══════════════════════════════════════════════════════
Regime: SIDEWAYS

Breadth (IDX80):
  Above SMA20 : 54.2%
  5d change   : -2.1%

Benchmark (^JKSE):
  Price       : 6,892
  vs SMA20    : -0.8%
  vs SMA50    : +1.2%
  20d return  : -1.4%

Foreign Flow Breadth: +23.4% stocks with net foreign buy
═══════════════════════════════════════════════════════
```

### Empat Regime dan Implikasinya

| Regime | Artinya | Strategi Foreign Accumulation |
|--------|---------|------------------------------|
| **BULLISH** | Breadth > 60%, IHSG di atas SMA20+50 | Oke, tapi saham lebih mahal — VWAP Disc mungkin kecil |
| **SIDEWAYS** | Breadth 40–60%, IHSG ranging | **Terbaik** — harga flat, asing masih mengumpulkan |
| **WEAK** | Breadth < 40%, IHSG di bawah SMA20 | Hati-hati — masih bisa kerja, ukuran lebih kecil |
| **RISK_OFF** | Breadth < 30%, IHSG turun kuat | Skip swing — tunggu stabilisasi |

**Aturan praktis:**
- `BULLISH` atau `SIDEWAYS` → jalankan screener normal
- `WEAK` → gunakan `--min-score 60`, ukuran posisi 50% dari normal
- `RISK_OFF` → tidak entry swing baru, fokus ke cash atau posisi yang sudah ada

---

## 6. Langkah 2 — Jalankan Screener Akumulasi

### Screening Dasar

```bash
saham swing screen --universe lq45
```

Contoh output (7d window):
```
FOREIGN ACCUMULATION — LQ45 | 7d window | 2026-06-13
══════════════════════════════════════════════════════════════════════════════
  # TICKER   SCORE  STREAK  NET_DAYS    NET_VALUE  FLOW%  VWAP_DISC    RSI  BB%ILE TREND
──────────────────────────────────────────────────────────────────────────────
  1 GGRM      72.4      4d       4/7       +19.4B  +24.8      +3.2%   42.5     15%  SIDE
  2 BBRI      68.1      3d       5/7       +89.2B  +18.2      +1.8%   44.0     28%  SIDE
  3 ASII      61.3      2d       5/7       +32.7B  +15.4      +2.1%   38.2     35%  DOWN
  4 TLKM      58.9      3d       4/7       +45.1B  +12.3      +0.9%   55.1     42%  SIDE
  5 BMRI      54.2      2d       4/7       +67.8B  +11.7      -0.3%   61.4     55%  UP
  ...
══════════════════════════════════════════════════════════════════════════════
Run with --guide for column explanations
```

---

### Screening Multi-Window (Lebih Informatif)

Tampilkan skor 7d, 30d, dan 90d sekaligus — ini memberikan konteks apakah akumulasi baru mulai atau sudah berlangsung lama.

```bash
saham swing screen --universe lq45 --multi
```

Contoh output:
```
FOREIGN ACCUMULATION — LQ45 | MULTI-WINDOW | 2026-06-13
══════════════════════════════════════════════════════════════════════════
  # TICKER     7d    30d    90d  PATTERN            TREND
────────────────────────────────────────────────────────────────────────
  1 GGRM      72.4    78.0    69.8  sustained           SIDE
  2 BBRI      68.1    52.3    38.4  building             SIDE
  3 ASII      61.3    41.2    28.9  building             DOWN
  4 TLKM      58.9    61.2    72.1  long-term only       SIDE
  5 BMRI      54.2    38.1    22.0  fresh rotation       UP
  6 UNVR      48.7    72.3    68.9  long-term only       SIDE
  7 ICBP      42.1    38.4    41.2  sustained            UP
══════════════════════════════════════════════════════════════════════════
```

### Pattern dan Cara Membacanya

| Pattern | Skor Antar Window | Trade Implication | Aksi |
|---------|------------------|-------------------|------|
| **sustained** | Tinggi di SEMUA window (7d/30d/90d ≥ 60) | Asing beli berbulan-bulan — konviksi tertinggi | Entry prioritas |
| **building** | Kuat 7d+30d, lebih lemah 90d | Akselerasi baru-baru ini — momentum sedang terbentuk | Entry dengan konfirmasi |
| **fresh rotation** | Kuat 7d saja, lemah 30d+90d | Baru mulai — bisa awal gerakan atau noise | Monitor dulu, masuk kalau streak bertambah |
| **long-term only** | Kuat 90d, lemah recent | Asing mungkin sudah mulai ambil profit | Waspada, cek FVWAP negatif |
| **coiled spring** | Window apapun ≥ 60 + BB Width ≤ 20%ile | Volatilitas rendah + akumulasi = setup breakout | Entry prioritas tinggi |
| **weak** | Tidak ada window ≥ 60 | Tidak ada pola yang jelas | Skip |

---

### Filter Tambahan

```bash
# Hanya saham yang siap breakout (volatilitas rendah)
saham swing screen --universe lq45 --squeeze-only

# Hanya saham yang asing masih underwater (ada price floor)
saham swing screen --universe lq45 --vwap-only

# Kombinasi: skor tinggi + squeeze + underwater
saham swing screen --universe lq45 --vwap-only --squeeze-only --min-score 60

# Tampilkan breakdown skor per komponen
saham swing screen --universe lq45 --breakdown

# Universe lebih luas
saham swing screen --universe idx80 --multi --min-score 50 --top 15

# Saham spesifik (bukan universe)
saham swing screen BBCA BBRI BMRI TLKM --multi
```

---

### Pilih Kandidat

Setelah screener, pilih 2–4 saham untuk analisis detail. Prioritas:

1. `sustained` atau `coiled spring` pattern
2. VWAP_DISC positif (asing underwater)
3. TREND = `SIDE` (masuk sebelum move, bukan saat sudah naik)
4. BB%ILE ≤ 30% (volatilitas rendah)
5. RSI sekitar 30–50 (ada ruang naik)

---

## 7. Langkah 3 — Analisis Kandidat Terpilih

Untuk setiap kandidat dari screener, jalankan analisis lengkap dengan preset `foreign-bounce`.

```bash
saham swing analyze GGRM --preset foreign-bounce --capital 10000000 --with-regime
```

### Contoh Output Lengkap

```
══════════════════════════════════════════════════════════════════════════════
SWING ANALYSIS — GGRM  |  2026-06-13  |  balanced profile
══════════════════════════════════════════════════════════════════════════════

ACCUMULATION (7d)
─────────────────────────────────────────────────────────────────────────────
  Score     :  72.4 / 120
  Streak    :  4d consecutive foreign net-buy
  Net Days  :  4/7 (57%)
  Net Value :  +19.4 B IDR
  Flow %    :  +24.8% of daily volume
  VWAP Disc :  +3.2%  (foreigners underwater — price floor)
  BB %ile   :  15%    (coiled spring — bottom 20th pctile)
  RSI       :  42.5
  Trend     :  SIDE   (vs SMA20)

PRESET — foreign-bounce
─────────────────────────────────────────────────────────────────────────────
  Gate              Required    Actual    Status
  score             ≥ 70        72.4      ✓ PASS
  vwap_disc_pct     ≥ +3.0%     +3.2%     ✓ PASS
  trend             SIDE        SIDE      ✓ PASS
  flow_pct          ≥ +5.0%     +24.8%    ✓ PASS
  rsi               ≤ 60        42.5      ✓ PASS

  Signal: ENTER  (5/5 gates passed)
  Plan  : TP +5%  |  SL -5%  |  Max Hold 10 days

MARKET REGIME
─────────────────────────────────────────────────────────────────────────────
  Regime    : SIDEWAYS
  Breadth   : 54.2% above SMA20  (5d Δ: -2.1%)
  IHSG      : 6,892  |  vs SMA20: -0.8%  |  vs SMA50: +1.2%
  Context   : Ranging market — foreign-bounce has historically performed
              better in SIDEWAYS vs BULLISH (less noise, cleaner setups)

RISK CONFIRMATION
─────────────────────────────────────────────────────────────────────────────
  SMA20     :  47,200  |  Price 47,100 — just below, neutral
  EMA20     :  47,050  |  Price slightly above — mild bullish
  RSI(14)   :  42.5    |  Room to run before overbought
  Verdict   :  CONFIRMING — no contradicting signals

PRESET SIZING  (capital: Rp 10,000,000 | risk: 1.0% = Rp 100,000)
─────────────────────────────────────────────────────────────────────────────
  Entry     :  47,100  (latest close)
  Stop      :  44,745  (-5.0%)
  Target    :  49,455  (+5.0%)
  Reward/Risk:  1.0 : 1.0
  Max Lots  :  0 lots  (low capital for price; consider reducing entry)

HISTORY  (strategy: foreign-accumulation | GGRM | since 2024-01-01)
─────────────────────────────────────────────────────────────────────────────
  Trades    :  8
  Win Rate  :  62.5%  (5/8)
  Profit Factor: 1.84
  Max DD    :  -8.2%
  Avg Hold  :  6.2d

SENTIMENT
─────────────────────────────────────────────────────────────────────────────
  Call      :  NEUTRAL
  Confidence:  0.62
  Headlines :  2 neutral, 1 positive (last 7d)

SUMMARY & PLAN
─────────────────────────────────────────────────────────────────────────────
  ► ENTER — all preset gates pass, regime supports, sentiment neutral
  ► Entry : 47,100  (atau limit di support terdekat)
  ► Stop  : 44,745  (preset -5%)
  ► Target: 49,455  (preset +5%, consider Prev H as partial exit)
  ► Hold  : maks 10 hari trading
══════════════════════════════════════════════════════════════════════════════
```

---

### Membaca Gate `foreign-bounce`

Preset `foreign-bounce` mengevaluasi 5 gate secara deterministik:

| Gate | Requirement | Rationale |
|------|-------------|-----------|
| `score ≥ 70` | Skor komposit minimal | Butuh konviksi yang cukup kuat |
| `vwap_disc_pct ≥ +3%` | Asing underwater ≥ 3% | Price floor aktif — mereka defend posisi |
| `trend = SIDE` | Harga ranging vs SMA20 | Masuk sebelum move, bukan saat sudah trending |
| `flow_pct ≥ +5%` | Asing dominasi ≥ 5% volume harian | Bukan noise — ada aksi nyata setiap hari |
| `rsi ≤ 60` | RSI tidak overbought | Masih ada ruang naik |

**Output gate:**
- `ENTER` — semua 5 gate pass
- `WATCH` — skor ≥ 70 ATAU ≤ 2 gate gagal — monitor, mungkin masuk besok
- `AVOID` — terlalu banyak gate gagal

### Opsi Analisis Lainnya

```bash
# Tanpa preset — analisis lengkap dengan profil risiko
saham swing analyze BBRI --profile conservative --capital 10000000

# Aggressive profile dengan ATR stop lebih longgar
saham swing analyze BBRI --profile aggressive --capital 10000000 --atr-mult 2.0

# Dengan custom entry price
saham swing analyze BBRI --preset foreign-bounce --capital 10000000 --entry 4825

# Tanpa backtest (lebih cepat)
saham swing analyze BBRI --preset foreign-bounce --no-backtest

# Format JSON (untuk integrasi)
saham swing analyze BBRI --preset foreign-bounce --format json
```

---

## 8. Langkah 4 — Sizing dan Order Plan

### Sizing Standalone (Kalau Sudah Tahu Entry)

```bash
saham swing size BBRI --capital 10000000 --risk-pct 1 --entry 4825
```

Contoh output:
```
POSITION SIZING — BBRI
══════════════════════════════════════════════════════
INPUTS
  Capital        : Rp 10,000,000
  Risk %         : 1.0%  (Rp 100,000 at risk)
  Entry          : 4,825
  ATR(14)        : 128.4
  ATR Mult       : 1.5×

STOP
  Stop Price     : 4,633  (4,825 - 1.5 × 128.4)
  Distance       : 192 per share
  Stop %         : -3.98%

TARGET
  Target Price   : 5,209  (2.0 : 1.0 R/R)
  Target %       : +7.96%

POSITION
  Max Lots       : 5 lots  (500 shares)
  Estimated Cost : Rp 2,412,500
  Actual Risk    : Rp 96,000  (0.96%)
══════════════════════════════════════════════════════
```

### Parameter Sizing

| Parameter | Default | Kapan Diubah |
|-----------|---------|-------------|
| `--risk-pct` | 1.0 | 0.5 kalau regime WEAK, 2.0 kalau setup sangat kuat |
| `--atr-mult` | 1.5 | 1.0 untuk stop ketat, 2.0 kalau saham volatile |
| `--rr` | 2.0 | Turunkan ke 1.5 kalau target jelas di resistance dekat |
| `--entry` | latest close | Masukkan harga limit order yang kamu rencanakan |

### Template Order Plan

```
TICKER: GGRM
──────────────────────────────────────────────
Setup   : sustained pattern | ENTER (5/5 gates)
Regime  : SIDEWAYS — kondisi optimal

Entry   : Limit buy di 47,100 (atau 47,000 kalau mau lebih aman)
Stop    : 44,745 (-5%) — pasang segera setelah terisi
Target 1: Prev High 48,200 — jual 50% di sini
Target 2: +5% = 49,455 — sisanya trailing stop
Max Hold: 10 hari trading (dari tanggal entry)

Lots    : 2 lots (Rp ~9.4jt, risk Rp ~94rb = 0.94% modal)
──────────────────────────────────────────────
```

---

## 9. Langkah 5 — Eksekusi dan Manajemen Posisi

### Entry

Swing trade ini **tidak time-sensitive** seperti intraday — tidak perlu masuk detik pertama. Pilihan entry:

1. **Limit di close kemarin** — masuk kalau harga confirm di level itu
2. **Limit sedikit di bawah close** — lebih aman, mungkin tidak kena kalau harga langsung naik
3. **Limit di support terdekat** (Prev Low, SMA20) — entry lebih baik, probabilitas lebih tinggi

Jangan market order. Swing trade masuk dengan sabar.

### Stop-Loss

Pasang stop segera setelah order terisi. Untuk swing, dua pilihan:

| Tipe Stop | Formula | Kapan Digunakan |
|-----------|---------|----------------|
| **ATR Stop** | `entry - (ATR × mult)` | Default — mengikuti volatilitas saham |
| **Preset Stop** | `-5%` dari entry | Quick alternative, konsisten dengan backtest |
| **Structural Stop** | Bawah support terdekat | Kalau ada level teknikal yang jelas |

Jangan geser stop ke bawah. Boleh geser ke atas (trailing) setelah harga bergerak menguntungkan.

### Manajemen Posisi Aktif

```
Setelah entry:
  ☐ Stop terpasang?
  ☐ Target 1 sudah ditandai?
  ☐ Tanggal max hold sudah dicatat?

Harian (cukup 5 menit):
  ☐ Cek apakah streak asing masih berlanjut (saham swing screen TICKER)
  ☐ Kalau streak BERHENTI selama 2 hari → pertimbangkan exit lebih awal

Saat Target 1 (Prev High) tercapai:
  ☐ Jual 50% posisi
  ☐ Geser stop ke breakeven (harga entry)
  ☐ Biarkan 50% sisanya dengan trailing stop

Kalau streak asing jadi negatif (mulai distribusi):
  ☐ Exit SEMUA posisi — sinyal dasar sudah hilang
  ☐ Jangan tunggu stop kena kalau fundamentalnya sudah berubah

Kalau max hold tercapai (10 hari):
  ☐ Exit semua posisi — strategi ini dirancang untuk 10 hari maks
```

### Monitoring Harian Cepat

```bash
# Cek apakah setup kandidat aktif masih valid
saham swing screen GGRM BBRI --multi

# Kalau streak berhenti, cek detail
saham broker flow GGRM --days 5
```

---

## 10. Langkah 6 — Log dan Review

### Log Kandidat ke Journal

Catat setiap kandidat yang kamu analisis (bukan hanya yang kamu masuki) — ini membangun database untuk review akurasi.

```bash
saham swing log --ticker GGRM --window 7

# Dengan harga entry
saham swing log --ticker GGRM --window 7 --entry-price 47100
```

### Review Performa Strategi

```bash
# Review return 10 hari setelah log
saham swing review --horizon 10

# Review return 5 hari
saham swing review --horizon 5
```

Contoh output:
```
SWING REVIEW — horizon: 10d | 2026-06-13
═══════════════════════════════════════════════════════════════════
BY SCORE BUCKET
  Score ≥ 70  :  12 entries | avg +3.8%  | win rate 66.7%
  Score 40–69 :   8 entries | avg +1.2%  | win rate 50.0%
  Score < 40  :   4 entries | avg -0.8%  | win rate 25.0%

BY PATTERN
  sustained       :  7 entries | avg +4.2%  | win rate 71.4%
  building        :  6 entries | avg +2.8%  | win rate 66.7%
  fresh rotation  :  4 entries | avg +0.9%  | win rate 50.0%
  long-term only  :  3 entries | avg -1.1%  | win rate 33.3%

SIGNAL DELTA ANALYSIS
  streak (higher → better return):  r = +0.41  ✓ predictive
  vwap_disc (higher → better):      r = +0.38  ✓ predictive
  bb_pctile (lower → better):       r = -0.29  ✓ predictive
  flow_pct (higher → better):       r = +0.22  ~ weak signal

RECOMMENDATION
  Focus on: sustained + building patterns, streak ≥ 3d, vwap_disc ≥ 3%
  Reduce: long-term only (negative avg return)
═══════════════════════════════════════════════════════════════════
```

---

## 11. Validasi Strategi dengan Backtest

Sebelum sizing besar atau mengubah parameter, validasi dengan backtest historis.

### Backtest Dasar

```bash
saham swing backtest --universe lq45 --start 2025-01-01
```

### Backtest dengan Regime Filter (Direkomendasikan)

```bash
# Bandingkan performa berdasarkan regime entry
saham swing backtest --universe lq45 --start 2025-01-01 --with-regime
```

Contoh output:
```
SWING BACKTEST — foreign-bounce | LQ45 | 2025-01-01 → 2026-06-13
═══════════════════════════════════════════════════════════════════
SUMMARY
  Initial Capital  : Rp 100,000,000
  Final Equity     : Rp 118,420,000
  Total Return     : +18.4%
  Max Drawdown     : -12.3%
  Trade Count      : 87
  Win Rate         : 59.8%
  Profit Factor    : 1.72
  Exposure %       : 34.2%

PERFORMANCE BY ENTRY REGIME
  BULLISH  : 22 trades | win 63.6% | avg +3.1% | PF 1.91
  SIDEWAYS : 41 trades | win 65.9% | avg +3.8% | PF 2.14  ← best
  WEAK     : 18 trades | win 50.0% | avg +1.2% | PF 1.28
  RISK_OFF :  6 trades | win 33.3% | avg -2.1% | PF 0.61  ← avoid

RECOMMENDATION
  Filter to BULLISH + SIDEWAYS for better risk-adjusted returns
  Command: --allow-regimes BULLISH,SIDEWAYS
═══════════════════════════════════════════════════════════════════
```

### Bandingkan Variant Regime Filter

```bash
saham swing compare --universe lq45 --start 2025-01-01
```

Contoh output:
```
VARIANT COMPARISON — LQ45 | 2025-01-01 → today
════════════════════════════════════════════════════════
  Variant           Return   MaxDD   Trades  WinRate  PF
  baseline          +18.4%  -12.3%      87    59.8%  1.72
  sideways_only     +21.2%   -8.9%      41    65.9%  2.14  ← best
  weak_plus         +19.1%  -11.2%      59    61.0%  1.83
════════════════════════════════════════════════════════
```

### Backtest Saham Spesifik

```bash
saham swing backtest BBCA BBRI BMRI --start 2025-01-01 --capital 50000000
```

### Parameter Backtest yang Bisa Disesuaikan

| Parameter | Default | Keterangan |
|-----------|---------|-----------|
| `--take-profit` | 5.0% | Target preset |
| `--stop-loss` | 5.0% | Stop preset |
| `--max-hold` | 10 | Maks hari hold |
| `--max-positions` | 5 | Posisi concurrent maksimal |
| `--risk-pct` | 1.0% | Risk per trade |
| `--cost-bps` | 0.0 | Biaya transaksi one-way (bps) |
| `--allow-regimes` | all | Filter: `BULLISH,SIDEWAYS` atau `SIDEWAYS` saja |

---

## 12. Quick Reference Card

```
┌──────────────────────────────────────────────────────────────────────┐
│  SWING FOREIGN ACCUMULATION — QUICK REFERENCE                        │
├──────────────────────────────────────────────────────────────────────┤
│  SETUP (sekali)                                                       │
│    saham update --universe lq45                                       │
├──────────────────────────────────────────────────────────────────────┤
│  SETIAP HARI (15–20 menit)                                            │
│    saham update --universe lq45            ← refresh data            │
│    saham regime                            ← cek konteks pasar       │
│    saham swing screen --universe lq45 --multi ← scan universe        │
├──────────────────────────────────────────────────────────────────────┤
│  PER KANDIDAT (5 menit/saham)                                         │
│    saham swing analyze TICKER \                                       │
│      --preset foreign-bounce \                                        │
│      --capital 10000000 \                                             │
│      --with-regime                                                    │
├──────────────────────────────────────────────────────────────────────┤
│  FILTER SCREENER BERGUNA                                              │
│    --squeeze-only     BB Width ≤ 20th pctile (coiled spring)         │
│    --vwap-only        Asing masih underwater                         │
│    --min-score 60     Hanya skor tinggi                               │
│    --multi            Tampilkan 7d/30d/90d + pattern                 │
│    --breakdown        Skor per komponen                               │
├──────────────────────────────────────────────────────────────────────┤
│  PRIORITAS ENTRY                                                      │
│    ✓ Gate: ENTER (5/5 gates pass)                                    │
│    ✓ Pattern: sustained atau coiled spring                            │
│    ✓ VWAP_DISC > 0% (asing underwater)                               │
│    ✓ TREND = SIDE (masuk sebelum move)                               │
│    ✓ Regime: SIDEWAYS atau BULLISH                                    │
├──────────────────────────────────────────────────────────────────────┤
│  SKIP KALAU                                                           │
│    ✗ Gate: AVOID                                                      │
│    ✗ Pattern: long-term only                                          │
│    ✗ Regime: RISK_OFF                                                 │
│    ✗ TREND = UP (sudah terlambat)                                    │
│    ✗ VWAP_DISC negatif besar (asing sudah untung, siap jual)         │
├──────────────────────────────────────────────────────────────────────┤
│  MANAJEMEN POSISI                                                     │
│    Stop  : pasang segera setelah entry, jangan digeser ke bawah      │
│    Target 1: Prev High — jual 50%, geser stop ke breakeven           │
│    Target 2: +5% atau trailing stop                                   │
│    Exit early: streak asing berhenti 2+ hari berturut-turut          │
│    Max hold: 10 hari trading                                          │
├──────────────────────────────────────────────────────────────────────┤
│  JOURNAL                                                              │
│    saham swing log --ticker TICKER --entry-price XXXX                 │
│    saham swing review --horizon 10                                    │
├──────────────────────────────────────────────────────────────────────┤
│  VALIDASI BERKALA (bulanan)                                           │
│    saham swing backtest --universe lq45 --start 2025-01-01 --with-regime
│    saham swing compare --universe lq45 --start 2025-01-01            │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 13. Troubleshooting

### Screener Tidak Menampilkan Skor (Semua N/A atau 0)

```
! BBCA: No broker data — run 'saham broker fetch BBCA' first
```

```bash
saham broker fetch BBCA --days 90
```

Kalau sudah ada data tapi skor tetap 0, cek apakah data fresh:
```bash
saham broker flow BBCA --days 7
```

### Skor Tinggi Tapi `WATCH` atau `AVOID`

Artinya satu gate spesifik gagal. Cek detail:
```bash
saham swing analyze TICKER --preset foreign-bounce
```

Lihat gate mana yang `✗ FAIL` dan alasannya:
- `vwap_disc < 3%` → asing sudah dekat breakeven, floor lebih lemah
- `trend ≠ SIDE` → harga sudah trending, bukan setup ideal lagi
- `rsi > 60` → overbought, risiko koreksi

### Pattern `long-term only` Tapi Skor Tinggi

Artinya akumulasi kuat di 90d tapi melemah di 30d dan 7d. Ini warning: asing mungkin sudah mulai distribusi perlahan. Cek:
```bash
saham broker flow TICKER --days 30
```

Kalau trend berbalik (lebih banyak hari sell belakangan), skip.

### Backtest Profit Factor < 1.0

Strategi tidak profitable untuk periode/universe itu. Coba:
1. Filter regime: `--allow-regimes BULLISH,SIDEWAYS`
2. Perkecil universe: dari `idx80` ke `lq45`
3. Naikkan `--min-score` di screener ke 60 atau 70

### `saham regime` Menunjukkan RISK_OFF

Jangan entry swing baru. Fokus ke:
```bash
# Pantau regime setiap hari sampai membaik
saham regime

# Kalau ada posisi terbuka, cek apakah masih valid
saham swing screen TICKER1 TICKER2 --multi
```

---

## Catatan Penting

- Strategi ini dirancang untuk holding 3–10 hari trading, bukan intraday
- Sinyal akumulasi adalah **leading indicator** — terkadang harga belum bergerak saat entry
- `sustained` pattern lebih reliable dari `fresh rotation` — tapi lebih lambat terdeteksi
- Paper trade minimal 20 setup menggunakan `saham swing log` + `saham swing review` sebelum sizing besar
- Data broker IDX (default) adalah data T+0 — akurat tapi mungkin 1 hari delay di beberapa ticker
- Gunakan `--provider stockbit` untuk `saham broker fetch` jika butuh data lebih granular per-broker (butuh auth)

---

*Untuk penjelasan konsep dasar (ATR, RSI, FVWAP), lihat [`how_to_intraday_trading.md`](how_to_intraday_trading.md).*
*Untuk data flow broker detail: `saham broker --help`.*
