# Swing Foreign Accumulation — Checklist Operasional

Checklist harian dan mingguan untuk screening, analisis, sizing, monitoring,
journal, dan validasi. CLI/code/tests menang jika dokumentasi drift.

## Prasyarat

- [ ] Tentukan universe (`lq45`, `idx80`, atau ticker eksplisit).
- [ ] Fetch data harga dan broker flow:

  ```bash
  saham fetch market --universe lq45
  ```

- [ ] Untuk ticker baru di luar universe:

  ```bash
  saham fetch market TICKER --days 365
  ```

- [ ] Pastikan candle, broker sessions, enrichment cache, dan benchmark context
  cukup untuk analisis yang dipilih.
- [ ] Gunakan mode cached/offline hanya jika freshness sudah dipahami.

## Workflow Harian

### 1. Refresh Data

```bash
saham fetch market --universe lq45
```

- [ ] Baca status gap-fill/provider.
- [ ] Jangan menganggap kalender hari ini berarti provider sudah menerbitkan EOD.
- [ ] Pastikan `NET_DAYS`/`STREAK` memakai jumlah sesi broker yang tersedia.

### 2. Cek Regime

```bash
saham inspect regime
```

- [ ] Catat label, confidence/stability bila ditampilkan, benchmark trend,
  breadth, dan foreign-flow breadth.
- [ ] Jangan entry swing baru jika regime/policy memblokir `ENTER`.
- [ ] Kurangi size atau naikkan kebutuhan bukti di kondisi lemah sesuai policy.

### 3. Screen Candidates

```bash
saham screen accum --universe lq45 --multi
```

Filter opsional:

```bash
saham screen accum --universe lq45 --squeeze-only
saham screen accum --universe lq45 --vwap-only
saham screen accum --universe lq45 --vwap-only --squeeze-only
saham screen accum --universe idx80 --multi --top 15
saham screen accum BBCA BBRI BMRI TLKM --multi
```

- [ ] Gunakan `--detail` untuk score scale dan komponen runtime.
- [ ] Pilih 2–4 kandidat; jangan hanya urut berdasarkan score.
- [ ] Prioritaskan recent flow, phase, compression, VWAP context, trend, broker
  quality, coverage, dan regime yang saling mendukung.
- [ ] Tandai `long-term only`, recent distribution, dan price chase sebagai
  warning.

### 4. Analyze Candidates

```bash
saham plan swing TICKER \
  --setup foreign-bounce \
  --capital 10000000
```

Opsi sesuai kebutuhan:

```bash
saham plan swing TICKER --with-flow-detail
saham plan swing TICKER --with-technical-gate
saham plan swing TICKER --with-market-context
saham plan swing TICKER --strategy foreign-accumulation
saham plan swing TICKER --format json
```

- [ ] Pilih `--setup` secara eksplisit jika mengevaluasi lensa setup tertentu.
- [ ] Baca decision, setup match, failed gates, phase/trigger, coverage,
  conviction, regime constraints, risk reasons, dan freshness.
- [ ] Enrichment adalah context sesuai authority status; jangan gunakan satu
  enrichment signal untuk mengoverride canonical decision.

### 5. Chart Confirmation

```bash
# retired: inspect chart (TUI later)
# retired: inspect chart (TUI later)
# retired: inspect chart (TUI later)
```

- [ ] Struktur harga berupa base, higher low, atau pullback sehat.
- [ ] Hindari breakdown/lower-low yang bertentangan dengan setup.
- [ ] RSI memiliki headroom dan tidak menjadi trigger tunggal.
- [ ] Compression memiliki directional release/volume confirmation sebelum
  diperlakukan sebagai trigger.
- [ ] Support, Prev High/Low, dan foreign VWAP masuk akal terhadap plan.

### 6. Sizing dan Order Plan

Gunakan output analisis atau sizing standalone:

```bash
plan swing --capital  # sizing TICKER --capital 10000000 --risk-pct 1
```

