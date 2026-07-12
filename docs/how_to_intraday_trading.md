# Panduan Intraday Trading dengan ai-saham

Panduan ini menjadi indeks singkat untuk referensi, checklist operasional, dan
catatan desain workflow intraday `ai-saham`.

## Dokumen Aktif

- [Quick Reference Intraday](intraday_trading_quick_reference.md) — istilah,
  waktu sesi IDX, perintah utama, cara membaca output, aturan risiko, dan
  kesalahan umum.
- [Checklist Operasional Intraday](intraday_trading_operational_checklist.md) —
  workflow harian dari persiapan, pre-open, confirmation, journal, review,
  sampai validasi backtest.
- [Catatan Desain Intraday](intraday_trading_design_notes.md) — penjelasan
  indikator, IEV/IEP, liquidity, speculative filter, FVWAP, Stockbit adapter,
  dan endpoint yang digunakan.

## Arsip

- [Panduan Intraday Lengkap (Arsip)](archive/how_to_intraday_trading_full_guide.md)
  mempertahankan seluruh materi historis sebelum dokumen aktif dipecah.

## Authority Warning

Perilaku CLI saat ini adalah sumber kebenaran jika dokumentasi drift. Verifikasi
nama command, option, default, output, dan gate terhadap `saham --help`, config,
code, dan tests sebelum menjalankan workflow produksi.
