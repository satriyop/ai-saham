# Swing Foreign Accumulation — Catatan Desain

Catatan konsep di balik workflow swing foreign accumulation. Dokumen ini tidak
mengubah strategy, config, atau authority. CLI, code, config, dan tests saat ini
menjadi sumber kebenaran jika contoh atau planning text drift.

## Filosofi

Premis historis strategi adalah bahwa pembelian asing yang konsisten dapat
menjadi leading evidence sebelum harga bergerak. Kemungkinan yang diamati:

1. institusi sedang membangun posisi;
2. institusi melakukan average-down atas posisi lama;
3. flow terlihat kuat tetapi sebenarnya noise, rotation singkat, atau menjelang
   distribution.

Karena itu flow tidak cukup menjadi trigger entry. Kombinasi yang dicari adalah:

```text
akumulasi konsisten
+ foreign positioning/FVWAP context
+ struktur harga dan relative strength yang layak
+ compression/readiness
+ price/volume confirmation
+ regime dan risk policy yang mengizinkan
```

Strategi berusaha masuk sebelum move, tetapi tidak berarti membeli tanpa
confirmation. Raw net buy tidak boleh langsung menciptakan `ENTER`.

## Score Component Explanation

Foreign-flow score adalah ringkasan evidence, bukan probabilitas profit dan
bukan decision final. Komponen historis mencakup:

| Komponen | Pertanyaan yang dijawab |
|---|---|
| Konsistensi | Berapa banyak sesi dalam window yang net buy? |
| Streak | Apakah net buy berlanjut sampai sesi terbaru? |
| VWAP discount | Apakah foreign flow masih underwater atau sudah profit? |
| RSI headroom | Apakah momentum masih punya ruang tanpa terlalu panas? |
| Flow ratio | Seberapa dominan net foreign terhadap aktivitas? |
| BB compression | Apakah volatilitas sedang terkompresi? |
| Broker concentration/BCI | Apakah named broker quality mendukung context? |
| Sector breadth | Apakah pergerakan didukung rotasi/partisipasi sektor? |

Bobot, scale, cap, bonus, threshold, dan status authority telah berubah sepanjang
evolusi sistem. Gunakan `saham screen accum --explain`, config, code, dan tests
untuk kontrak runtime; jangan menyalin angka dari arsip ke implementasi baru.

### Membaca Evidence Bersama

- `NET_DAYS` tinggi tanpa recent streak dapat berarti flow lama melemah.
- Streak tinggi dengan coverage pendek perlu diperlakukan konservatif.
- VWAP discount positif dapat menjadi floor context, bukan jaminan defend.
- RSI memberi momentum/headroom context, bukan trigger tunggal.
- Compression adalah readiness; arah baru jelas setelah release/confirmation.
- Broker code adalah evidence perilaku, bukan bukti beneficial owner.
- Sector breadth dapat memperkuat context tetapi tidak mengoverride ticker risk.

## Multi-Window Pattern

Multi-window membedakan akumulasi recent dan historis:

| Pattern | Penjelasan desain |
|---|---|
| `sustained` | Evidence kuat di short, medium, dan long window |
| `building` | Recent/medium flow menguat dibanding histori panjang |
| `fresh rotation` | Kuat hanya di short window; awal move atau noise |
| `long-term only` | Histori panjang kuat tetapi recent melemah |
| `coiled spring` | Akumulasi bertemu compression; trigger belum otomatis aktif |
| `weak` | Tidak ada alignment yang cukup jelas |

Pattern membantu prioritas research dan monitoring. Pattern tidak boleh
mengalahkan phase validity, price confirmation, regime, atau risk gates.

## Setup Catalog

Setup dipilih secara eksplisit agar pertanyaan yang diuji jelas. Gate dan
threshold aktual berasal dari `config/swing_setups.yaml` dan tests.

### `foreign-bounce`

Digunakan ketika foreign accumulation/positioning mendukung bounce dari area
foreign VWAP atau base. Pertanyaan utamanya:

```text
apakah foreign evidence cukup kuat,
harga belum terlalu extended,
dan phase/trigger mengizinkan entry?
```

Historical guide mencatat gate score, VWAP discount, trend, flow ratio, RSI
availability, dan RSI cap. Angka historis tidak menjadi authority; baca output
gate runtime untuk `MATCH`, `PARTIAL`, atau `NO_MATCH`.

### `coiled-spring`

Menguji accumulation saat BB width/volatilitas terkompresi. Compression saja
tidak bullish; breakout/pivot dengan volume/price confirmation tetap diperlukan.

### `smart-money-confirmed`

Menguji apakah named-broker flow lebih konsisten dengan smart-money evidence
daripada noise/retail-heavy flow. Broker quality harus tetap diagnostic atau
sesuai authority status sampai validasi historis mendukung promotion.

### `pullback-continuation`

Menguji pullback dalam tren yang sudah terbentuk. Setup ini membutuhkan struktur
trend, support/reclaim, dan flow yang tidak menunjukkan distribution.

## Regime Context

Regime menjawab apakah kondisi pasar mendukung setup, bukan mengubah evidence
mentah secara tersembunyi.

