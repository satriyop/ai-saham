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
8. [Langkah 4 — Konfirmasi Struktur Chart](#8-langkah-4--konfirmasi-struktur-chart)
9. [Langkah 5 — Sizing dan Order Plan](#9-langkah-5--sizing-dan-order-plan)
10. [Langkah 6 — Eksekusi dan Manajemen Posisi](#10-langkah-6--eksekusi-dan-manajemen-posisi)
11. [Langkah 7 — Log dan Review](#11-langkah-7--log-dan-review)
12. [Validasi Strategi dengan Backtest](#12-validasi-strategi-dengan-backtest)
13. [Quick Reference Card](#13-quick-reference-card)
14. [Troubleshooting](#14-troubleshooting)

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
saham fetch market --universe lq45        # harga + broker flow LQ45 (~5 menit)

# Saham di luar LQ45 yang ingin di-screen
saham fetch market BUMI --days 365
saham fetch market GOTO --days 365
saham fetch market BREN --days 365
```

### Seberapa Sering Refresh?

| Kapan | Perintah |
|-------|---------|
| Setiap hari sebelum screen | `saham fetch market --universe lq45` |
| Mingguan untuk universe lebih luas | `saham fetch market --universe idx80` |
| Kalau ada saham baru masuk radar | `saham fetch market TICKER --days 90` |

Data akan di-gap-fill otomatis kalau cache lokal belum mencapai tanggal hari ini. Output `cached-current` berarti cache sudah sampai hari ini, `+Nrows/span=Nd` berarti ada baris baru tersimpan, dan `up-to-date(YYYY-MM-DD)` berarti provider sudah dicek tetapi belum punya data trading yang lebih baru.

Catatan: opsi `--window 7`, `--window 30`, dan `--window 90` memakai jumlah sesi broker terakhir yang tersedia. Selalu baca `NET_DAYS` / `STREAK` untuk mengetahui berapa sesi yang merupakan net buy asing.

---

## 3. Peta Waktu Workflow

```
FREKUENSI        AKTIVITAS                           PERINTAH
─────────────────────────────────────────────────────────────────────────
Setiap hari      Refresh data harga + broker flow    saham fetch market --universe lq45
Setiap hari      Cek regime pasar                    saham analyze regime
Setiap hari      Jalankan screener                   saham screen accum --universe lq45 --multi
Per kandidat     Analisis detail + sizing            saham analyze swing TICKER --setup foreign-bounce
Saat entry       Log keputusan ke journal            saham trade log swing --ticker TICKER --from-analysis --with-regime
Saat exit        Catat outcome                       (manual di journal)
Mingguan         Review hit rate                     saham trade review swing --horizon 10
Bulanan          Validasi dengan backtest             saham trade backtest-swing --universe lq45 --start ...
```

**Estimasi waktu harian: 15–20 menit** (update + screen + 2–3 analisis detail).

---

## 4. Pahami Skor Akumulasi

Sebelum menggunakan screener, pahami apa yang diukur tiap komponen skor.

### Komponen Skor (Total 0–120, +10 Bonus)

| Komponen | Maks Poin | Formula | Artinya |
|----------|-----------|---------|---------|
| **Konsistensi** | 40 pts | `net_buy_ratio × 40` | Berapa hari asing net-beli dari total window |
| **Streak** | 30 pts | `30 × (1 − e^(−streak/7))` | Berapa hari beruntun net-beli terakhir |
| **VWAP Discount** | 20 pts | Linear: 0% → 0 pts, ≥10% → 20 pts | Seberapa jauh asing masih underwater |
| **RSI Headroom** | 10 pts | Puncak di RSI=40, nol di ≤25 atau ≥75 | Momentum tapi ada ruang naik |
| **Flow Ratio** | 10 pts | Linear: 0% → 0 pts, ≥20% → 10 pts | Dominansi volume asing vs total |
| **BB Squeeze** | 10 pts | Bottom 20%ile: 5–10 pts; bottom 40%ile: 0–5 pts | Volatilitas rendah, siap breakout |
| **BCI CLUSTER** | 15 pts | 3+ Tier 1 foreign desks (AK/BK/ZP/KZ/YU/RX/HD/CP/DR) di top net-buyers | Broker institusional asing dominan |
| **BCI STABLE** | 5 pts | 1–2 Tier 1 foreign desks di top net-buyers | Ada institusional asing |
| **BCI RETAIL-LED** | 0 pts | 0 Tier 1 foreign desks | Didominasi retail/noise |
| **Sektor Breadth** | +10 | Bonus ke SEMUA anggota grup kalau ≥60% peers sektor positif | Konfirmasi rotasi sektor |

Skor di-cap di 120 lalu ditambah bonus sektor (sehingga bisa >120). Definisi komponen bisa dilihat dengan `--explain` atau `--guide`.

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
| `NET_DAYS` | 4/7 | 4 sesi net-beli dari 7 sesi broker |
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
saham analyze regime
```

Contoh output:
```
══════════════════════════════════════════════════════════════════════════════
MARKET REGIME
══════════════════════════════════════════════════════════════════════════════
Date: 2026-06-13 | Label: SIDEWAYS | Score: 5/7

METRIC                                    VALUE
────────────────────────────────────────────────
^JKSE close                            6,892.34
Benchmark SMA20                         6,941.50
Benchmark SMA50                         6,847.80
Benchmark 5d return                        -0.8%
Benchmark 20d return                       -1.4%
Breadth above SMA20                        54.2%
Breadth change 5d                          -2.1%
Foreign flow breadth                       23.4%
Universe evaluated                       62/80
Flow evaluated                           58/80
```

### Empat Regime dan Implikasinya

Sistem menghitung skor komposit **0–7** (7-point check) untuk menentukan kondisi pasar secara objektif.

**Checklist Skor (+1 per item):**
1. IHSG di atas SMA20
2. IHSG di atas SMA50
3. Return IHSG 5-hari positif
4. Return IHSG 20-hari positif
5. Universe Breadth >= 50% (saham di atas SMA20)
6. Breadth membaik (5-day change >= 0)
7. Foreign Flow Breadth >= 50% (saham dengan net-buy asing)

| Regime | Skor | Artinya | Strategi Foreign Accumulation |
|--------|------|---------|------------------------------|
| **BULLISH** | 6–7 | Konfirmasi kuat di benchmark & breadth | Oke, tapi saham lebih mahal — VWAP Disc mungkin kecil |
| **SIDEWAYS** | 4–5 | Kondisi normal, tidak ada tren dominan | **Terbaik** — harga flat, asing masih mengumpulkan |
| **WEAK** | 2-3 | Tekanan jual meningkat, IHSG di bawah SMA | Hati-hati — gunakan `--min-foreign-flow-score 70`, size 50% |
| **RISK_OFF** | 0–1 | Penjualan massal (Panic/Crash) | **Skip swing** — tunggu stabilisasi |

**Aturan praktis:**
- `BULLISH` atau `SIDEWAYS` → jalankan screener normal
- `WEAK` → gunakan `--min-foreign-flow-score 60`, ukuran posisi 50% dari normal
- `RISK_OFF` → tidak entry swing baru, fokus ke cash atau posisi yang sudah ada

---

## 6. Langkah 2 — Jalankan Screener Akumulasi

### Screening Dasar

```bash
saham screen accum --universe lq45
```

Contoh output (7 sesi broker):
```
FOREIGN ACCUMULATION — LQ45 | 7 sessions | 2026-06-13
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
Score 0–120 | consistency 40 | streak 30 | VWAP 20 | RSI 10 | flow 10 | BB 10 | BCI 0/5/15
Run with --guide for column explanations
```

---

### Screening Multi-Window (Lebih Informatif)

Tampilkan skor 7, 30, dan 90 sesi sekaligus — ini memberikan konteks apakah akumulasi baru mulai atau sudah berlangsung lama.

```bash
saham screen accum --universe lq45 --multi
```

Contoh output:
```
FOREIGN ACCUMULATION — LQ45 | MULTI-WINDOW | 2026-06-13
══════════════════════════════════════════════════════════════════════════
  # TICKER     7s    30s    90s  PATTERN            TREND     BRK
────────────────────────────────────────────────────────────────────────
  1 GGRM      72.4    78.0    69.8  sustained           SIDE  smart+
  2 BBRI      68.1    52.3    38.4  building             SIDE  mixed
  3 ASII      61.3    41.2    28.9  building             DOWN  noise+
  4 TLKM      58.9    61.2    72.1  long-term only       SIDE  smart-
  5 BMRI      54.2    38.1    22.0  fresh rotation       UP      n/a
  6 UNVR      48.7    72.3    68.9  long-term only       SIDE  mixed
  7 ICBP      42.1    38.4    41.2  sustained            UP    smart+
══════════════════════════════════════════════════════════════════════════
```

### Pattern dan Cara Membacanya

| Pattern | Skor Antar Window | Trade Implication | Aksi |
|---------|------------------|-------------------|------|
| **sustained** | Tinggi di SEMUA window (7/30/90 sesi ≥ 60) | Asing beli berbulan-bulan — konviksi tertinggi | Entry prioritas |
| **building** | Kuat 7s+30s, lebih lemah 90s | Akselerasi baru-baru ini — momentum sedang terbentuk | Entry dengan konfirmasi |
| **fresh rotation** | Kuat 7s saja, lemah 30s+90s | Baru mulai — bisa awal gerakan atau noise | Monitor dulu, masuk kalau streak bertambah |
| **long-term only** | Kuat 90s, lemah recent | Asing mungkin sudah mulai ambil profit | Waspada, cek FVWAP negatif |
| **coiled spring** | Window apapun ≥ 60 + BB Width ≤ 20%ile | Volatilitas rendah + akumulasi = setup breakout | Entry prioritas tinggi |
| **weak** | Tidak ada window ≥ 60 | Tidak ada pola yang jelas | Skip |

`BRK` adalah ringkasan kualitas top-broker bernama dari cache Stockbit:

| BRK | Arti |
|-----|------|
| `smart+` | Tier smart-money net buy di top-broker row terbaru |
| `noise+` | Tier noise/retail-heavy net buy; hati-hati untuk fresh rotation |
| `smart-` | Tier smart-money net sell; jangan upgrade setup |
| `noise-` | Tier noise/retail-heavy net sell |
| `mixed` | Ada named flow, tapi tidak jelas dipimpin smart/noise tier |
| `n/a` | Tidak ada detail broker Stockbit bernama di cache |

### Enrichment Signals (Stockbit)

Di bawah tabel screener dan output `swing analyze`, muncul baris-baris enrichment
dari cache Stockbit (di-prewarm oleh `saham fetch market`):

| Signal | Contoh Tampilan | Sumber |
|--------|----------------|--------|
| **Analyst Consensus** | `📊 ANALYST: 35B 2H \| target Rp8,827 (+40.7%)` | Stockbit analyst ratings |
| **Shareholding** | `🏦 HOLDING: DWIMURIA 54.9% \| Inst 31.9% \| Individual 8.7%` | Stockbit shareholder API |
| **Bandar Detector** | `🔍 BANDAR: Score +5 (Acc, top1 47%)` | Stockbit market detectors |
| **Fundamentals** | `📈 FUNDAM: P/E 18.3, ROE 21.2%, F-Score 7, quality=True` | Stockbit keystats |
| **Insider Activity** | `⭐ INSIDER BUY — John Doe (Comm) BUY 500,000 @ 1,200` | Stockbit insider API |
| **Corp Action Risk** | `⚠ DIVIDEND RISK` atau `⚠ RIGHTS ISSUE` | Stockbit corp action calendar |
| **Seasonality** | `SEASONAL +0.9% (60%wr, 5y)` | Stockbit seasonality API |

Warna indikatif:
- **Hijau** — bullish/buy sinyal (analyst bullish+upside≥10%, bandar score≥4, quality fundamentals)
- **Kuning** — netral atau akumulasi awal
- **Merah** — bearish/sell sinyal (bandar distributing, analyst sell > buy)
- **Putih** — netral atau data terbatas

Semua sinyal ini read-only — analysis commands tidak pernah memanggil API.
Data di-fetch sekali oleh `saham fetch market`, cache di SQLite.

---

### Filter Tambahan

```bash
# Hanya saham yang siap breakout (volatilitas rendah)
saham screen accum --universe lq45 --squeeze-only

# Hanya saham yang asing masih underwater (ada price floor)
saham screen accum --universe lq45 --vwap-only

# Kombinasi: skor tinggi + squeeze + underwater
saham screen accum --universe lq45 --vwap-only --squeeze-only --min-foreign-flow-score 60

# Tampilkan definisi skor dan konteks run
saham screen accum --universe lq45 --explain

# Universe lebih luas
saham screen accum --universe idx80 --multi --min-foreign-flow-score 50 --top 15

# Saham spesifik (bukan universe)
saham screen accum BBCA BBRI BMRI TLKM --multi
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

Untuk setiap kandidat dari screener, jalankan analisis lengkap dengan setup yang sesuai. Setup tidak dipilih secara implisit; gunakan `--setup` hanya saat ingin mengevaluasi lensa setup tertentu.

```bash
saham analyze swing GGRM --setup foreign-bounce --capital 10000000
```

### Katalog Setup

Semua gate setup bersifat deterministik dan bisa diubah di `config/swing_setups.yaml`.

| Setup | Dipakai Saat | Pertanyaan yang Dijawab |
|-------|--------------|--------------------------|
| `foreign-bounce` | Harga masih range/SIDE dan asing underwater | Apakah akumulasi asing cukup kuat untuk bounce dari area foreign VWAP? |
| `coiled-spring` | Volatilitas rendah, BB width percentile kecil | Apakah akumulasi terjadi saat volatilitas terkompresi sebelum ekspansi? |
| `smart-money-confirmed` | Data top broker detail tersedia | Apakah aliran broker didominasi smart money, bukan noise flow? |
| `pullback-continuation` | Tren sudah UP dan sedang pullback ringan | Apakah pullback masih sehat dan didukung foreign flow? |

Secara default, command ini akan mengecek dan refresh data harga + broker flow hanya untuk ticker tersebut kalau cache lokal stale atau belum ada. Gunakan `--no-refresh` untuk mode cached-only/offline, atau `--force-refresh` kalau ingin memaksa fetch ulang dari provider.

Sentiment/news hanya konteks tambahan dan default-nya mati. Gunakan `--with-sentiment` untuk menampilkan evidence berita; error provider RSS disembunyikan menjadi warning singkat supaya gate deterministik tetap mudah dibaca. Tambahkan `--sentiment-verbose` hanya untuk debugging provider berita.

### Contoh Output Lengkap

Output menggunakan Rich panel-based rendering. Panel inti (Verdict, Signal, Risk, Plan, Data) selalu ditampilkan; panel evidence (SETUP EVIDENCE, FLOW/BROKER DETAIL, STRATEGY EVIDENCE, SENTIMENT EVIDENCE) bersifat opt-in.

```
╭────────────────────────────────────── Swing Analysis - GGRM ──────────────────────────────────────╮
│ ╭─────────────────────────────────────────── Verdict ───────────────────────────────────────────╮ │
│ │ Action Price   Signal  Risk Setup  Market                                                      │ │
│ │ ENTER  47,100  STRONG  OPEN  MATCH  SIDEWAYS                                                  │ │
│ ╰───────────────────────────────────────────────────────────────────────────────────────────────╯ │
│ ╭──────────────────────────────────────────── Signal ───────────────────────────────────────────╮ │
│ │ STRONG score 72.4  ENTER                                                                      │ │
│ │ Bandar Foreign Insider Season Analyst Fwd                                                     │ │
│ │     22      60      50     55      45  55                                                     │ │
│ ╰───────────────────────────────────────────────────────────────────────────────────────────────╯ │
│ ╭───────────────────────────────────────────── Risk ────────────────────────────────────────────╮ │
│ │ Gates     OPEN               no gate fired                                                    │ │
│ │ Technical off                use --with-technical-gate to enable                              │ │
│ ╰───────────────────────────────────────────────────────────────────────────────────────────────╯ │
│ ╭─────────────────────────────────────── Market Context ────────────────────────────────────────╮ │
│ │ Market       SIDEWAYS (4/7)      conviction 0.57                                              │ │
│ │ Signal       score 72.4 → 78.5   from: BULLISH impact (+8%)                                   │ │
│ │ Risk         gate tightened      regime: SIDEWAYS; gate: regime:SIDEWAYS                       │ │
│ ╰───────────────────────────────────────────────────────────────────────────────────────────────╯ │
│ ╭───────────────────────────────────────────── Plan ────────────────────────────────────────────╮ │
│ │ ENTER setup passed. Consider 2 lots at 47,100; TP 49,455; SL 44,745; max hold 10d.            │ │
│ ╰───────────────────────────────────────────────────────────────────────────────────────────────╯ │
│ ╭───────────────────────────────────────────── Data ────────────────────────────────────────────╮ │
│ │ Candles  2026-06-12  ok                                                                       │ │
│ │ Broker   2026-06-12  ok                                                                       │ │
│ │ Quality  OK          broad accumulation; smart support                                        │ │
│ │ Notation Papan Utama                                                                            │ │
│ ╰───────────────────────────────────────────────────────────────────────────────────────────────╯ │
╰──────────────────────────────────────────── 2026-06-13 ───────────────────────────────────────────╯
```

Dengan `--with-technical-gate`, panel Risk menampilkan baris Technical:
```
│ │ Gates     OPEN               no gate fired                                                    │ │
│ │ Technical RSI 43 · SMA above gate: open                                                       │ │
```

Panel evidence berikut muncul saat opsi terkait digunakan:

**SETUP EVIDENCE** (`--setup foreign-bounce`):
```
╭───────────────────────────────────────── SETUP EVIDENCE ─────────────────────────────────────────╮
│ MATCH - foreign-bounce                                                                           │
│ Result Gate        Actual Required Meaning                                                       │
│ PASS   score       72.4   >= 70    overall accumulation conviction                               │
│ PASS   fvwap%      3.2%   >= +3%   foreign holders still have price support incentive            │
│ PASS   trend       SIDE   SIDE     chart regime required by the setup                            │
│ PASS   flow_pct    24.8%  >= +5%   foreign net flow is meaningful versus turnover                │
│ PASS   RSI present 42.5   present  momentum indicator is available                               │
│ PASS   RSI         42.5   <= 60    momentum is not overextended                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

**FLOW / BROKER DETAIL** (`--with-flow-detail`):
```
╭─────────────────────────────────────── FLOW DETAIL ───────────────────────────────────────╮
│ Accumulation (7 sessions)   Score 72.4  STREAK 4s  FLOW% +24.8%  VWAP +3.2%  BB%ILE 15%   │
│   [cons=22.9 streak=15.3 vwap=6.4 rsi=5.8 flow=10.0 bb=8.5]                              │
│                                                                                            │
│ Flow (30 sessions)          +71.81B IDR  BUY/SELL 19/11  STREAK 6s  Avg +18.4%             │
│                                                                                            │
│ Additional Signals & Flags                                                                │
│ 📊 ANALYST: 35B 2H | target Rp8,827 (+40.7%)                                             │
│ 🏦 HOLDING: DWIMURIA 54.9% | Inst 31.9% | Individual 8.7%                                │
│ 🔍 BANDAR: Score +5 (Acc, top1 47%)                                                       │
│ 📈 FUNDAM: P/E 18.3, ROE 21.2%, F-Score 7, quality=True                                  │
│ ⭐ INSIDER BUY — John Doe (Comm) BUY 500,000 @ 1,200                                      │
│ ⚠ DIVIDEND RISK — ex-date within hold window                                             │
│ ★ SEASONAL Dec (score +0.92)                                                              │
╰───────────────────────────────────────────────────────────────────────────────────────────╯

╭─────────────────────────────────────── BROKER DETAIL ───────────────────────────────────────╮
│ 5/5 sessions · stockbit                                                                      │
│ Top buyers       AK +18.20B (4s), CC +12.40B (3s), YP +8.10B (2s)                           │
│ Top sellers      KZ -9.40B (2s), DB -6.70B (1s)                                             │
│ Smart flow       +14.10B IDR   Noise flow  +8.10B IDR                                       │
│ Weighted net     +20.45B IDR   Smart share  58.4%                                           │
│ Concentration    top buyer 38.0%; top seller 41.6%                                          │
│ Quality          broad accumulation; smart support                                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────╯
```

**STRATEGY EVIDENCE** (`--strategy foreign-accumulation`):
```
╭─────────────────────────────────────── STRATEGY EVIDENCE ───────────────────────────────────────╮
│ Historical Backtest (foreign-accumulation): 8 trades                                             │
│ Evidence only: this panel does not change TradeSetup.action.                                    │
│ Win Rate Profit Factor Max Drawdown Avg Win        Avg Loss                                     │
│ 62.5%    1.84          8.2%         4,621,503 IDR  -3,041,931 IDR                               │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

**SENTIMENT EVIDENCE** (`--with-sentiment`):
```
╭─────────────────────────────────────── SENTIMENT EVIDENCE ───────────────────────────────────────╮
│ News Sentiment (3d): NEUTRAL                                                                      │
│ Headlines scanned: 4 (+1 / =2 / -1) | Confidence: 62%                                            │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

RiskEngine sekarang menampilkan `OPEN` (tidak ada gate terpicu) atau `BLOCKED (gate: Nama)` — label risk level lama (`LOW_RISK`/`MODERATE`/`HIGH_RISK`) tidak lagi muncul di output swing. Gunakan `--with-risk-detail` untuk breakdown gate-by-gate dengan nilai SMA/EMA/RSI.

`BROKER DETAIL` hanya muncul kalau cache broker punya transaksi per-broker, biasanya dari Stockbit. Ini adalah view top broker bernama, bukan time-series aggregate foreign flow seperti `FLOW DETAIL`. Pakai blok ini sebagai konteks konfirmasi:

- `broad accumulation` mendukung sinyal aggregate flow.
- `concentrated accumulation` berarti satu broker terlalu dominan; turunkan confidence kecuali chart sangat konstruktif.
- `recent distribution` berarti sesi broker-detail terbaru adalah net foreign selling; jangan upgrade setup hanya karena akumulasi 30 sesi masih positif.
- `Smart flow` / `Noise flow` mengklasifikasikan semua top-broker row yang tersedia di summary Stockbit, termasuk broker lokal kalau Stockbit mengembalikannya.
- Tier broker deterministik: `AK`, `BK`, `KZ`, `ZP`, `RX`, `MS`, `DB`, `CS`, `ML`, `YU` bobot lebih tinggi; `YP`, `PD`, `XL`, `XC` bobot noise lebih rendah.
- Kalau kode broker tidak muncul, artinya tidak ada di top-broker row yang tersimpan, bukan berarti aktivitas broker itu nol.
- `Weighted net` masih layer pengukuran saja. Belum mengubah gate `MATCH/PARTIAL/NO_MATCH`.
- Catatan `Broker quality` di bawah setup adalah konteks konfirmasi/warning saja. `smart+` bisa mendukung `ENTER` atau memprioritaskan `WATCH`, sedangkan `noise+` atau `smart-` berarti chart harus lebih kuat atau setup tidak boleh di-upgrade.

---

### Membaca Gate `foreign-bounce`

Setup `foreign-bounce` mengevaluasi **6 gate** secara deterministik:

| Gate | Requirement | Rationale |
|------|-------------|-----------|
| `score ≥ 70` | Skor komposit minimal | Butuh konviksi yang cukup kuat |
| `vwap_disc_pct ≥ +3%` | Asing underwater ≥ 3% | Price floor aktif — mereka defend posisi |
| `trend = SIDE` | Harga ranging vs SMA20 | Masuk sebelum move, bukan saat sudah trending |
| `flow_pct ≥ +5%` | Asing dominasi ≥ 5% volume harian | Bukan noise — ada aksi nyata setiap hari |
| `RSI present` | Data RSI harus tersedia | Validasi indikator bisa dihitung |
| `rsi ≤ 60` | RSI tidak overbought | Masih ada ruang naik |

**Output gate:**
- `MATCH` — semua gate setup pass
- `PARTIAL` — setup hampir cocok, tetapi masih ada gate gagal dalam batas toleransi
- `NO_MATCH` — terlalu banyak gate gagal atau evidence wajib tidak tersedia

**Regime-adaptive TP/SL:** TP dan SL setup bervariasi berdasarkan regime entry, di-load dari `config/swing_targets.yaml`:

| Regime | TP | SL | R:R |
|--------|----|----|-----|
| BULLISH | +8% | -4% | 2:1 |
| SIDEWAYS | +5% | -5% | 1:1 |
| WEAK | +3% | -3% | 1:1 |
| RISK_OFF | +3% | -3% | 1:1 |
| Default | +5% | -5% | 1:1 |

### Opsi Analisis Lainnya

```bash
# Tanpa setup — verdict inti dengan ATR sizing
saham analyze swing BBRI --capital 10000000 --risk-pct 1

# Dengan entry price override dan risk ratio
saham analyze swing BBRI --capital 10000000 --entry 4825 --rr 2.5

# Dengan custom entry price dan setup
saham analyze swing BBRI --setup foreign-bounce --capital 10000000 --entry 4825

# Dengan TechnicalGate execution gate
saham analyze swing BBRI --setup foreign-bounce --capital 10000000 --with-technical-gate

# Evidence opsional
saham analyze swing BBRI --strategy foreign-accumulation
saham analyze swing BBRI --with-flow-detail --explain
saham analyze swing BBRI --with-sentiment

# Market context preview
saham analyze swing BBRI --with-market-context

# Format JSON (untuk integrasi)
saham analyze swing BBRI --setup foreign-bounce --format json
```

---

## 8. Langkah 4 — Konfirmasi Struktur Chart

Sebelum sizing atau log paper entry, pastikan struktur harga mendukung gate numerik. Ini memakai command chart yang sudah ada dan tidak mengubah sinyal deterministik.

```bash
saham analyze chart price BBRI --sma 20 --days 90
saham analyze chart rsi BBRI --days 90
saham analyze chart volume BBRI --days 30
```

| Cek | Lebih Baik | Hindari |
|-----|------------|---------|
| Struktur harga | Base sideways, higher low, range ketat dekat SMA20/support | Lower-high breakdown, candle merah lebar, harga jauh di bawah support |
| RSI | Pulih dari area 30-50 dan masih punya ruang ke 60 | RSI tertahan di bawah 30 saat harga terus lower low |
| Volume | Hari akumulasi didukung partisipasi volume yang terlihat | Volume tipis, atau spike volume dominan di hari turun |

Aturan praktis:

- `ENTER` dari `saham analyze swing` + chart konstruktif = boleh lanjut sizing/logging.
- `ENTER` + chart breakdown = downgrade ke `WATCH`; tunggu struktur membaik.
- `WATCH` + chart konstruktif = tetap di shortlist, cek ulang besok.
- `AVOID` tetap `AVOID`; chart tidak dipakai untuk override gate deterministik.

---

## 9. Langkah 5 — Sizing dan Order Plan

### Sizing Standalone (Kalau Sudah Tahu Entry)

```bash
saham trade size BBRI --capital 10000000 --risk-pct 1 --entry 4825
```

Contoh output:
```
══════════════════════════════════════════════════════════════════
POSITION SIZE — BBRI · 2026-06-13
══════════════════════════════════════════════════════════════════

INPUTS
  Capital                   10,000,000 IDR
  Risk per trade                 1.00 %  =     100,000 IDR
  Entry (latest close)           4,825
  ATR(14)                       128.40
  ATR multiplier                   1.5×
  Reward : Risk                    2.0

STOP
  Stop price                    4,633
  Stop distance                   192  per share
  Stop %                       -3.98 %

TARGET
  Target price                  5,178
  Target %                     +7.32 %

POSITION
  Raw shares                      520
  Round lots                        5  lots = 500 shares
  Position cost            2,412,500  IDR  (24.1% of capital)
  Actual risk                 96,000  IDR  (vs target 100,000)
  Actual reward              192,000  IDR

══════════════════════════════════════════════════════════════════
ACTION: Buy 5 lots at 4,825.  Stop 4,633.  Target 5,178.
══════════════════════════════════════════════════════════════════
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
Setup   : sustained pattern | ENTER (6/6 gates)
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

## 10. Langkah 6 — Eksekusi dan Manajemen Posisi

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
| **Setup Stop** | `-5%` dari entry | Quick alternative, konsisten dengan backtest |
| **Structural Stop** | Bawah support terdekat | Kalau ada level teknikal yang jelas |

Jangan geser stop ke bawah. Boleh geser ke atas (trailing) setelah harga bergerak menguntungkan.

### Manajemen Posisi Aktif

```
Setelah entry:
  ☐ Stop terpasang?
  ☐ Target 1 sudah ditandai?
  ☐ Tanggal max hold sudah dicatat?

Harian (cukup 5 menit):
  ☐ Cek apakah streak asing masih berlanjut (saham screen accum TICKER)
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
saham screen accum GGRM BBRI --multi

# Kalau streak berhenti, cek detail
saham view broker flow GGRM --days 5
```

---

## 11. Langkah 7 — Log dan Review

### Log Keputusan ke Journal

Catat setiap kandidat yang kamu analisis (bukan hanya yang kamu masuki), tetapi simpan juga ringkasan setup dan rencana trade. Ini membuat review bisa membedakan setup `MATCH`, `PARTIAL`, dan `NO_MATCH`.

```bash
saham trade log swing --ticker GGRM --window 7 --from-analysis --with-regime

# Dengan harga entry yang berbeda dari latest close
saham trade log swing --ticker GGRM --window 7 --entry-price 47100 --from-analysis --with-regime
```

Dengan `--from-analysis`, journal menyimpan:

| Field | Isi |
|-------|-----|
| `setup` | Nama setup, saat ini `foreign-bounce` |
| `setup_match` | `MATCH`, `PARTIAL`, atau `NO_MATCH` |
| `failed_gates` | Gate yang gagal, misalnya VWAP atau trend |
| `regime` | Regime pasar jika memakai `--with-regime` |
| `planned_entry`, `planned_stop`, `planned_target` | Rencana harga dari setup |
| `max_hold_days` | Batas hold setup, saat ini 10 hari trading |

### Review Performa Strategi

```bash
# Review return 10 hari setelah log
saham trade review swing --horizon 10

# Review return 5 hari
saham trade review swing --horizon 5
```

Contoh output:
```
══════════════════════════════════════════════════════════════════
ACCUMULATION TRADE JOURNAL REVIEW
══════════════════════════════════════════════════════════════════
Journal  : journals/accumulation.csv
Entries  : 24 total | 20 with 10d+ data
Horizon  : 10 trading days | min_score filter: 0.0

PERFORMANCE BY SCORE BUCKET
  BUCKET       N    AVG_5D    AVG_10D   WIN_RATE_10D
  --------------------------------------------------
  Score ≥ 70   12    +3.2%     +5.1%           67%
  Score 40–69   8    +1.1%     +1.8%           50%
  Score 0–39    5    -0.8%     -2.1%           40%

PERFORMANCE BY SETUP MATCH
  DECISION       N   AVG_10D   WIN_RATE  AVG_MAX_UP   AVG_MAX_DD
  --------------------------------------------------------------
  ENTER          8    +5.4%       62%       +8.9%       -3.8%
  WATCH          6    +1.7%       50%       +5.2%       -5.9%
  AVOID          3    -2.4%       33%       +2.1%       -7.4%

PERFORMANCE BY PATTERN
  PATTERN              N   AVG_10D   WIN_RATE  AVG_MAX_UP   AVG_MAX_DD
  ----------------------------------------------------------------------
  sustained            7    +6.2%       71%      +10.1%       -3.2%
  building             5    +4.8%       60%       +8.3%       -4.1%
  fresh rotation       3    +0.4%       33%       +5.0%       -6.7%

SIGNAL DELTA (correlation with 10d return)
  SIGNAL         GROUP A                 N_A  AVG_A  GROUP B                 N_B  AVG_B
  ----------------------------------------------------------------------------------
  streak         ≥5d                      12  +5.8%  <5d                      8  +0.9%
  vwap_disc      >0 (underwater)          15  +4.2%  ≤0 (in profit)          5  -1.8%
  bb_pctile      ≤20% (squeeze)            6  +7.1%  >40%                   14  +2.1%
  flow_pct       ≥15%                      9  +6.0%  <15%                   11  +1.3%
```

---

## 12. Validasi Strategi dengan Backtest

Sebelum sizing besar atau mengubah parameter, validasi dengan backtest historis.

### Backtest Dasar

```bash
saham trade backtest-swing --universe lq45 --start 2025-01-01
```

### Backtest dengan Regime Filter (Direkomendasikan)

```bash
# Bandingkan performa berdasarkan regime entry
saham trade backtest-swing --universe lq45 --start 2025-01-01 --with-regime
```

Contoh output:
```
══════════════════════════════════════════════════════════════════════════════
WALK-FORWARD SWING BACKTEST
══════════════════════════════════════════════════════════════════════════════
Setup: foreign-bounce | Period: 2025-01-01 to 2026-06-13
Cost: 20 bps one-way, applied on entry and exit
Read as: the workflow scans each replay date, opens eligible signals within
portfolio limits, then exits by TP/SL/max-hold.

METRIC                             VALUE
──────────────────────────────────────────────
Initial capital               100,000,000
Final equity                  118,400,000
Total return                       +18.40%
Max drawdown                        -8.20%
Trades                                  47
Win rate                             57.4%
Avg trade return                     +1.84%
Profit factor                          1.72
Exposure days                        38.5%

Skipped: no_cash=0, duplicate=0, no_forward_data=5, regime=8

PERFORMANCE BY ENTRY REGIME
──────────────────────────────────────────────────────────────────────────────
REGIME        TRADES    AVG_RET       WIN       TOTAL_PNL
BULLISH           18     +3.1%       67%      12,400,000
SIDEWAYS          22     +1.4%       55%       7,300,000
WEAK               7     -0.8%       43%      -1,200,000
```

### Validasi Broker Quality Dengan Audit

Sebelum `smart+`, `noise+`, atau `smart-` dijadikan gate, ukur dulu hasil historisnya:

```bash
saham analyze accum-audit --universe lq45 --setup foreign-bounce --start 2026-01-01
```

Output audit sekarang punya dimensi `broker_quality`:

| Bucket | Makna |
|--------|-------|
| `smart+` | Top-broker smart-money net buy |
| `noise+` | Top-broker noise/retail-heavy net buy |
| `smart-` | Top-broker smart-money net sell |
| `noise-` | Top-broker noise/retail-heavy net sell |
| `mixed` | Ada detail broker, tapi tidak dominan jelas |
| `no_detail` | Tidak ada top-broker detail di cache |

Gunakan AVG10D, WIN10D, MAXUP, dan MAXDD untuk memutuskan apakah broker quality cukup kuat untuk tetap sebagai warning, menjadi downgrade, atau layak menjadi gate setup baru.

### Bandingkan Variant Regime Filter

```bash
saham analyze swing-compare --universe lq45 --start 2025-01-01
```

Contoh output:
```
══════════════════════════════════════════════════════════════════════════════
SWING BACKTEST COMPARISON
══════════════════════════════════════════════════════════════════════════════
Universe: lq45 | Period: 2025-01-01 to 2026-06-13 | Cost: 20 bps one-way

VARIANT          REGIMES                   TRADES    RETURN    MAX_DD       WIN       PF   SKIP_REG   EXPOSURE
────────────────────────────────────────────────────────────────────────────────────────────────────────────────
baseline         all                           47   +18.4%    -8.2%     57.4%     1.72          0     38.5%
sideways_only    SIDEWAYS,BULLISH              39   +21.2%    -5.8%     61.5%     1.94          8     32.1%
weak_plus        WEAK,SIDEWAYS,BULLISH         44   +19.8%    -7.1%     58.0%     1.81          3     36.4%
```

### Backtest Saham Spesifik

```bash
saham trade backtest-swing BBCA BBRI BMRI --start 2025-01-01 --capital 50000000
```

Default backtest biaya adalah `--cost-bps 20` one-way, diterapkan saat entry dan exit. Angka ini mendekati rata-rata fee retail Indonesia 0.15% buy / 0.25% sell. Pakai `--cost-bps 0` hanya untuk membandingkan hasil gross tanpa biaya.

### Parameter Backtest yang Bisa Disesuaikan

| Parameter | Default | Keterangan |
|-----------|---------|-----------|
| `--take-profit` | 5.0% | Target setup |
| `--stop-loss` | 5.0% | Stop setup |
| `--max-hold` | 10 | Maks hari hold |
| `--max-positions` | 5 | Posisi concurrent maksimal |
| `--risk-pct` | 1.0% | Risk per trade |
| `--cost-bps` | 20.0 | Biaya transaksi one-way (bps); `0` untuk gross/no-cost |
| `--allow-regimes` | all | Filter: `BULLISH,SIDEWAYS` atau `SIDEWAYS` saja |

---

## 13. Quick Reference Card

```
┌──────────────────────────────────────────────────────────────────────┐
│  SWING FOREIGN ACCUMULATION — QUICK REFERENCE                        │
├──────────────────────────────────────────────────────────────────────┤
│  SETUP (sekali)                                                       │
│    saham fetch market --universe lq45                                       │
├──────────────────────────────────────────────────────────────────────┤
│  SETIAP HARI (15–20 menit)                                            │
│    saham fetch market --universe lq45            ← refresh data            │
│    saham analyze regime                            ← cek konteks pasar       │
│    saham screen accum --universe lq45 --multi ← scan universe        │
├──────────────────────────────────────────────────────────────────────┤
│  PER KANDIDAT (5 menit/saham)                                         │
│    saham analyze swing TICKER \                                       │
│      --setup foreign-bounce \                                        │
│      --capital 10000000 \                                             │
│      --with-regime                                                    │
├──────────────────────────────────────────────────────────────────────┤
│  FILTER SCREENER BERGUNA                                              │
│    --squeeze-only     BB Width ≤ 20th pctile (coiled spring)         │
│    --vwap-only        Asing masih underwater                         │
│    --min-foreign-flow-score 60 Hanya bukti foreign-flow tinggi         │
│    --multi            Tampilkan 7/30/90 sesi + pattern               │
│    --explain          Definisi skor + konteks run                     │
├──────────────────────────────────────────────────────────────────────┤
│  PRIORITAS ENTRY                                                      │
│    ✓ Gate: ENTER (6/6 gates pass)                                    │
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
│    saham trade log swing --ticker TICKER --entry-price XXXX --from-analysis │
│                    --with-regime                                      │
│    saham trade review swing --horizon 10                                    │
├──────────────────────────────────────────────────────────────────────┤
│  REGIME-ADAPTIVE TP/SL                                                  │
│    BULLISH: TP+8% / SL-4% (2:1 R:R)                                    │
│    SIDEWAYS: TP+5% / SL-5% (1:1 R:R) — default dalam setup            │
│    WEAK: TP+3% / SL-3%                                                  │
│    RISK_OFF: TP+3% / SL-3%                                              │
├──────────────────────────────────────────────────────────────────────┤
│  VALIDASI BERKALA (bulanan)                                           │
│    saham trade backtest-swing --universe lq45 --start 2025-01-01 --with-regime
│    saham analyze swing-compare --universe lq45 --start 2025-01-01            │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 14. Troubleshooting

### Screener Tidak Menampilkan Skor (Semua N/A atau 0)

```
! BBCA: No broker data — run 'saham fetch broker BBCA' first
```

```bash
saham fetch broker BBCA --days 90
```

Kalau sudah ada data tapi skor tetap 0, cek apakah data fresh:
```bash
saham view broker flow BBCA --days 7
```

### Skor Tinggi Tapi `WATCH` atau `AVOID`

Artinya satu gate spesifik gagal. Cek detail:
```bash
saham analyze swing TICKER --setup foreign-bounce
```

Lihat gate mana yang `✗ FAIL` dan alasannya:
- `vwap_disc < 3%` → asing sudah dekat breakeven, floor lebih lemah
- `trend ≠ SIDE` → harga sudah trending, bukan setup ideal lagi
- `rsi > 60` → overbought, risiko koreksi

### Pattern `long-term only` Tapi Skor Tinggi

Artinya akumulasi kuat di 90 sesi tapi melemah di 30 dan 7 sesi. Ini warning: asing mungkin sudah mulai distribusi perlahan. Cek `FLOW DETAIL` di output `saham analyze swing`, atau jalankan breakdown harian bila perlu:
```bash
saham view broker flow TICKER --days 30
```

Kalau trend berbalik (lebih banyak hari sell belakangan), skip.

### Backtest Profit Factor < 1.0

Strategi tidak profitable untuk periode/universe itu. Coba:
1. Filter regime: `--allow-regimes BULLISH,SIDEWAYS`
2. Perkecil universe: dari `idx80` ke `lq45`
3. Naikkan `--min-foreign-flow-score` di screener ke 60 atau 70

### `saham analyze regime` Menunjukkan RISK_OFF

Jangan entry swing baru. Fokus ke:
```bash
# Pantau regime setiap hari sampai membaik
saham analyze regime

# Kalau ada posisi terbuka, cek apakah masih valid
saham screen accum TICKER1 TICKER2 --multi
```

---

## Catatan Penting

- Strategi ini dirancang untuk holding 3–10 hari trading, bukan intraday
- Sinyal akumulasi adalah **leading indicator** — terkadang harga belum bergerak saat entry
- `sustained` pattern lebih reliable dari `fresh rotation` — tapi lebih lambat terdeteksi
- Paper trade minimal 20 setup menggunakan `saham trade log swing` + `saham trade review swing` sebelum sizing besar
- Data broker IDX (default) adalah data T+0 — akurat tapi mungkin 1 hari delay di beberapa ticker
- Gunakan `--provider stockbit` untuk `saham fetch broker` jika butuh data lebih granular per-broker (butuh auth)

---

*Untuk penjelasan konsep dasar (ATR, RSI, FVWAP), lihat [`how_to_intraday_trading.md`](how_to_intraday_trading.md).*
*Untuk data flow broker detail: `saham view broker --help` dan `saham fetch broker --help`.*
