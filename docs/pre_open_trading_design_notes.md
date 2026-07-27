# Catatan Desain Intraday Trading

Penjelasan konsep dan integrasi yang mendasari workflow intraday. Dokumen ini
bukan pengganti output CLI, config, code, atau tests yang berlaku saat ini.

## Model Dua Fase

Workflow memisahkan kandidat dari keputusan entry:

```text
Fase 1 — pre-open:
  identifikasi kandidat, liquidity, entry range, stop, dan context

Fase 2 — post-open:
  gunakan opening price aktual untuk ENTER / WAIT / SKIP
```

Bid pre-open berubah dan belum tentu menjadi clearing price. Previous close
adalah referensi stabil untuk plan; opening price hasil call auction menjadi
input confirmation setelah 09:00.

## IEV, IEP, dan Liquidity

### IEV

IEV adalah estimasi volume lot yang dapat match saat opening. IEV tinggi berarti
pasar aktif dan cenderung lebih mudah dimasuki/ditinggalkan; bukan prediksi arah.
Threshold default historis dalam panduan adalah 100.000 lot, tetapi config/CLI
saat ini menentukan nilai aktual.

### IEV Intensity

```text
IEV_Intensity = IEV / (ADV_20d / 78)
```

`78` mewakili jumlah interval lima menit dalam satu sesi. Nilai sangat tinggi
dapat diberi label unusual volume. Label ini informasional, bukan gate arah.

### IEP

IEP adalah Indicative Equilibrium Price dari call auction. IEP dapat dipakai
untuk filter harga minimum dan disimpan bersama snapshot IEV jika tersedia.

### Liquidity dan Spread

IEV mengukur aktivitas indikatif; `SPRD%` mengukur biaya implisit best bid/offer:

```text
SPRD% = (best_offer - best_bid) / best_bid * 100
```

Spread sempit biasanya lebih sesuai untuk execution intraday. Spread lebar
meningkatkan slippage dan biaya keluar ketika arah salah.

## Speculative Symbol Filter

Workflow pre-open tidak dirancang untuk warrant (`-W`), rights/HMETD (`-R`),
bond-like symbols, atau listing yang belum memiliki histori cukup. Instrumen
tersebut memiliki mekanisme harga, maturity, dan volatilitas berbeda. Filter
speculative adalah guardrail, bukan error data.

## ATR dan Plan Risiko

ATR mengukur true range rata-rata, biasanya memakai 14 sesi:

```text
True Range = max(High-Low, |High-PrevClose|, |Low-PrevClose|)
ATR(14) = smoothed average True Range
```

Kegunaan utama:

```text
entry band = ATR / previous close, capped oleh policy
ATR stop = entry - ATR multiple, dibatasi max-stop policy
```

ATR-scaled band menyesuaikan plan dengan karakter volatilitas ticker. Data
harian tetap proxy kasar untuk intraday dan dapat drift setelah corporate
action. Nilai multiplier, cap, dan stop aktual berasal dari config dan output.

## RSI

RSI mengukur momentum 0–100. Pedoman historis:

```text
RSI > 75  overbought / bearish context untuk long
RSI 65–75 panas, perlu waspada
RSI 30–65 ruang long relatif lebih sehat
RSI < 30  oversold, tetapi bisa tetap dalam downtrend
```

RSI memberi konteks tren, bukan trigger entry mandiri. RSI rendah tidak menjamin
rebound, dan RSI tinggi tidak berarti harga langsung turun.

## Gap dan Entry Range

```text
Gap% = (harga pre-open - previous close) / previous close * 100
Entry Range = previous close ± ATR-scaled band
```

Gap hanya tersedia jika orderbook/pre-open price tersedia. Opening di atas range
menunjukkan chase risk; opening di bawah range menunjukkan bearish/problem
context. Regime policy dapat mempersempit band secara eksplisit.

## Suggested Entry dan ATR Stop

Suggested Entry adalah titik awal limit order, bukan harga pasti. Gunakan hanya
setelah opening price lolos confirmation. ATR Stop harus ditetapkan sebelum
entry dan tidak digeser ke bawah setelah posisi rugi.

## Tick Friction

IDX menggunakan tick minimum berdasarkan tier harga. Plan dengan stop atau
target terlalu sedikit tick dapat habis oleh spread dan biaya transaksi. Gate
historis meminta stop minimal 2 tick dan target minimal 3 tick; config/tests
saat ini menentukan policy aktual.

| Harga | Tick |
|---|---|
| < Rp200 | Rp1 |
| Rp200–<Rp500 | Rp2 |
| Rp500–<Rp2.000 | Rp5 |
| Rp2.000–<Rp5.000 | Rp10 |
| ≥ Rp5.000 | Rp25 |

## ACCUM

ACCUM merangkum konsistensi foreign/broker flow dalam window historis:

| Label | Makna desain |
|---|---|
| `BACKED` | Akumulasi cukup konsisten untuk menambah conviction |
| `UNCONFIRMED` | Aktivitas ada tetapi pola akumulasi belum jelas |
| `DISTRIBUTING` | Net sell/distribution context; tidak cocok untuk long |