```text
BULLISH:
  banyak setup didukung, tetapi risiko price extension meningkat

SIDEWAYS:
  base/compression accumulation sering lebih mudah diamati

WEAK:
  perlu evidence lebih kuat, eligibility lebih ketat, dan size lebih kecil

RISK_OFF:
  entry baru biasanya dibatasi atau dilarang oleh policy
```

Label, threshold, confidence, stability, dan allowed decision aktual berasal
dari regime engine/config. Setup-specific policy dapat memperketat regime, bukan
diam-diam melonggarkan larangan.

## Enrichment Signals

Enrichment memperkaya konteks tetapi authority masing-masing harus dibaca dari
runtime/config.

| Signal | Peran desain |
|---|---|
| Analyst consensus | Ekspektasi analis dan target context |
| Shareholding | Struktur kepemilikan/institutional context |
| Bandar detector | Domestic accumulation/distribution diagnostic |
| Fundamentals | Quality/valuation context |
| Insider activity | Event/insider direction context |
| Corporate actions | Event risk dan active-window warning |
| Seasonality | Weak prior dengan sample-size requirement |
| Broker quality | Named-broker flow diagnostic/attribution |

Analysis sebaiknya membaca cache lokal/PIT sesuai workflow. Enrichment yang
missing menurunkan coverage; jangan diubah menjadi nilai nol atau bearish secara
otomatis. Diagnostic evidence tidak boleh menjadi scoring authority hanya
karena tersedia di output.

## Chart Confirmation

Chart digunakan untuk memeriksa apakah struktur mendukung evidence numerik:

| Cek | Mendukung | Warning |
|---|---|---|
| Harga | base, higher low, range ketat, support hold | breakdown, lower low, extended |
| RSI | pulih dan punya headroom | stuck oversold saat lower low atau overbought |
| Volume | dry-up lalu directional expansion | volume tipis/noisy atau bearish spike |
| Relative strength | tidak tertinggal berat dari IHSG/sector | rotation-out/distribution |
| VWAP/support | reclaim/hold sesuai setup | gagal reclaim atau breakdown |

Chart tidak menjadi subjective override terhadap hard gate. Ia mengonfirmasi
struktur dan membantu menentukan apakah order plan konsisten dengan output.

## Sizing dan Execution Design

Position sizing memisahkan conviction dari jumlah uang yang dirisikokan:

```text
risk budget = capital * risk_pct
risk per share = entry - stop
shares = risk budget / risk per share
lots = floor(shares / 100)
```

Regime, volatility, liquidity, dan portfolio cap dapat memperkecil effective
size. Jangan memperbesar size hanya karena score tinggi.

Pilihan stop historis meliputi ATR stop, setup-percentage stop, atau structural
stop. Output/config aktual menentukan plan. Stop dipasang setelah fill dan tidak
digeser ke bawah. Entry memakai limit dan invalidation yang sudah ditulis.

## Journal dan Attribution

Journal sebaiknya menyimpan semua kandidat yang dianalisis, tidak hanya trade
yang dieksekusi. Field penting meliputi:

```text
setup dan setup_match
failed gates
regime
planned entry/stop/target
max hold
score/pattern/evidence context
actual entry/outcome bila ada
```

Review membandingkan score bucket, setup match, pattern, regime, broker quality,
VWAP, max-up, max-drawdown, dan forward return. Tujuannya menguji apakah evidence
memisahkan winners/losers, bukan membenarkan threshold yang sudah dipilih.

## Backtest Design

Backtest swing melakukan replay per tanggal, membuka sinyal eligible dalam
portfolio/risk constraints, lalu keluar berdasarkan TP, SL, atau max hold.
Biaya diterapkan pada entry dan exit.

Validasi perlu melihat:

- return dan max drawdown;
- win rate, average trade, profit factor, dan exposure;
- skipped reason, no-forward-data, dan coverage;
- attribution per regime, pattern, setup, ticker, dan evidence bucket;
- concentration pada satu regime/ticker;
- hasil walk-forward/OOS sebelum config production berubah.

Broker-quality audit harus dilakukan sebelum `smart+`, `noise+`, atau `smart-`
dipromosikan menjadi gate. Backtest buruk bukan alasan untuk mencoba filter tanpa
batas sampai overfit.

## Contoh Ringkas

```text
Candidate: TICKER
Pattern: building / coiled spring
Foreign evidence: recent net-buy + positive positioning context
Setup phase: COMPRESSION, trigger pending
Regime: SIDEWAYS
Decision: WATCH
Reason: Alpha evidence ada, tetapi price/volume confirmation belum lengkap

Order plan baru dibuat setelah:
- setup/phase valid;
- trigger terkonfirmasi;
- risk gate pass;
- entry, stop, target, max hold, dan lot sudah dihitung.
```

Contoh output lengkap dan threshold historis dipertahankan di
[arsip workflow lengkap](archive/workflow_swing_foreign_accumulation_full_guide.md).

## Dokumen Terkait

- [Quick Reference](swing_foreign_accumulation_quick_reference.md)
- [Checklist Operasional](swing_foreign_accumulation_operational_checklist.md)
- [Indeks Workflow](workflow_swing_foreign_accumulation.md)
- [Konsep Dasar ATR/RSI/FVWAP](how_to_intraday_trading.md)
