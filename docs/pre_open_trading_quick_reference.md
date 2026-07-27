# Quick Reference Intraday Trading

Ringkasan cepat untuk menjalankan dan membaca workflow intraday `ai-saham`.
Perilaku CLI saat ini adalah sumber kebenaran jika dokumentasi drift.

## Waktu Sesi IDX

```text
08:45–08:56  PRE-OPEN INPUT; discovery, screen kandidat, siapkan order plan
08:56–08:58  NCP LOCKED INPUT; baseline 08:56, keputusan final sebelum 08:58
08:58–09:00  PRE-OPEN MATCHING; bukan window keputusan produksi
09:00        sesi reguler dan harga pembukaan
09:00–09:05  opening confirmation
09:00–11:30  sesi 1
11:30–13:30  istirahat; Jumat sampai 14:00
13:30–15:49  sesi 2
15:50–16:00  pre-close auction
16:00        harga penutupan resmi
```

Selesaikan sinyal kanonis sebelum matching pukul 08:58. Order yang sudah masuk
setelah lock 08:56 memiliki pembatasan amend/withdraw; bid/offer tetap belum
tentu menjadi clearing price.

## Command Quick Reference

| Tujuan | Command |
|---|---|
| Refresh harga dan broker flow | `saham fetch market --universe lq45` |
| Login Stockbit | `saham fetch stockbit login` |
| Cek status auth lokal | `saham fetch stockbit status` |
| Simpan snapshot IEV | `saham fetch iev` |
| Screen pre-open autonomous | `saham screen pre-open --top 5` |
| Regime + risk (always-on; opt-out with flags) | `saham screen pre-open --top 5` |
| Fast mode manual | `saham screen pre-open --movers-json '…' --fast` |
| Post-open assess NCP plan | `saham analyze pre-open --session YYYY-MM-DD` |
| Log paper assess | `saham trade log --type pre-open --observation-id … --opening-snapshot-id …` |
| Catat outcome aktual | `saham trade outcome BBCA --entry 5200 --exit 5375` |
| Review journal | `saham trade review pre-open` |
| Grade prediksi | `saham research pre-open grade` |
| Backtest intraday | `saham trade backtest-intraday --universe lq45` |

Gunakan `saham COMMAND --help` untuk option dan default yang berlaku saat ini.

## Membaca Output Pre-Open

Fase pre-open menyiapkan kandidat, bukan keputusan final masuk:

- `IEV`: estimasi volume opening; tinggi berarti aktif, bukan pasti naik.
- `IEP`: indicative equilibrium price dari call auction.
- `IEV Intensity`: IEV dibanding volume normal; unusual volume bersifat
  informasional.
- `SPRD%`: spread bid/offer; semakin kecil biasanya semakin likuid.
- `Entry Range`: rentang opening berbasis ATR di sekitar previous close.
- `Suggested Entry`: titik awal limit order, bukan harga wajib.
- `ATR Stop`: stop awal berbasis volatilitas; catat sebelum entry.
- `ACCUM`: `BACKED`, `UNCONFIRMED`, atau `DISTRIBUTING`.
- `FVWAP`: konteks posisi rata-rata beli asing terhadap harga sekarang.
- `Prev H`/`Prev L`: resistance/support hari sebelumnya.

## Membaca Opening Confirmation

| Decision | Arti ringkas |
|---|---|
| `ENTER` | Semua gate yang diperlukan pass; gunakan plan entry/stop |
| `WAIT` | Range pass tetapi arah belum cukup jelas; tunggu confirmation |
| `SKIP_GAP_UP` | Opening di atas entry range |
| `SKIP_GAP_DOWN` | Opening di bawah entry range |
| `SKIP_BEARISH_CONTEXT` | Trend, distribution, atau regime tidak mendukung |
| `SKIP_RISK_TOO_WIDE` | Jarak risiko melewati batas |
| `SKIP_LOW_VOLATILITY` | Stop/target terlalu sempit terhadap tick dan biaya |

Di regime `WEAK`/`RISK_OFF`, policy dapat mempersempit entry band dan meminta
`ACCUM=BACKED`. Baca alasan yang dicetak CLI; config dan tests menentukan
perilaku aktual.

## Aturan Risiko Ringkas

- Maksimal loss per trade: acuan konservatif 2% total modal.
- Jangan membuka lebih dari dua posisi `ENTER` sekaligus; pemula sebaiknya fokus
  pada satu posisi.
- Hitung lot dari jarak entry ke stop, bukan dari keyakinan.
- Pasang stop segera setelah order terisi dan jangan geser ke bawah.
- Ambil profit sebagian di resistance/Prev High bila sesuai plan.
- Waspadai risiko gap setelah istirahat sesi.
- Hormati tick-friction gate: stop minimal 2 tick dan target minimal 3 tick
  sesuai policy aktif.
- `SKIP_*` berarti lewatkan; jangan membuat pengecualian ad hoc.

Contoh sizing:

```text
max loss = Rp200.000
entry = 5.200
stop = 4.904
risk per saham = 296
max saham = 200.000 / 296 = 675 -> 6 lot
```

## Kesalahan Umum

1. FOMO masuk saat output masih `WAIT`.
2. Mengabaikan `DISTRIBUTING` hanya karena IEV tinggi.
3. Tidak memasang stop segera atau melakukan averaging down.
4. Trading ticker tanpa data cache sehingga ATR/range tidak tersedia.
5. Mengabaikan FVWAP negatif besar dan potensi sell risk.
6. Trading warrant, rights, bond, atau IPO baru dengan workflow ini.
7. Mengabaikan `SKIP_LOW_VOLATILITY` dan biaya round-trip.
8. Tidak menjalankan `saham fetch iev`, sehingga validasi top-N IEV historis
   kehilangan data.

## Glosarium

| Istilah | Penjelasan |
|---|---|
| ATR | Average True Range; volatilitas harian rata-rata |
| ATR Band | Lebar entry range berbasis ATR/previous close |
| ACCUM | Konteks akumulasi: BACKED/UNCONFIRMED/DISTRIBUTING |
| Backtest Option A | Simulasi memakai daily OHLC sebagai proxy intraday |
| Call Auction | Order dikumpulkan lalu match pada satu clearing price |
| Entry Range | Rentang opening yang lolos range gate |
| Expectancy | Rata-rata laba/rugi per trade setelah probabilitas |
| FVWAP | Foreign VWAP Discount terhadap harga sekarang |
| IEP | Indicative Equilibrium Price |
| IEV | Intraday Expected Volume |
| IEV Intensity | IEV dibanding estimasi volume normal per interval |
| Lot | 100 saham IDX |
| NCP | No-amend 08:56–09:00; locked-input/no-withdraw 08:56–08:58 |
| Opening Confirmation | Keputusan post-open dari opening price aktual |
| Prev Close/H/L | Close, high, dan low hari sebelumnya |
| RSI | Relative Strength Index 0–100 |
| SPRD% | Spread best offer terhadap best bid dalam persen |
| Tick-Friction Gate | Menolak plan dengan stop/target terlalu sedikit tick |

### Tick Size IDX

| Harga | Tick |
|---|---|
| < Rp200 | Rp1 |
| Rp200–<Rp500 | Rp2 |
| Rp500–<Rp2.000 | Rp5 |
| Rp2.000–<Rp5.000 | Rp10 |
| ≥ Rp5.000 | Rp25 |

## Dokumen Terkait

- [Checklist Operasional](pre_open_trading_operational_checklist.md)
- [Catatan Desain](pre_open_trading_design_notes.md)
- [Indeks Panduan](how_to_pre_open_trading.md)
