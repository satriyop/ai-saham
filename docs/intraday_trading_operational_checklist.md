# Checklist Operasional Intraday Trading

Checklist harian untuk workflow pre-open sampai evaluasi. Perilaku CLI dan
config saat ini adalah sumber kebenaran jika dokumentasi drift.

## Setup Awal

- [ ] Install optional browser dependency sesuai README.
- [ ] Login manual dan simpan persistent profile:

  ```bash
  saham fetch stockbit login
  ```

- [ ] Verifikasi status lokal:

  ```bash
  saham fetch stockbit status
  ```

- [ ] Pastikan universe dan database yang digunakan sesuai workflow.

## Malam Sebelumnya

- [ ] Refresh candle dan broker flow:

  ```bash
  saham fetch market --universe lq45
  ```

- [ ] Baca status provider/cache. `cached-current` berarti cache sudah current;
  `provider-no-new-data` berarti provider sudah dicek tetapi belum punya sesi
  trading lebih baru.
- [ ] Hindari ticker yang belum punya data cukup untuk ATR/RSI.

## 08:45 — Capture IEV

- [ ] Jalankan:

  ```bash
  saham fetch iev
  ```

- [ ] Periksa ranking IEV, IEP coverage, ΔIEV, timestamp, dan badge
  `[PRE-NCP]`/`[NCP LOCKED]`.
- [ ] Simpan snapshot setiap hari agar backtest dapat memakai top-N IEV aktual.

## 08:47–08:55 — Pre-Open

### Jalur Autonomous

- [ ] Jalankan screener sebelum NCP:

  ```bash
  saham screen pre-open --top 5
  ```

- [ ] Tambahkan context bila diperlukan:

  ```bash
  saham screen pre-open --top 5
  saham screen pre-open --top 5 --signal-strategy williams-r-bounce
  saham screen pre-open --top 5 --iep-min 50
  ```

### Jalur Inspect Raw Data

- [ ] Ambil IEV dan orderbook:

  ```bash
  saham fetch stockbit fetch-top5
  ```

- [ ] Jika perlu, jalankan screener dengan `--movers-json` dan
  `--order-books-json` yang sudah diperiksa.

### Fast Mode

- [ ] Gunakan hanya jika input movers tersedia tetapi orderbook tidak:

  ```bash
  saham screen pre-open \
    --movers-json '[{"ticker":"BBCA","iev":450000}]' \
    --fast
  ```

- [ ] Ingat bahwa Gap%/spread dan confirmation orderbook tidak tersedia.

### Pemeriksaan Kandidat

- [ ] IEV memenuhi threshold aktif dan ticker bukan instrumen speculative.
- [ ] Catat Entry Range, Suggested Entry, ATR Stop, Prev H/L.
- [ ] Baca ACCUM dan FVWAP; jangan menganggap IEV sebagai sinyal arah.
- [ ] Baca spread dan warning liquidity.
- [ ] Jika memakai regime, pahami band/gate yang diperketat.
- [ ] Selesaikan keputusan order sebelum 08:56.

Untuk latihan weekend/non-trading day gunakan override eksplisit dan perlakukan
hasil sebagai dry-run:

```bash
saham screen pre-open \
  --movers-json '[{"ticker":"BBCA","iev":450000}]' \
  --fast \
  --allow-non-trading-day
```

## 09:00–09:05 — Opening Confirmation

- [ ] Ambil opening price aktual, bukan bid terakhir pre-open.
- [ ] Masukkan semua kandidat:

  ```bash
  saham trade confirm \
    --opening-json '{"BBCA":5175,"BMRI":4290,"TLKM":2820}'
  ```

- [ ] Ikuti decision deterministik:
  - `ENTER`: gunakan plan limit dan stop yang dicetak.
  - `WAIT`: tunggu confirmation; skip jika tidak jelas dalam batas waktu plan.
  - `SKIP_*`: lewatkan tanpa override ad hoc.
- [ ] Untuk `ENTER`, hitung lot dari max loss dan jarak stop.
- [ ] Pasang stop segera setelah entry terisi.
- [ ] Kurangi size saat regime/lebar spread/risiko sesi menuntut konservatisme.

## Setelah Trading — Journal dan Outcome

- [ ] Log confirmation terakhir:

  ```bash
  saham trade log intraday
  ```

- [ ] Setelah posisi ditutup, catat outcome aktual:

  ```bash
  saham trade outcome BBCA \
    --entry 5200 \
    --exit 5375 \
    --notes "keluar jam 10:30, target tercapai di Prev H"
  ```

- [ ] Jangan mengubah journal hanya untuk memperbaiki hasil statistik.

## Review Berkala

Setelah minimal sekitar 20 sesi paper trade:

```bash
saham research pre-open grade
saham trade review intraday
```

Periksa:

- win rate per decision (`ENTER`, `WAIT`, dan alasan skip);
- breakdown ACCUM, FVWAP, RSI, regime, dan ticker;
- apakah `BACKED` dan FVWAP floor benar-benar outperform;
- apakah gate mengurangi loss, bukan hanya mengurangi jumlah trade;
- kualitas dan kelengkapan outcome aktual.

## Workflow Validasi Backtest

### Baseline Historis

```bash
saham trade backtest-intraday \
  --universe lq45 \
  --start 2025-12-01
```

Jika snapshot IEV tersedia:

```bash
saham trade backtest-intraday \
  --universe lq45 \
  --iev-top-n 5 \
  --start 2026-01-01
```

### Validasi Hasil

- [ ] Gunakan periode yang menghasilkan minimal sekitar 30 trade.
- [ ] Universe cukup lebar; jangan menyimpulkan dari beberapa ticker saja.
- [ ] Periksa return, drawdown, win rate, profit factor, expectancy, dan average
  R-multiple setelah biaya.
- [ ] Periksa exit mix: `target`, `stop`, `close`, `both_assume_stop`.
- [ ] Jika `both_assume_stop` >15%, daily OHLC proxy terlalu kasar.
- [ ] Pastikan broker-flow coverage cukup untuk analisis ACCUM/FVWAP.
- [ ] Bandingkan breakdown BACKED/UNCONFIRMED/DISTRIBUTING dan FVWAP.
- [ ] Jangan menganggap backtest sebagai jaminan masa depan.

### Urutan Validasi

```text
1. Jalankan backtest historis dan cari edge setelah biaya.
2. Paper trade minimal 20 sesi dan catat outcome aktual.
3. Jalankan review intraday.
4. Bandingkan paper result dengan ekspektasi backtest.
5. Naikkan modal bertahap hanya jika hasil selaras dan risiko terkontrol.
```

## Dokumen Terkait

- [Quick Reference](intraday_trading_quick_reference.md)
- [Catatan Desain](intraday_trading_design_notes.md)
- [Indeks Panduan](how_to_intraday_trading.md)