IEV + `BACKED` adalah konfluensi liquidity dan positioning. ACCUM bukan bukti
identitas beneficial owner dan tidak boleh mengalahkan price confirmation.

## FVWAP

FVWAP membandingkan rata-rata harga beli asing dengan harga sekarang:

```text
FVWAP = foreign_buy_value / (foreign_buy_lots * 100)
FVWAP% = (FVWAP - current_price) / current_price * 100
```

- FVWAP positif: rata-rata beli asing di atas harga sekarang; dapat menjadi
  floor/defend context.
- FVWAP negatif besar: posisi asing berada dalam profit; sell risk meningkat.
- Dekat nol: tidak ada insentif arah yang kuat dari metric ini.

FVWAP adalah context, bukan jaminan institusi akan mempertahankan harga.

## Previous High dan Previous Low

Previous High sering menjadi resistance/target awal; Previous Low menjadi
support dan warning jika ditembus. Level ini membantu menilai apakah target dan
stop masih logis terhadap struktur hari sebelumnya.

## Opening Confirmation Gates

Decision tree menggabungkan opening range, arah/tren, ACCUM, regime, jarak stop,
dan tick friction. Output alasan harus dipertahankan agar keputusan auditable.

```text
ENTER                 semua gate yang diperlukan pass
WAIT                  range pass, confirmation belum cukup
SKIP_GAP_UP/DOWN      opening keluar entry range
SKIP_BEARISH_CONTEXT  arah/distribution/regime tidak mendukung
SKIP_RISK_TOO_WIDE    stop melewati batas risiko
SKIP_LOW_VOLATILITY   target/stop tidak ekonomis dalam tick
```

## Daily OHLC Backtest Proxy

Backtest Option A memakai candle harian:

```text
signal dihitung dengan data sampai d-1
opening = candle.open pada d
low/high menguji stop dan target
jika stop dan target sama-sama tersentuh, asumsi konservatif stop dulu
posisi yang tersisa keluar di close
tidak ada overnight
```

Proxy ini tidak mengetahui urutan intraday high/low. `both_assume_stop` yang
tinggi menunjukkan hasil terlalu sensitif terhadap keterbatasan daily OHLC.

## Stockbit Adapter

### Persistent Profile dan JWT

```bash
saham fetch stockbit login
saham fetch stockbit status
```

Login menyimpan persistent browser profile dan mencoba menangkap JWT Exodus.
JWT memakai claim `exp`; fallback TTL hanya berlaku untuk JWT valid tanpa
`exp`. Browser-profile age bersifat informasional. API client dapat mencoba satu
refresh dari profile ketika token tidak tersedia atau ditolak.

`saham fetch stockbit browse` membuka profile tersimpan dan dapat menangkap JWT
RS256 baru dari request Exodus normal. Berhasil membuka halaman saja bukan
bukti bahwa API menerima token.

### Command Adapter

| Command | Fungsi |
|---|---|
| `saham fetch stockbit login` | Login manual dan simpan profile |
| `saham fetch stockbit status` | Status lokal profile/token tanpa network |
| `saham fetch stockbit fetch-top5` | IEV movers dan top-of-book |
| `saham fetch stockbit test` | Smoke test movers/orderbook |
| `saham fetch stockbit spy` | Capture traffic untuk debugging endpoint |
| `saham fetch stockbit browse` | Browser interaktif dengan profile tersimpan |

### IEV Snapshot

```bash
saham fetch iev
saham fetch iev --top-n 30
```

Snapshot menyimpan ranking, timestamp, IEP bila tersedia, ΔIEV, dan status NCP
ke histori lokal untuk replay/backtest top-N.

### Endpoint Exodus yang Digunakan

Endpoint historis yang dikonfirmasi melalui DevTools:

| Data | Pola endpoint |
|---|---|
| IEV movers main board | `order-trade/market-mover` dengan mover/filter main board |
| IEV special monitoring | `order-trade/market-mover` dengan special-monitoring filter |
| Orderbook ticker | `company-price-feed/v2/orderbook/companies/{TICKER}` |

Field yang digunakan:

```text
ticker     item.stock_detail.code
IEV        item.iepiev_detail.iev.raw
IEP        item.iepiev_detail.iep.raw (optional)
best bid   data.iepiev.best_bid_offer.bid.price/quantity.raw
best offer data.iepiev.best_bid_offer.offer.price/quantity.raw
```

Detail endpoint/config aktual berada di `config/stockbit.yaml` dan code provider.
Jangan menyalin raw probe payload ke dokumen aktif.

### Debugging

```bash
saham fetch stockbit spy --wait 10
saham fetch stockbit spy --target orderbook --ticker BBCA
saham screen pre-open --no-headless --top 3
```

Jika profile tidak dapat menghasilkan token valid, ulangi login manual.

## Dokumen Terkait

- [Quick Reference](pre_open_trading_quick_reference.md)
- [Checklist Operasional](pre_open_trading_operational_checklist.md)
- [Indeks Panduan](how_to_pre_open_trading.md)
- [Panduan Lengkap Arsip](archive/how_to_intraday_trading_full_guide.md)