- [ ] Tetapkan planned entry, stop, target, max hold, dan jumlah lot.
- [ ] Risk dihitung dari jarak entry-stop dan capital risk, bukan keyakinan.
- [ ] Periksa effective size multiplier/regime constraint bila tersedia.
- [ ] Jangan melebihi portfolio-position cap.
- [ ] Hindari market order; gunakan limit di level yang direncanakan.

Template:

```text
Ticker:
Setup/phase:
Regime:
Entry:
Stop:
Target 1 / Target 2:
Max hold:
Lots / capital at risk:
Invalidation reason:
```

### 7. Execution dan Monitoring

- [ ] Tunggu harga mencapai entry plan; swing tidak perlu entry detik pertama.
- [ ] Pasang stop segera setelah fill; jangan geser stop ke bawah.
- [ ] Catat target dan tanggal max hold.
- [ ] Monitor flow dan struktur secara singkat setiap hari:

  ```bash
  saham screen accum TICKER1 TICKER2 --multi
  saham view ticker flow TICKER --days 5
  ```

- [ ] Jika flow berbalik distribution atau setup invalid, evaluasi exit awal.
- [ ] Jika Target 1 tercapai, kelola partial exit/trailing sesuai plan.
- [ ] Exit saat max hold tercapai jika policy/setup tidak menentukan lain.

### 8. Journal dan Review

Log setiap kandidat yang dianalisis agar `MATCH`, `PARTIAL`, dan `NO_MATCH`
dapat dibandingkan:

```bash
saham trade log swing \
  --ticker TICKER \
  --from-analysis \
  --with-regime
```

Jika entry aktual berbeda:

```bash
saham trade log swing \
  --ticker TICKER \
  --entry-price 47100 \
  --from-analysis \
  --with-regime
```

Review:

```bash
saham trade accum review --horizon 5
saham trade accum review --horizon 10
```

- [ ] Bandingkan score bucket, setup match, pattern, regime, broker quality,
  VWAP context, max-up, dan max-drawdown.
- [ ] Paper trade minimal sample yang memadai sebelum sizing besar.

## Workflow Mingguan

- [ ] Refresh universe lebih luas bila digunakan:

  ```bash
  saham fetch market --universe idx80
  ```

- [ ] Review posisi aktif dan kandidat yang belum trigger.
- [ ] Review journal 5d/10d dan outlier.
- [ ] Audit apakah data stale/missing memengaruhi keputusan.
- [ ] Jangan mengubah threshold dari beberapa contoh saja.

## Backtest Workflow

### Baseline

```bash
saham trade backtest-swing --universe lq45 --start 2025-01-01
```

### Dengan Regime

```bash
saham trade backtest-swing \
  --universe lq45 \
  --start 2025-01-01 \
  --with-regime
```

### Compare Variant

```bash
saham plan swing-compare --universe lq45 --start 2025-01-01
```

### Broker Quality Audit

```bash
saham research accum evaluate \
  --universe lq45 \
  --setup foreign-bounce \
  --start 2026-01-01
```

### Validation Checklist

- [ ] Biaya entry/exit diterapkan.
- [ ] Sample size dan periode cukup; tidak didominasi satu ticker/regime.
- [ ] Periksa return, max drawdown, win rate, profit factor, exposure, dan
  skipped reasons.
- [ ] Bandingkan performa per regime dan setup/pattern.
- [ ] Periksa no-forward-data dan coverage gaps.
- [ ] Uji broker-quality bucket sebelum menjadikannya gate.
- [ ] Gunakan walk-forward/OOS evidence sebelum mengubah config produksi.
- [ ] Jangan mengejar overfit melalui kombinasi filter berulang.

## Dokumen Terkait

- [Quick Reference](swing_foreign_accumulation_quick_reference.md)
- [Catatan Desain](swing_foreign_accumulation_design_notes.md)
- [Indeks Workflow](workflow_swing_foreign_accumulation.md)
