# Panduan Intraday Trading dengan ai-saham
## Untuk Pemula — Lengkap dari Persiapan sampai Eksekusi

---

## Daftar Isi

1. [Apa itu Intraday Trading?](#1-apa-itu-intraday-trading)
2. [Jam Bursa IDX yang Wajib Kamu Tahu](#2-jam-bursa-idx-yang-wajib-kamu-tahu)
3. [Konsep Penting Sebelum Mulai](#3-konsep-penting-sebelum-mulai)
4. [Cara Kerja — Full Workflow](#4-cara-kerja--full-workflow)
5. [Memahami Setiap Indikator dan Sinyal](#5-memahami-setiap-indikator-dan-sinyal)
6. [Workflow Harian Step-by-Step](#6-workflow-harian-step-by-step)
7. [Membaca Output Pre-Open](#7-membaca-output-pre-open)
8. [Membaca Output Confirm-Open](#8-membaca-output-confirm-open)
9. [Kapan Harus Masuk, Kapan Harus Lewat](#9-kapan-harus-masuk-kapan-harus-lewat)
10. [Manajemen Risiko](#10-manajemen-risiko)
11. [Journal — Validasi Sebelum Uang Sungguhan](#11-journal--validasi-sebelum-uang-sungguhan)
12. [Backtest — Validasi Strategi pada Data Historis](#12-backtest--validasi-strategi-pada-data-historis)
13. [Stockbit Adapter — Setup dan Penggunaan](#13-stockbit-adapter--setup-dan-penggunaan)
14. [Kesalahan Umum Pemula](#14-kesalahan-umum-pemula)
15. [Glosarium](#15-glosarium)

---

## 1. Apa itu Intraday Trading?

Intraday trading berarti kamu membuka dan menutup posisi di **hari yang sama**. Tidak ada posisi yang dibawa bermalam. Keuntungan (dan kerugian) ditentukan sepenuhnya oleh pergerakan harga dalam satu sesi perdagangan.

**Mengapa orang memilih intraday?**
- Tidak terekspos risiko berita malam hari (laporan keuangan, geopolitik)
- Modal bisa diputar lebih cepat
- Tidak perlu menahan saham yang turun berhari-hari

**Mengapa intraday lebih sulit dari swing trading?**
- Waktu keputusan sangat sempit
- Biaya transaksi (komisi + pajak) memakan margin lebih besar secara proporsional — IDX tick-friction gate (Kep-00196/BEI/12-2024) memastikan target stop minimal 3 tick dan stop minimal 2 tick, karena round-trip cost 0.41–0.65%
- Psikologi lebih berat — harga bergerak setiap detik

**Tool ini membantu kamu dengan:** identifikasi kandidat sebelum pasar buka, menentukan entry range yang valid, dan di harga berapa keluar rugi. Tool ini **tidak** mengeksekusi order — kamu tetap yang memutuskan.

---

## 2. Jam Bursa IDX yang Wajib Kamu Tahu

```
08:45 – 08:56  PRE-OPEN (order bisa diubah)   ← collect-iev + pre-open + order plan
08:56 – 09:00  NON-CANCELLATION PERIOD        ← order TIDAK bisa diubah/dibatalkan
09:00          PASAR BUKA (call auction)
09:00 – 09:05  OPENING WINDOW                 ← confirm-open
09:00 – 11:30  SESI 1
11:30 – 13:30  ISTIRAHAT (Jumat: 11:30 – 14:00)
13:30 – 15:49  SESI 2
15:50 – 16:00  PRE-CLOSE AUCTION
16:00          HARGA PENUTUPAN RESMI
```

**Non-Cancellation Period (08:56–09:00):** Mulai Desember 2025, BEI menerapkan aturan bahwa order pre-open tidak bisa diubah/dibatalkan dalam 4 menit terakhir sebelum pasar buka (Kep-00003/BEI/04-2025). Ini mencegah manipulasi harga detik-akhir dan menyelaraskan IDX dengan praktik bursa global. Order baru bisa dimasukkan, tapi order yang sudah ada tidak bisa di-amend. Pastikan kamu sudah yakin dengan harga dan jumlah lot sebelum pukul 08:56.

### Mengapa Ada Dua Step?

Tool ini membagi keputusan menjadi dua fase:

**Phase 1 — Pre-open (08:45–09:00): `saham trade intraday pre-open`**
Identifikasi KANDIDAT berdasarkan IEV, ATR, RSI, ACCUM, dan FVWAP.
Output: entry range, suggested limit, ATR stop, dan sinyal arah per saham.
Kamu belum memutuskan masuk — kamu hanya menyiapkan daftar pantau.

**Phase 2 — Post-open (09:00–09:05): `saham trade intraday confirm-open`**
Setelah pasar buka dan opening price diketahui, kamu memasukkan harga pembukaan aktual. Tool memberikan keputusan deterministik: **ENTER / WAIT / SKIP** per saham, ditambah gate tambahan (tick-friction, regime gate). Ini yang membuat kamu tidak perlu menghitung ulang manual di saat paling kritis.

### Memahami Pre-Open Auction (08:45–09:00)

Selama 15 menit ini, investor memasukkan order beli/jual tapi **tidak ada matching**. Bursa mengumpulkan semua order. Pada tepat 09:00, sistem menemukan satu harga yang memaksimalkan volume yang bisa dieksekusi — inilah opening price.

**Implikasinya:**
- Bid yang kamu lihat pukul 08:52 belum tentu menjadi opening price
- Opening price bisa lebih tinggi ATAU lebih rendah dari bid manapun sebelum 09:00
- Strategi yang benar: siapkan kandidat + entry range dulu, putuskan setelah opening price diketahui

---

## 3. Konsep Penting Sebelum Mulai

### IEV — Intraday Expected Volume

IEV adalah estimasi volume (dalam lot) yang akan ditransaksikan saat opening, dihitung dari order-order yang masuk selama pre-open auction.

**Cara membacanya:**
- IEV tinggi = banyak pihak yang sudah antri order → saham ramai, likuid
- IEV rendah = sedikit minat → spread lebar, susah keluar kalau salah arah

```
BBCA  IEV: 450,000 lots  ← banyak order, likuid, kandidat intraday
ABCD  IEV:   8,000 lots  ← sepi, hindari untuk intraday
```

**Threshold default: IEV ≥ 100,000 lots.**

**Peringatan:** IEV tinggi tidak berarti harga pasti naik. Ia hanya mengatakan saham ini akan aktif — syarat *minimal* untuk intraday, bukan sinyal arah.

### IEV Intensity — Unusual Volume Detection (Baru)

Membandingkan IEV dengan volume harian rata-rata 20 hari terakhir:

```
IEV_Intensity = IEV / (ADV_20d / 78)
```

Dimana 78 = jumlah bar 5 menit dalam satu sesi IDX. Kalau IEV > 5× normal → ditandai sebagai **UNUSUAL_VOLUME**. Informasional, bukan gating — BEI Juli 2024 mengonfirmasi IEV lebih sulit dimanipulasi dari bid-offer.

### IEP — Indicative Equilibrium Price

Harga indikatif dari call auction. Beberapa movers dari Stockbit menyertakan IEP. Digunakan oleh `--iep-min` untuk menyaring penny stock (IEP < Rp 50). Data IEP juga dikumpulkan oleh `saham trade intraday collect-iev` untuk membangun dataset historis.

### Mengapa Liquidity Penting?

Kamu beli 10 lot lalu ternyata salah arah. Kalau bid-nya tipis, kamu terjebak di harga jauh lebih rendah dari yang kamu inginkan. IEV tinggi = banyak pembeli dan penjual aktif = kamu bisa keluar mendekati harga yang kamu mau.

### Speculative Symbol Filter (Baru)

IDX punya instrumen yang tidak cocok untuk strategi pre-open:
- **-W** (Warrant) — derivatif, aturan berbeda
- **-R** (Rights/HMETD) — sementara, bisa gap parah
- **-L** (Bond) — obligasi, tidak relevan

Saham dengan **history < 20 hari** (IPO baru) juga di-skip — ATR dan RSI-nya meaningless. Filter ini otomatis, tidak bisa dimatikan dari CLI (bisa dari config YAML).

---

## 4. Cara Kerja — Full Workflow

### Fase 0: Collect-IEV (Baru — 08:45)

```
INPUT: Stockbit browser session
       ↓
1. Fetch IEV movers dari Exodus API (semua board)
2. Simpan ke iev_snapshot_history dengan timestamp + flag NCP
3. Tampilkan ranking + IEP coverage
OUTPUT: Dataset IEV harian untuk backtest, ΔIEV cross-run
```

Jalankan tiap hari untuk membangun dataset historis. Setelah 3+ bulan, `saham trade intraday backtest` bisa filter by IEV rank.

### Fase 1: Pre-Open Screener

```
INPUT: Movers dari Stockbit (IEV data) + Order Book (opsional)
       ↓
0.  Speculative filter: skip -W/-R/-L + < 20 days history
1.  IEP floor: skip penny stocks (optional, via --iep-min)
2.  Filter IEV >= threshold — ambil top N (default 5)
3.  Per saham:
    a. ATR(14) dari data harian lokal
    b. RSI(14) dari data harian lokal
    c. IEV intensity: bandingkan IEV vs ADV_20d (UNUSUAL_VOLUME flag)
    d. Entry range: prev_close ± ATR% (bukan fixed 3%)
    e. ATR Stop: entry - 1×ATR, capped -7%
    f. Gap%: (bid - prev_close) / prev_close (jika order book tersedia)
    g. Spread%: (offer - bid) / bid × 100 (jika offer tersedia)
    h. ACCUM: cek 7 hari broker flow → BACKED/UNCONFIRMED/DISTRIBUTING
    i. FVWAP: Foreign VWAP vs current price → floor/sell risk
4.  Trend: RSI gate + gap% gate + ACCUM context
OUTPUT: Daftar kandidat dengan entry range, stop, spread%, sinyal arah
        + SPRD%, UNUSUAL_VOLUME, STRAT (opsional)
```

### Fase 2: Open Confirmation (setelah 09:00)

```
INPUT: Hasil pre-open + opening prices aktual dari Stockbit
       ↓
Per kandidat (berurutan):
1. Apakah opening price dalam entry range?             → SKIP_GAP_UP/DOWN
2. Apakah trend bukan BEARISH?                         → SKIP_BEARISH_CONTEXT
3. Apakah ACCUM bukan DISTRIBUTING?                    → SKIP_BEARISH_CONTEXT
4. Di regime WEAK/RISK_OFF: BACKED required?           → SKIP_BEARISH_CONTEXT
5. Di regime WEAK/RISK_OFF: entry band dipersempit 50%
6. Apakah ATR stop tidak lebih dari 7% dari opening?   → SKIP_RISK_TOO_WIDE
7. Tick-friction: stop >= 2 tick, target >= 3 tick?    → SKIP_LOW_VOLATILITY  (Baru)
8. BULLISH = ENTER, NEUTRAL lainnya = WAIT
OUTPUT: Keputusan deterministik per saham dengan alasan
```

**Mengapa prev_close sebagai acuan, bukan bid?**

Karena pre-open bid berubah terus dan tidak mencerminkan clearing price. Prev_close adalah harga terakhir yang disepakati pasar — referensi stabil dan objektif.

---

## 5. Memahami Setiap Indikator dan Sinyal

### 5.1 ATR — Average True Range

**Apa itu:** ATR mengukur seberapa jauh rata-rata harga bergerak per hari. Dihitung dari 14 hari terakhir.

```
True Range = max(High-Low, |High-PrevClose|, |Low-PrevClose|)
ATR(14)    = rata-rata bergerak dari 14 True Range terakhir
```

**Dua kegunaan ATR dalam tool ini:**

**1. Untuk stop-loss:**
```
Stop = entry - (1.0 × ATR), tidak lebih dari -7% entry

BBCA entry 9,050 | ATR 150 → stop = 8,900 (-1.7%)  ✓
GOTO entry   240 | ATR   8 → stop = 232   (-3.3%)  ✓
```

**2. Untuk entry range (ATR-scaled):**
```
Entry Range = prev_close ± (ATR / prev_close), capped [1%, 5%]

BBCA prev_close 5,000 | ATR 280 → band = 5.6% → capped 5%
  → Entry Range: 4,750 – 5,250

GOTO prev_close   235 | ATR   8 → band = 3.4% → tidak di-cap
  → Entry Range: 227 – 243
```

**Mengapa ATR-scaled lebih baik dari fixed ±3%:**
- BBCA dengan ATR 5.6% dari harga: ±3% terlalu sempit, banyak false rejection
- Saham berbeda punya karakter volatilitas berbeda
- ATR mencerminkan volatilitas *aktual* saham tersebut, bukan asumsi generik

**Yang perlu diwaspadai:**
- ATR dari data HARIAN — masih kasar untuk intraday, tapi jauh lebih baik dari stop tetap
- Setelah corporate action (split, rights issue), ATR lama tidak relevan
- ATR sangat kecil (< 1% harga) → saham sedang konsolidasi ketat, bisa breakout besar

---

### 5.2 RSI — Relative Strength Index

**Apa itu:** RSI mengukur kecepatan dan besarnya perubahan harga dalam 14 hari terakhir. Nilai 0–100.

```
RSI > 75   : OVERBOUGHT → tool tandai BEARISH, skip long
RSI 65–75  : Panas, waspada
RSI 30–65  : Zona ideal untuk long intraday
RSI < 30   : OVERSOLD → potensi rebound, tapi bisa terus turun
```

**Bagaimana digunakan:**
- RSI > 75 = gate BEARISH — kandidat di-skip untuk long
- RSI 30–65 + gap kecil = sinyal BULLISH
- Di fast mode (tanpa order book), RSI + SMA digunakan sebagai fallback classifier

**Peringatan penting:**
- RSI dari data 14 hari terakhir — memberikan *konteks tren*, bukan sinyal masuk
- RSI 40 ≠ "pasti naik hari ini" — hanya berarti ruang naik lebih terbuka dibanding RSI 80
- Saham RSI sangat rendah (< 25) bisa dalam downtrend kuat — jangan FOMO beli

---

### 5.3 Gap% — Kesenjangan Harga Pre-Open

**Apa itu:** Selisih antara harga pre-open bid dan harga penutupan kemarin.

```
Gap% = (bid_pre_open - prev_close) / prev_close × 100
```

Hanya tersedia kalau kamu menyediakan data order book (`--order-books-json`). Di `--fast` mode, Gap% ditampilkan sebagai `—`.

**Cara membaca:**
```
Gap% = +0.5%  → normal, dalam ATR band → aman
Gap% = +2.5%  → mungkin masih dalam band BBCA (ATR ~5%), tergantung saham
Gap% = +4.2%  → keluar band → tool tandai BEARISH, warning ditampilkan
Gap% = -3.0%  → gap down signifikan → BEARISH
```

**Kunci:** batas BEARISH bukan lagi fixed ±3% — sekarang menggunakan ATR band per saham. TLKM dengan ATR 5% tidak di-flag BEARISH pada gap +3.2%, tapi BBRI dengan ATR 2% akan di-flag.

### 5.3b SPRD% — Bid/Offer Spread (Baru)

Selisih antara best offer dan best bid sebagai persentase dari bid.

```
SPRD% = (offer - bid) / bid × 100
```

Hanya tersedia kalau order book menyertakan offer side. Sekarang `fetch-top5` dan `pre-open` otomatis menyertakan offer side (tidak didiskard seperti sebelumnya).

**Cara membaca:**
```
SPRD% 0.4%  → spread sempit, likuiditas tinggi — ideal
SPRD% 0.9%  → spread normal untuk saham mid-cap
SPRD% > 3%  → spread lebar, likuiditas rendah — waspada
```

Spread membantumu menilai biaya implisit masuk/keluar. Semakin lebar spread, semakin banyak harga yang kamu "berikan" ke market maker.

---

### 5.4 Entry Range — Rentang Harga Masuk

**Apa itu:** Range harga opening yang dianggap "normal" dan aman untuk masuk long.

```
Entry Range = [prev_close × (1 - band), prev_close × (1 + band)]
Band = ATR / prev_close, capped antara 1% dan 5%
```

**Cara menggunakannya (setelah 09:00):**
```
Kalau opening price DALAM entry range  → masuk konfirmasi Fase 2
Kalau opening price DI ATAS range high → SKIP_GAP_UP (terlalu mahal)
Kalau opening price DI BAWAH range low → SKIP_GAP_DOWN (ada masalah)
```

Di regime **WEAK/RISK_OFF**, entry range dipersempit 50% oleh regime gate. Lihat §5.10.

---

### 5.5 Suggested Entry — Harga Limit Order

```
Suggested Entry = prev_close × 1.005  (0.5% di atas close kemarin)
```

Ini titik awal untuk limit order, bukan harga pasti. Kamu pasang setelah opening price diketahui dan masuk dalam entry range. Adjust berdasarkan posisi opening price.

---

### 5.6 ATR Stop — Harga Stop-Loss

```
ATR Stop = entry - (1.0 × ATR14), tidak lebih dari -7%
```

Pasang segera setelah order beli terisi. Jangan digeser ke bawah.

---

### 5.7 ACCUM — Akumulasi Smart Money

**Apa itu:** Ringkasan aktivitas beli/jual asing selama 7 hari terakhir.

Tool menganalisis data broker flow (dari IDX atau Stockbit) dan memberikan tag:

| Tag | Artinya | Aksi |
|-----|---------|------|
| **BACKED** (score ≥ 50) | Asing net-beli konsisten 7 hari → smart money positioning | Konviksi tinggi untuk long |
| **UNCONFIRMED** | IEV spike tapi tidak ada pola akumulasi yang jelas | Konviksi sedang, ukuran lebih kecil |
| **DISTRIBUTING** | Asing net-jual konsisten → IEV mungkin driven retail | Tool akan SKIP_BEARISH_CONTEXT di Fase 2 |

**Score (0–70 pts):**
```
Consistency: net_buy_days / total_days × 40 pts  (berapa hari asing beli)
Streak:      30 × (1 - e^(-streak/7))            (berapa hari beruntun beli)
```

**Contoh:**
```
BMRI ACCUM: BACKED 65pts streak:5d
→ Asing beli 5 hari beruntun, konviksi tinggi

GOTO ACCUM: DISTRIBUTING 0pts
→ Asing net-jual, skip untuk long meskipun IEV tinggi
```

**Mengapa penting:**
IEV tinggi bisa karena *institusi yang lanjutkan posisi* atau *retail yang chase breakout*. ACCUM membedakan keduanya. Konfluensi IEV + BACKED → probabilitas lebih tinggi.

**Catatan:** Membutuhkan data broker flow di database lokal. Jalankan `saham data update --universe lq45` dulu.

---

### 5.8 FVWAP — Foreign VWAP Discount

**Apa itu:** Selisih antara harga rata-rata beli asing (volume-weighted, 20 hari) dan harga saat ini.

```
FVWAP = Σ(foreign_buy_value) / (Σ(foreign_buy_lots) × 100)
FVWAP% = (FVWAP - current_price) / current_price × 100
```

**Cara membaca:**
```
FVWAP% = +3.2%  (hijau: "floor")
→ Asing rata-rata beli di harga +3.2% di atas harga sekarang
→ Mereka rugi saat ini → incentif kuat untuk DEFEND posisi (tidak jual)
→ Ada "lantai" di bawah harga sekarang = bullish untuk long

FVWAP% = -5.8%  (merah: "sell risk")
→ Asing rata-rata beli di harga -5.8% dari sekarang
→ Mereka untung → mungkin JUAL di opening untuk lock profit
→ Ada tekanan jual potensial = waspada untuk long

FVWAP% = -0.5%  (netral)
→ Asing hampir impas → tidak ada incentif kuat ke salah satu arah
```

**Mengapa relevan untuk intraday:**
Kalau FVWAP positif (asing underwater), saham punya "price floor" alami karena institusi cenderung defend atau average down. Ini meningkatkan probabilitas upside jangka pendek.

**Contoh konfluensi ideal:**
```
BBCA: BACKED 72pts streak:5d | FVWAP: +3.2% (floor)
→ Asing akumulasi + masih underwater = sangat menarik untuk long
```

**Catatan:** Membutuhkan data broker flow. Jika tidak ada data, ditampilkan sebagai tidak ada baris FVWAP.

---

### 5.9 Prev High / Prev Low — S/R Kemarin

**Apa itu:** Harga tertinggi (H) dan terendah (L) dari hari kemarin.

```
Prev H → resistance — sering menjadi target pertama
Prev L → support   — kalau breach di sini, ada masalah
```

Gunakan sebagai:
- **Target**: entry di 4,290, Prev H 4,260 di bawah → sudah melewati resistance, lebih bersih
- **Warning**: entry di 4,290, Prev L 4,050 di bawah → stop di 4,148, masih di atas Prev L → oke

---

### 5.10 Decisions dari Confirm-Open

Setelah kamu masukkan opening prices aktual, tool menjalankan gate berurutan:

| Decision | Artinya | Gate yang Dilanggar |
|----------|---------|-------------------|
| `ENTER` | Semua gate pass + BULLISH → masuk dengan limit di Suggested Entry | — |
| `WAIT` | Range pass tapi NEUTRAL trend → pantau dulu | Trend gate |
| `SKIP_GAP_UP` | Opening di atas entry range → terlambat | Range gate |
| `SKIP_GAP_DOWN` | Opening di bawah entry range → ada sentimen negatif | Range gate |
| `SKIP_BEARISH_CONTEXT` | Trend BEARISH / ACCUM DISTRIBUTING / di WEAK regime tanpa BACKED | Trend/ACCUM/Regime gate |
| `SKIP_RISK_TOO_WIDE` | ATR stop > 7% dari opening → risiko terlalu besar | Risk gate |
| `SKIP_LOW_VOLATILITY` | Tick-friction: target < 3 tick atau stop < 2 tick (Kep-00196/BEI/12-2024) | Tick-friction gate (Baru) |

#### Regime-Tightened Gate (Baru)

Saat market regime adalah **WEAK** atau **RISK_OFF**:
1. Entry range (`max_gap_pct`) dipersempit 50%
2. Hanya kandidat dengan ACCUM `BACKED` yang lanjut — UNCONFIRMED/DISTRIBUTING = SKIP
3. Informasi "regime WEAK: entry band tightened to X–Y" di output

Ini melindungi dari BBCA/BBRI/BMRI/BBNI anchor effect — saat IHSG turun tajam, bid second-liner menguap.

#### Tick-Friction Gate (Baru — Kep-00196/BEI/12-2024)

IDX punya tick size minimum per tier harga. Kalau implied 1:1 target < 3 tick atau stop < 2 tick, biaya transaksi (0.41–0.65%) bisa makan seluruh profit. Gate ini mencegah kamu trading pada ticker yang terlalu sempit pergerakannya.

| Harga | Tick | Contoh (entry 5,000, stop 4,904) |
|-------|------|----------------------------------|
| < Rp 200 | Rp 1 | stop = 9,600 tick → aman |
| Rp 200 – < Rp 500 | Rp 2 | stop = 48 tick → aman |
| Rp 500 – < Rp 2.000 | Rp 5 | stop = 19 tick → aman |
| Rp 2.000 – < Rp 5.000 | Rp 10 | stop = 9 tick → aman |
| ≥ Rp 5.000 | Rp 25 | stop = 3 tick → aman (target 3 tick) |

Gate default aktif. Bisa dimatikan di `config/pre_open_screener.yaml` → `risk.tick_friction_gate: false`.

---

## 6. Workflow Harian Step-by-Step

### Malam Sebelumnya (10 menit, opsional tapi direkomendasikan)

```bash
saham data update --universe lq45
```

Refresh data harga + broker flow. Kalau cache belum mencapai tanggal hari ini, `saham data update` mencoba mengisi gap ke provider. `cached-current` berarti cache sudah sampai hari ini; `provider-no-new-data(latest=YYYY-MM-DD)` berarti provider sudah dicek tetapi belum punya data trading lebih baru.

---

### Setup Satu Kali — Login Stockbit (kalau belum pernah atau sesi expired)

```bash
saham data stockbit login
```

Sesi tersimpan di `.stockbit_profile/`. Tidak perlu diulang setiap hari kecuali expired.

---

### 08:45 — Capture IEV Snapshot (Baru — Bangun Dataset Historis)

```bash
saham trade intraday collect-iev
```

Mengambil ranking IEV dari Stockbit dan menyimpannya ke database. Data ini dipakai oleh `saham trade intraday backtest` untuk simulasi yang mirip live (filter top-N IEV).

Informasi yang ditampilkan:
- Ranking IEV + IEP coverage
- ΔIEV jika sudah ada snapshot sebelumnya hari ini
- Badge `[NCP LOCKED]` / `[PRE-NCP]` berdasarkan jam koleksi
- Ringkasan coverage database (berapa hari, IEP fill rate)

---

### 08:47–08:55 — Jalankan Pre-Open Screener

Ada beberapa cara, pilih yang sesuai situasi:

---

#### Cara 1 — Autonomous (Direkomendasikan)

Satu perintah, tidak perlu buka browser manual:

```bash
saham trade intraday pre-open --top 5
```

Tool otomatis fetch IEV movers + orderbook dari Stockbit, lalu tampilkan hasil screening. Butuh `.stockbit_profile/` valid (lihat login di atas).

Dengan regime context:
```bash
saham trade intraday pre-open --top 5 --with-regime
```

Dengan kolom STRAT (sinyal strategi):
```bash
saham trade intraday pre-open --top 5 --signal-strategy williams-r-bounce
```

Dengan filter penny stock (pakai data IEP dari collect-iev):
```bash
saham trade intraday pre-open --top 5 --iep-min 50
```

---

#### Cara 2 — Fetch Data Dulu, Screener Terpisah

Berguna kalau mau lihat raw data IEV + orderbook sebelum diproses:

```bash
# Langkah 1: ambil top 5 IEV + orderbook
saham data stockbit fetch-top5

# Contoh output:
#   1  BUMI   972,420   bid=156 (409K lots)   offer=157 (303K lots)
#   2  BBRI   373,423   bid=2,850 (219K lots)  offer=2,860 (2.7K lots)
#   ...

# Langkah 2: jalankan screener dengan data yang sudah terlihat
saham trade intraday pre-open \
  --movers-json '[{"ticker":"BUMI","iev":972420},{"ticker":"BBRI","iev":373423}]' \
  --order-books-json '{"BUMI":{"price":156,"volume":409437},"BBRI":{"price":2850,"volume":219024}}'
```

---

#### Cara 3 — Fast Mode (Input Manual, Tanpa Orderbook)

```bash
saham trade intraday pre-open \
  --movers-json '[{"ticker":"BBCA","iev":450000},{"ticker":"BMRI","iev":320000}]' \
  --fast
```

Data IEV diambil manual dari Stockbit web (Movers → IEP/IEV tab). Fast mode tidak membutuhkan data orderbook (~15 detik total).

---

#### Override Threshold

```bash
saham trade intraday pre-open --top 3 --max-gap 0.05 --atr-mult 1.5
```

Catat output: entry range, ATR stop, dan sinyal ACCUM/FVWAP per saham.

Policy default disimpan di `config/pre_open_screener.yaml`. Ini adalah konfigurasi screener intraday, bukan strategy package untuk `saham strategy backtest --strategy`. Untuk eksperimen threshold yang reproducible:

```bash
saham trade intraday pre-open --config config/pre_open_screener.yaml --top 3
```

Untuk menambahkan konteks market regime deterministik:

```bash
saham trade intraday pre-open --top 5 --with-regime
```

Default-nya memakai `--regime-universe idx80` dan `--benchmark ^JKSE`. Regime tidak mengubah verdict diam-diam — ia memberi warning agar konfirmasi lebih ketat atau size dikurangi. Di regime `WEAK`/`RISK_OFF`, entry band dipersempit 50% dan hanya BACKED yang lanjut (lihat config `regime_gate.*`).

#### Dry-Run di Weekend / Non-Trading Day

Secara default, tool menolak `pre-open` di weekend agar journal tidak terisi sesi palsu. Untuk latihan atau backfill, pakai override eksplisit:

```bash
saham trade intraday pre-open \
  --movers-json '[{"ticker":"BBCA","iev":450000}]' \
  --fast \
  --allow-non-trading-day
```

Output akan menampilkan baris `DATA` berisi `Analysis date`, `Candles through`, dan `Broker flow through`. Kalau tanggal data tertinggal dari tanggal analisis, anggap hasil sebagai dry-run, bukan sinyal live.

---

### 09:00–09:05 — Konfirmasi Setelah Pasar Buka

Setelah pasar buka, lihat opening price aktual di Stockbit untuk setiap kandidat. Masukkan ke tool:

```bash
saham trade intraday confirm-open \
  --opening-json '{"BBCA":5175,"BMRI":4290,"TLKM":2820}'
```

Tool langsung output dengan gate regime + tick-friction (lihat §8 untuk contoh lengkap).

**Ini momen paling penting.** Ikuti keputusan tool:
- `ENTER` → pasang limit di Suggested Entry, set stop di ATR Stop
- `WAIT` → pantau 15 menit, masuk kalau arah mulai jelas ke atas
- `SKIP_*` → lewati saham ini hari ini, tanpa pengecualian

---

### Setelah Trading — Catat di Journal

```bash
# Log hasil pre-open screening
saham trade intraday pre-open-log

# Log hasil confirmation (lebih detail, termasuk keputusan)
saham trade intraday log
```

`saham trade intraday log` adalah alias dari `saham trade intraday confirm-log`.

---

### Catat Hasil Aktual (setelah posisi ditutup)

```bash
saham trade intraday outcome BBCA \
  --entry 5200 \
  --exit 5375 \
  --notes "keluar jam 10:30, target tercapai di Prev H"
```

---

### Evaluasi Berkala (setiap 20+ sesi)

```bash
# Evaluasi accuracy entry range
saham trade intraday pre-open-review --horizon 5

# Evaluasi accuracy keputusan confirm-open
saham trade intraday review
```

`saham trade intraday review` adalah alias dari `saham trade intraday confirm-review`. Jika manual outcome belum dicatat, review memakai daily OHLC lokal sebagai proxy; urutan stop/target intraday yang persis membutuhkan data menit/tick dan belum dimodelkan.

---

## 7. Membaca Output Pre-Open

Output pre-open menggunakan layout **VERDICT-first** — satu baris per ticker, diurutkan dari setup terkuat ke terlemah.

```
PRE-OPEN SCREENER RESULTS
Date: 2026-06-17   IEV filter: >= 100,000
Movers evaluated: 16   Candidates: 5

DATA: Analysis date 2026-06-17   Candles through 2026-06-16   Broker flow through 2026-06-16

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
   saham trade intraday confirm-open \
     --opening-json '{"BNBR":___,"BUMI":___}'
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Cara membaca VERDICT:**

| VERDICT | Artinya | Aksi |
|---------|---------|------|
| `★ PRIME` | BULLISH + BACKED + FVWAP floor + range valid | Watchlist prioritas |
| `◉ WATCH` | Bullish tapi belum semua sinyal hijau | Watchlist, konfirmasi di 09:00 |
| `✗ SKIP` | BEARISH atau DISTRIBUTING atau gap di luar range | Tidak masuk |
| `? NO_DATA` | Tidak ada data ATR lokal | `saham data update TICKER --days 365` malam ini |

**Penjelasan kolom:**

| Kolom | Penjelasan |
|-------|-----------|
| `VERDICT` | Sinyal sintesis — baca kolom ini saja untuk keputusan utama |
| `IEV` | Volume expected. Makin tinggi = makin likuid |
| `GAP%` | Selisih pre-open bid vs kemarin. `—` = fast mode |
| `SPRD%` | Bid/offer spread (hanya muncul kalau data offer tersedia) |
| `ENTRY-RANGE` | ATR-scaled band. Dikonfirmasi oleh confirm-open di 09:00 |
| `STOP%` | % rugi kalau stop kena (ATR-based, capped -7%) |
| `RSI` | Momentum. > 75 = overbought |
| `SIGNAL` | ACCUM tag × streak + FVWAP% + PH (Prev High target) + IEV_INTENSITY flag |

**Warning baru:**
- `UNUSUAL_VOLUME` — IEV > 5× rata-rata volume 5-menit (informasional, bukan gating)
- WARNING speculative symbol atau < 20 days history (tidak jadi candidate)

---

## 8. Membaca Output Confirm-Open

Setelah kamu jalankan `saham trade intraday confirm-open`, output dikelompokkan per aksi:

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
 saham trade intraday log   (record this session)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Apa yang kamu lakukan:**

- **▶ ENTER**: Buka broker, pasang limit buy di harga yang tertera, set stop segera setelah terisi.
- **◎ WAIT**: Pantau 15 menit. Entry hanya kalau harga holds above range_low dengan volume. Skip kalau tidak ada gerakan.
- **✗ SKIP**: Tidak masuk — alasan ditampilkan per ticker. Tidak ada pengecualian.

**Penting:** Harga limit buy dan stop sudah dihitung otomatis. Kamu tidak perlu kalkulasi manual.

### Gate Baru di Confirm-Open

**SKIP_LOW_VOLATILITY (tick-friction gate):**
```
BBRI    tick-friction: stop=1t target=2t (min stop=2t target=3t)
```
Terjadi kalau rentang entry ke stop atau target terlalu sempit < batas tick size. Biaya round-trip IDX 0.41–0.65% bisa makan seluruh profit. Aman dilewati.

**Regime-gate tightening:**
```
BBRI    regime WEAK: BACKED accumulation required (got DISTRIBUTING)
```
Di regime WEAK/RISK_OFF, entry band dipersempit 50% dan BACKED required. Informasi band tightening ditampilkan sebagai alasan range adjustment.

---

## 9. Kapan Harus Masuk, Kapan Harus Lewat

### Checklist Sebelum Masuk (semua harus terpenuhi)

```
□ confirm-open output: ▶ ENTER atau ◎ WAIT
□ Stop-loss sudah tertera di confirm-open output — catat sebelum pasang order
□ Modal per trade tidak lebih dari 10% total modal kamu
□ Tidak ada berita besar yang belum kamu baca
□ (Di regime WEAK): hanya trade kalau benar-benar yakin — size lebih kecil
□ (Tick-friction): pastikan stop >= 2 tick dan target >= 3 tick (otomatis ditangani)
```

### Langsung Lewati Kalau:

- `✗ SKIP` (alasan apapun, termasuk SKIP_LOW_VOLATILITY) — tidak ada pengecualian
- `◎ WAIT` + tidak ada konfirmasi naik dalam 15 menit → skip

### Situasi Khusus

**Hari Senin dan setelah libur panjang:**
Gap lebih sering terjadi karena akumulasi berita selama libur. Pertimbangkan `--max-gap 0.05` (5%) atau skip lebih banyak.

**BBCA FVWAP -5.8% (sell risk) meski BACKED:**
Asing mungkin ambil profit di opening. Konfirmasi WAIT dulu, masuk kalau harga tidak langsung turun setelah 5 menit.

**30 menit pertama (09:00–09:30):**
Volume tinggi tapi harga belum stabil. Pemula lebih aman tunggu sampai 09:30 untuk entry WAIT.

**Saham kena SKIP_SPECULATIVE (warrant/rights/bond):**
Jangan trading instrumen ini dengan strategi pre-open. Mereka punya mekanisme harga yang berbeda.

---

## 10. Manajemen Risiko

### Aturan Dasar

**1. Maksimal loss per trade: 2% total modal**
```
Total modal: Rp 10,000,000
Maksimal loss: Rp 200,000

BBCA: entry 5,200, stop 4,904, risk = 296 poin/saham
Max lot = 200,000 / (296 × 100) = 6.7 → ambil 6 lot
Check: 6 × 100 × 5,200 = Rp 3,120,000 modal terpakai ✓
```

**2. Jangan lebih dari 2 ENTER sekaligus**
Kalau BBCA dan BBRI keduanya ENTER, fokus pada 1 dulu. Dua posisi simultaan butuh monitoring ganda di saat market paling volatile.

**3. Stop-loss tidak boleh digeser ke bawah**
Pernah geser stop? Itu adalah awal dari kekalahan besar.

**4. Ambil profit sebagian di Prev High**
Jual 50% posisi di Prev High, sisanya biarkan jalan. Kalau tembus Prev High, trailing stop.

**5. Waspada jeda istirahat 11:30–13:30**
Posisi yang masuk di 30 menit pertama akan memasuki jeda 2 jam saat bursa istirahat. Selama jeda, stop-loss di JATS tetap aktif, tapi jika ada berita besar saat istirahat, harga bisa gap melampaui stop saat sesi 2 dibuka. Solusi: kurangi ukuran posisi untuk trade pagi, atau ambil profit sebelum istirahat kalau sudah cukup.

**6. Tick-friction gate melindungi dari biaya transaksi**
Kalau stop < 2 tick atau target < 3 tick, SKIP_LOW_VOLATILITY. Ini bukan error — ini melindungi kamu dari trade yang biayanya > potensi profit.

### Position Sizing dari Tool

```
Dari confirm-open output:
  BBCA: entry 5,200 | stop 4,904 | risk = 296 poin

Maksimal loss kamu: Rp 200,000
Max saham: 200,000 / 296 = 675 saham = 6 lot
Nilai posisi: 6 × 100 × 5,200 = Rp 3,120,000
```

---

## 11. Journal — Validasi Sebelum Uang Sungguhan

### Mengapa Journal?

Sebelum kamu tahu apakah screener ini bekerja untuk kondisi pasar saat ini, paper trade dulu. Setelah 20–30 sesi kamu punya data:
- Berapa % entry range akurat?
- Keputusan ENTER yang benar berapa %?
- FVWAP floor signal memprediksi apa?
- Apakah regime gate menyelamatkan dari loss?

### Alur Journal

```bash
# Setelah pre-open run:
saham trade intraday pre-open-log

# Setelah confirm-open run:
saham trade intraday log

# Setelah posisi ditutup (masukkan outcome aktual):
saham trade intraday outcome BBCA --entry 5200 --exit 5375 --notes "target tercapai"

# Evaluasi setelah 20+ sesi:
saham trade intraday pre-open-review --horizon 1    # akurasi range 1 hari
saham trade intraday review                          # akurasi keputusan confirm-open
```

### Membaca `saham trade intraday review`

```
DECISION BREAKDOWN:
  ENTER      : 45 total, 28 win (62.2%) ← ini yang paling penting
  WAIT       : 18 total, 10 win (55.6%)
  SKIP_*     : 24 total (tidak dieksekusi — tidak ada data win/loss)

CONTEXT BREAKDOWN (untuk ENTER):
  ACCUM=BACKED    : 28 entries, 20 win (71.4%)  ← lebih baik
  ACCUM=UNCONFIRMED: 12 entries,  7 win (58.3%)
  FVWAP positive  : 22 entries, 16 win (72.7%)  ← floor signal works
  FVWAP negative  :  6 entries,  3 win (50.0%)
```

Dari breakdown ini kamu tahu: BACKED + FVWAP floor meningkatkan win rate. Data ini memvalidasi bahwa sinyal-sinyal tersebut memang berguna, bukan hanya noise.

---

## 12. Backtest — Validasi Strategi pada Data Historis

### Review vs Backtest — Apa Bedanya?

| Aspek | `saham trade intraday review` | `saham trade intraday backtest` |
|-------|-------------------------|---------------------------|
| **Sumber data** | Journal sesi nyata yang sudah kamu log | Data harian historis di `data.db` |
| **Periode** | Hanya hari-hari yang sudah kamu jalankan live | Periode bebas yang kamu pilih |
| **Butuh journaling dulu?** | Ya — min. 20 sesi | Tidak — langsung pakai data historis |
| **Kapan dipakai** | Setelah paper trade berjalan | Sebelum mulai paper trade, validasi awal |

Singkatnya: **backtest melihat ke belakang sejauh data kamu**, sedangkan **review hanya tahu sesi-sesi yang sudah kamu log**. Backtest cocok untuk menjawab: "kalau workflow ini dijalankan setiap hari selama 6 bulan terakhir, hasilnya seperti apa?"

### Cara Kerja `saham trade intraday backtest` (Option A — Daily OHLC Proxy)

Backtest ini menggunakan candle harian (open/high/low/close) sebagai pengganti data tick intraday:

```
Untuk setiap tanggal d di [start, end]:
  1. Hitung sinyal pre-open menggunakan data sampai d-1
     (ATR, RSI, SMA, ACCUM, FVWAP, entry range, ATR stop, tick-friction gate)
  2. Opening price = candle.open di tanggal d
     (di IDX, candle open ADALAH harga clearing call auction 09:00)
  3. Jalankan confirm-open decision tree (ENTER / WAIT / SKIP_*)
  4. Untuk setiap ENTER:
     - Entry di candle.open
     - Cek candle.low ≤ stop → exit di stop ("stop")
     - Cek candle.high ≥ target (prev_high) → exit di target ("target")
     - Kedua-duanya kena → asumsi stop duluan, konservatif ("both_assume_stop")
     - Tidak ada yang kena → exit di candle.close ("close")
  5. Semua posisi ditutup hari yang sama — tidak ada overnight
```

### IEV Snapshot — Backtest Lebih Akurat (Baru)

Dulu backtest menjalankan screener pada **seluruh** universe karena IEV tidak tersimpan. Sekarang, kalau kamu rutin menjalankan `saham trade intraday collect-iev`:

```bash
saham trade intraday backtest --universe lq45 --iev-top-n 5 --start 2026-01-01
```

Backtest hanya akan memproses top 5 ticker berdasarkan IEV asli hari itu (data dari iev_snapshot_history). Hari tanpa snapshot → warning + full universe.

### Parameter Lengkap

| Parameter | Default | Penjelasan |
|-----------|---------|-----------|
| `--universe` / arg ticker | — | `lq45` / `idx80` / `idxcomp100` / `cached`, atau daftar ticker eksplisit |
| `--start` / `--end` | start=2026-01-01, end=hari ini | Rentang tanggal backtest |
| `--capital` | 100,000,000 | Modal awal dalam IDR |
| `--risk-pct` | 1.0 | % modal yang di-risk per trade |
| `--max-daily-positions` | 3 | Max trade per hari |
| `--max-stop` | 0.07 | Max stop distance (7%) |
| `--cost-bps` | 20 | Biaya per side dalam bps (20 = 0.20%) |
| `--include-wait` | False | Anggap WAIT sebagai ENTER |
| `--atr-mult` | 1.0 | Multiplier ATR untuk stop |
| `--iev-top-n` | None | Filter top N IEV (butuh data collect-iev) |
| `--show-trades` | 20 | Berapa trade terakhir di-print |
| `--format` | table | `table` atau `json` |

### Membaca Output

Output terdiri dari tiga blok utama:

1. **Metric summary** — equity, return, drawdown, win rate, profit factor:
   - **Expectancy %** = win% × avg_winner − loss% × |avg_loser| → positif = ada edge setelah biaya
   - **Avg R-multiple** = rata-rata pnl / risk awal → target ≥ +0.2R agar strategi layak
   - **both_assume_stop rate** — kalau > 15% dari trade, daily OHLC proxy terlalu kasar

2. **Exit reason mix** — `target / stop / close / both_assume_stop`

3. **Breakdown by ACCUM / FVWAP / RSI / ticker** — validasi empiris klaim sinyal:
   - Idealnya BACKED win rate > UNCONFIRMED > DISTRIBUTING
   - FVWAP positif (floor signal) seharusnya outperform FVWAP negatif

### Kapan Hasil Backtest Tidak Bisa Dipercaya

- Periode < 1 bulan (statistik tidak meaningful — butuh min. 30 trade)
- Universe < 5 saham (terlalu sedikit kandidat)
- `both_assume_stop` > 15% dari total trade
- Tidak ada data broker untuk periode → ACCUM/FVWAP selalu `None`

### Rekomendasi Workflow Validasi

```
1. saham trade intraday backtest --universe lq45 --start 2025-12-01
   → lihat apakah ada edge historis

2. Paper trade 20+ sesi (saham trade intraday log + outcome)

3. saham trade intraday review
   → bandingkan hasil paper dengan ekspektasi backtest

4. Kalau aligned → naikkan modal secara bertahap
```

> Backtest bukan jaminan masa depan — ia indikator bahwa workflow punya edge historis. Pasar berubah; selalu validasi dengan paper trade sebelum modal nyata.

---

## 13. Stockbit Adapter — Setup dan Penggunaan

Adapter Stockbit menggunakan Playwright untuk mengakses Exodus API (API internal Stockbit) secara langsung. **Semua mode sudah diverifikasi bekerja** — tidak ada kalibrasi manual yang dibutuhkan.

---

### Setup Satu Kali — Login Stockbit

```bash
saham data stockbit login
```

Ini membuka browser Chrome. Login manual seperti biasa (termasuk 2FA kalau ada). Setelah berhasil, sesi tersimpan di `.stockbit_profile/` dan **tidak perlu login ulang** selama sesi masih valid.

```bash
saham data stockbit status    # Cek apakah sesi masih valid
```

Output contoh:
```
  Type   : persistent browser profile (recommended)
  Saved  : 2.5h ago
  Status : likely valid
```

Sesi expired otomatis dalam 8–12 jam. `pre-open` akan cepat-fail tanpa membuka browser kalau sesi expired (> 8 jam).

---

### Perintah Stockbit

| Perintah | Fungsi |
|----------|--------|
| `saham data stockbit login` | Login manual (satu kali, atau kalau sesi expired) |
| `saham data stockbit status` | Cek kesehatan sesi tanpa buka browser |
| `saham data stockbit fetch-top5` | Ambil top-N IEV + orderbook dalam satu sesi browser (sekarang termasuk offer side) |
| `saham data stockbit test` | Smoke test: verifikasi movers + orderbook bekerja |
| `saham data stockbit spy` | Capture semua API traffic (debugging endpoint, bukan prasyarat harian) |
| `saham data stockbit browse` | Buka browser dengan sesi tersimpan (tidak auto-close) |

### Perintah Intraday Lengkap

| Perintah | Fungsi |
|----------|--------|
| `saham trade intraday collect-iev` | Capture IEV snapshot ke database historis |
| `saham trade intraday pre-open` | Screen movers sebelum pembukaan |
| `saham trade intraday confirm-open` | Konfirmasi opening price menjadi ENTER / WAIT / SKIP |
| `saham trade intraday pre-open-log` | Log hasil pre-open ke `journals/pre-open.csv` |
| `saham trade intraday pre-open-review` | Review akurasi entry range pre-open |
| `saham trade intraday log` / `confirm-log` | Log hasil confirm-open ke `journals/intraday-confirmations.csv` |
| `saham trade intraday review` / `confirm-review` | Review keputusan confirm-open dan context buckets |
| `saham trade intraday outcome` / `confirm-outcome` | Catat hasil aktual trade untuk mengganti proxy daily OHLC |
| `saham trade intraday backtest` | Walk-forward backtest pada data harian historis (lihat §12) |

---

### `saham data stockbit fetch-top5` — Siapkan Data Pre-Open Secara Otomatis

Membuka browser sekali, mengambil token dari session aktif, memanggil Exodus API untuk IEV movers dari semua board, lalu mengambil orderbook untuk top-N ticker — semuanya dalam satu sesi. Sekarang termasuk **offer side** (best offer price + lots) untuk menghitung SPRD%.

```bash
saham data stockbit fetch-top5           # top 5 (default)
saham data stockbit fetch-top5 --top 10  # top 10
saham data stockbit fetch-top5 --no-headless  # lihat proses di browser
```

Contoh output (dengan kolom offer):
```
  #    TICKER            IEV     BEST BID     LOTS   BEST OFFER     LOTS
  --------------------------------------------------------------------
  1    BUMI          972,420          156   409,437          157   303,382
  2    BNBR          428,497          109    32,009          110   102,408
  3    BBRI          373,423        2,850   219,024        2,860     2,772
  4    BBCA          297,068        5,925    33,568        5,950       502
  5    CUAN          281,822          715     2,923          720    21,487
```

### `saham trade intraday collect-iev` — Bangun Dataset IEV Historis

```bash
saham trade intraday collect-iev
saham trade intraday collect-iev --top-n 30
saham trade intraday collect-iev --no-headless  # lihat browser
```

Output:
```
Saved 32 movers for 2026-06-17 to data.db (IEP captured: 28/32)
  Captured at 08:45:30 WIB  [PRE-NCP]

  RANK  TICKER          IEV       IEP   ΔIEV
  ----  --------  ----------  --------  ----
     1  BUMI         972,420      157    —
     2  BNBR         428,497      109    —
     3  BBRI         373,423    2,850    —

  Movers with IEP >= 50: 28/32
  IEV/IEP history: 47 days, avg 28 movers/day, IEP fill 86%
```

Data disimpan ke `iev_snapshot_history` dengan timestamp dan flag NCP.

---

### Mode Autonomous `saham trade intraday pre-open`

Kalau `.stockbit_profile/` ada dan valid, pre-open berjalan **sepenuhnya otomatis**:

```bash
saham trade intraday pre-open --top 5
```

Output langsung:
```
Playwright session found — running autonomously...
```

Tool otomatis fetch IEV movers dari semua board (main + special monitoring board), ambil orderbook per ticker (termasuk offer side), lalu jalankan screener — tanpa input JSON manual.

---

### Endpoint Exodus API yang Dikonfirmasi (DevTools, 2026-06-13)

| Data | Endpoint |
|------|---------|
| IEV Movers (main boards) | `order-trade/market-mover?mover_type=MOVER_TYPE_IEV_TOP_GAINER` + `filter_stocks=FILTER_STOCKS_TYPE_MAIN_BOARD` (+ dev/acc/neo) |
| IEV Movers (special monitoring) | `order-trade/market-mover?mover_type=MOVER_TYPE_IEV_TOP_GAINER&filter_stocks=FILTER_STOCKS_TYPE_SPECIAL_MONITORING_BOARD` |
| Orderbook per ticker | `company-price-feed/v2/orderbook/companies/{TICKER}` |

Field response yang digunakan:
- **IEV**: `item.iepiev_detail.iev.raw`
- **IEP**: `item.iepiev_detail.iep.raw` (mungkin absent)
- **Ticker**: `item.stock_detail.code`
- **Best bid price / lots**: `data.iepiev.best_bid_offer.bid.price.raw` / `.quantity.raw`
- **Best offer price / lots**: `data.iepiev.best_bid_offer.offer.price.raw` / `.quantity.raw`

Semua endpoint + broker codes didokumentasikan di `config/stockbit.yaml`.

---

### Debugging

```bash
saham data stockbit spy --wait 10                        # Lihat semua API request
saham data stockbit spy --target orderbook --ticker BBCA # Spy khusus orderbook
saham trade intraday pre-open --no-headless --top 3      # Lihat browser saat berjalan
```

Kalau sesi expired: `saham data stockbit login`.

---

## 14. Kesalahan Umum Pemula

**1. FOMO — Masuk karena confirm-open output WAIT**

Tool bilang WAIT bukan ENTER. Kamu pikir "sayang dilewati" dan tetap masuk. Tool memberi WAIT karena trend belum terkonfirmasi. Tunggu atau skip.

**2. Mengabaikan DISTRIBUTING**

"Tapi IEV-nya tinggi!" — ya, tapi asing net-jual 7 hari terakhir. Itu penjual yang sudah siap di opening. Ikuti sinyal SKIP_BEARISH_CONTEXT.

**3. Tidak pasang stop-loss segera setelah masuk**

Setiap menit tanpa stop adalah menit kamu menanggung unlimited risk. Pasang stop sebelum melakukan hal lain.

**4. Averaging down posisi rugi**

Stop di 4,904 → harga turun ke 4,950 → kamu beli lagi karena "lebih murah". Ini salah. Kalau keyakinan masih ada, cut di 4,904 lalu evaluate ulang setelah jelas arahnya.

**5. Trading saham yang tidak ada di database**

Kalau output menunjukkan "No cached data", jalankan `saham data update TICKER --days 365` dulu. Tanpa data historis, tidak ada ATR, tidak ada entry range.

**6. Tidak membaca context FVWAP negatif besar**

FVWAP -5.8% bukan hanya "kurang ideal" — artinya asing duduk di profit besar dan mungkin jual di opening. Confirm-open mungkin tetap WAIT jika semua gate lain pass, tapi kamu harus extra cautious.

**7. Trading warrant / rights / bond / IPO baru**

SKIP_SPECULATIVE di output bukan error — itu filter otomatis. Jangan trading -W, -R, -L dengan strategi pre-open. IPO baru (< 20 hari) juga di-skip karena ATR/RSI-nya belum meaningful.

**8. Mengabaikan SKIP_LOW_VOLATILITY**

Kalau confirm-open output SKIP_LOW_VOLATILITY, artinya pergerakan harga terlalu kecil relatif terhadap tick size. Biaya round-trip (0.41–0.65%) bisa makan seluruh potensi profit. Bukan berarti sahamnya jelek — hanya tidak cocok untuk strategi ini hari ini.

**9. Tidak menjalankan collect-iev setiap hari**

Tanpa data IEV harian, backtest tidak bisa filter top-N IEV dan hasilnya kurang akurat. Rutin `saham trade intraday collect-iev` tiap hari — 30 detik saja.

---

## 15. Glosarium

| Istilah | Penjelasan |
|---------|-----------|
| **ATR** | Average True Range. Volatilitas harian rata-rata 14 hari |
| **Backtest (Option A)** | Simulasi workflow pada data harian historis; candle.open sebagai proxy opening price 09:00, exit H/L/close hari yang sama |
| **Expectancy** | Rata-rata laba per trade = win% × avgWin − loss% × \|avgLoss\|. Positif berarti strategi punya edge |
| **R-multiple** | Rasio pnl / risk awal (entry − stop × shares). Mengukur kualitas trade independen dari sizing |
| **ATR Band** | Entry range width = ATR / prev_close, capped [1%, 5%] |
| **ACCUM** | Sinyal akumulasi asing 7 hari: BACKED/UNCONFIRMED/DISTRIBUTING |
| **Call Auction** | Sistem IDX: order dikumpulkan, matching di satu harga saat buka (08:45–09:00) |
| **Clearing Price** | Harga hasil call auction yang memaksimalkan volume |
| **Confirm-Open** | Phase 2: keputusan post-open berdasarkan opening price aktual |
| **Entry Range** | ATR-scaled band di sekitar prev_close. Enter hanya jika open di sini |
| **FVWAP** | Foreign VWAP Discount: % selisih VWAP asing vs harga sekarang |
| **IEP** | Indicative Equilibrium Price — harga indikatif call auction |
| **IEV** | Intraday Expected Volume. Proxy untuk likuiditas dan institutional interest |
| **IEV Intensity** | IEV / (ADV_20d / 78). > 5× = UNUSUAL_VOLUME (minat tidak biasa) |
| **Lot** | 1 lot = 100 saham di IDX |
| **NCP** | Non-Cancellation Period: 08:56–09:00, order tidak bisa diubah |
| **Overbought** | RSI > 75. Terlalu cepat naik, risiko koreksi meningkat |
| **Pre-Open** | Phase 1: kandidat dan entry plan sebelum pasar buka |
| **Prev Close** | Harga penutupan kemarin. Referensi utama untuk entry range |
| **RSI** | Relative Strength Index. Momentum 0–100 |
| **S/R** | Support dan Resistance. Level harga penting |
| **Smart Money** | Institusi dan investor asing yang dianggap lebih informed |
| **SKIP_LOW_VOLATILITY** | Tick-friction gate: stop/target terlalu sempit dari biaya transaksi |
| **SPRD%** | Bid/offer spread dalam persen. Semakin kecil semakin likuid |
| **Stop-Loss** | Harga keluar rugi. Wajib dipasang |
| **Tick-Friction Gate** | Validasi stop >= 2 tick, target >= 3 tick (Kep-00196/BEI/12-2024) |
| **VWAP** | Volume-Weighted Average Price |

### Tick Size IDX

| Harga | Tick |
|-------|------|
| < Rp 200 | Rp 1 |
| Rp 200 – < Rp 500 | Rp 2 |
| Rp 500 – < Rp 2.000 | Rp 5 |
| Rp 2.000 – < Rp 5.000 | Rp 10 |
| ≥ Rp 5.000 | Rp 25 |

---

## Penutup

Workflow lengkap intraday dengan tool ini:

```
Setup (sekali)  : saham data stockbit login
Setup YAML      : config/pre_open_screener.yaml  (semua threshold di sini)
Malam sebelum   : saham data update --universe lq45
08:45           : saham trade intraday collect-iev                ← bangun dataset backtest
08:47           : saham trade intraday pre-open --top 5           ← autonomous
    atau        : saham trade intraday pre-open --with-regime      ← regime context
    atau        : saham trade intraday pre-open --signal-strategy NAME
09:00–09:05     : saham trade intraday confirm-open --opening-json '...'
Setelah trading : saham trade intraday log && saham trade intraday outcome TICKER --entry X --exit Y
Evaluasi       : saham trade intraday review
                saham trade intraday backtest (setelah 3+ bulan data IEV)
```

**Catatan penting tentang gate baru:**
- **Tick-friction gate** (Kep-00196/BEI/12-2024): otomatis aktif, bisa dimatikan di config kalau backtest
- **Regime gate**: aktif di WEAK/RISK_OFF, persempit entry band 50% + require BACKED
- **Speculative filter**: selalu aktif, skip warrants/rights/bonds/IPO baru
- **IEP filter**: opsional via `--iep-min`, cocok dipasangkan dengan data collect-iev

Mulai dengan paper trade 20–30 sesi. Gunakan `saham trade intraday review` untuk evaluasi objektif. Data akurat lebih berharga dari keyakinan — ikuti angka, bukan perasaan.

> "Preserve capital first. Profits will follow discipline."

---

*Dokumen ini menjelaskan cara menggunakan tool ai-saham untuk analisis pre-open dan intraday. Ini bukan saran investasi atau trading. Semua keputusan trading adalah tanggung jawab pribadi kamu.*
