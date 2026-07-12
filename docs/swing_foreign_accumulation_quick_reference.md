# Swing Foreign Accumulation — Quick Reference

Referensi cepat untuk screening dan evaluasi swing 3–10 sesi. CLI, config, code,
dan tests saat ini adalah sumber kebenaran jika dokumentasi drift.

## Quick Reference Card

```text
SETUP / REFRESH
  saham fetch market --universe lq45

SETIAP HARI
  saham analyze regime
  saham screen accum --universe lq45 --multi

PER KANDIDAT
  saham analyze swing TICKER --setup foreign-bounce --capital 10000000
  saham analyze chart price TICKER --sma 20 --days 90
  saham analyze chart rsi TICKER --days 90
  saham analyze chart volume TICKER --days 30

JOURNAL / REVIEW
  saham trade log swing --ticker TICKER --from-analysis --with-regime
  saham trade review swing --horizon 10

BACKTEST
  saham trade backtest-swing --universe lq45 --start 2025-01-01 --with-regime
  saham analyze swing-compare --universe lq45 --start 2025-01-01
```

## Key Commands

| Tujuan | Command |
|---|---|
| Refresh market + broker flow | `saham fetch market --universe lq45` |
| Cek regime | `saham analyze regime` |
| Screen satu window | `saham screen accum --universe lq45` |
| Screen multi-window | `saham screen accum --universe lq45 --multi` |
| Filter squeeze | `saham screen accum --universe lq45 --squeeze-only` |
| Filter foreign underwater | `saham screen accum --universe lq45 --vwap-only` |
| Tampilkan definisi run | `saham screen accum --universe lq45 --explain` |
| Analisis setup | `saham analyze swing TICKER --setup foreign-bounce` |
| Flow detail | `saham analyze swing TICKER --with-flow-detail --explain` |
| Broker flow harian | `saham view broker flow TICKER --days 30` |
| Sizing standalone | `saham trade size TICKER --capital 10000000` |
| Audit accumulation | `saham analyze accum-audit --universe lq45` |

Gunakan `--help` untuk nama option dan default yang berlaku saat ini.

## Regime Implication Summary

| Regime | Implikasi operasional |
|---|---|
| `BULLISH` | Setup dapat berjalan, tetapi cek apakah harga sudah terlalu extended |
| `SIDEWAYS` | Umumnya cocok untuk akumulasi sebelum move dan compression setup |
| `WEAK` | Threshold/eligibility dapat lebih ketat; kurangi size dan butuh bukti lebih kuat |
| `RISK_OFF` | Hindari entry swing baru kecuali policy runtime secara eksplisit mengizinkan |

Regime adalah constraint/context, bukan alasan mengubah score secara manual.
Baca output `saham analyze regime`, config, dan alasan decision dari CLI.

## Score Interpretation Summary

Foreign-flow score merangkum evidence seperti konsistensi net buy, streak,
VWAP/positioning, RSI headroom, flow ratio, compression, broker concentration,
dan context lain yang diaktifkan config.

Jangan mengandalkan angka/skala historis dari arsip. Gunakan:

```bash
saham screen accum --universe lq45 --explain
```

Interpretasi umum:

- skor relatif tinggi: beberapa komponen evidence selaras; lanjut analisis;
- skor menengah: ada akumulasi tetapi trigger/context belum lengkap;
- skor rendah: evidence akumulasi lemah atau coverage terbatas;
- skor bukan keputusan entry; setup phase, trigger, coverage, conviction, regime,
  risk gates, dan DecisionPolicy tetap menentukan action.

Kolom yang perlu dibaca bersama:

| Kolom | Arti |
|---|---|
| `STREAK` | sesi net-buy beruntun terakhir |
| `NET_DAYS` | jumlah sesi net buy dalam window |
| `NET_VALUE` | kumulatif net foreign value |
| `FLOW%` | dominansi net foreign terhadap aktivitas |
| `VWAP_DISC` | posisi foreign VWAP terhadap harga |
| `RSI` | momentum/headroom |
| `BB%ILE` | compression readiness |
| `TREND` | posisi/tren relatif terhadap struktur harga |
| `BRK` | ringkasan named-broker quality bila tersedia |

## Multi-Window Pattern

| Pattern | Ringkasan |
|---|---|
| `sustained` | Akumulasi kuat lintas window; conviction relatif tinggi |
| `building` | Akumulasi recent menguat dibanding histori panjang |
| `fresh rotation` | Baru terlihat di short window; monitor noise vs awal move |
| `long-term only` | Histori panjang kuat, recent melemah; cek distribution |
| `coiled spring` | Akumulasi + compression; tetap butuh price/volume confirmation |
| `weak` | Tidak ada pola yang cukup jelas |

`BRK=smart+` dapat menguatkan context; `smart-` tidak boleh digunakan untuk
upgrade. Broker code adalah evidence, bukan bukti beneficial-owner identity.

## Kandidat Prioritas

- Pattern `sustained`, `building`, atau `coiled spring` dengan evidence lengkap.
- Foreign masih underwater/near FVWAP sesuai setup.
- Struktur sideways/base atau pullback sehat, bukan price chase.
- Compression dan volume mendukung trigger yang sedang ditunggu.
- RSI masih memiliki headroom.
- Regime dan sector context tidak memblokir decision.
- Setup detail menunjukkan gate/phase yang valid.

## Troubleshooting

### Score N/A atau 0

```bash
saham fetch broker TICKER --days 90
saham view broker flow TICKER --days 7
```

Pastikan candle dan broker data tersedia/fresh serta window memiliki cukup sesi.

### Skor Tinggi tetapi `WATCH`/`AVOID`

```bash
saham analyze swing TICKER --setup foreign-bounce --with-flow-detail
```

Periksa failed gates, coverage, conviction, setup phase, regime constraints,
price confirmation, dan risk gates. Skor tidak mengoverride policy.

### `long-term only`

Recent flow dapat melemah walau histori panjang tinggi:

```bash
saham view broker flow TICKER --days 30
```

Skip jika recent sessions menunjukkan distribution atau struktur rusak.

### Profit Factor Backtest < 1

- Jangan memaksakan parameter sampai hasil terlihat bagus.
- Bandingkan regime filter dan universe secara walk-forward.
- Periksa biaya, sample size, coverage, dan concentration per ticker.
- Uji threshold hanya lewat config/validator dan simpan hasil eksperimen.

### `RISK_OFF`

Jangan membuka posisi baru hanya karena score tinggi. Pantau regime dan validitas
posisi aktif:

```bash
saham analyze regime
saham screen accum TICKER1 TICKER2 --multi
```

## Dokumen Terkait

- [Checklist Operasional](swing_foreign_accumulation_operational_checklist.md)
- [Catatan Desain](swing_foreign_accumulation_design_notes.md)
- [Indeks Workflow](workflow_swing_foreign_accumulation.md)
