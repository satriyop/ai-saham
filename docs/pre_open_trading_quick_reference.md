# Pre-Open Quick Reference

Ringkasan cepat lane **pre-open**. Sumber kebenaran operator:
[runbook_pre_open.md](runbook_pre_open.md). CLI `--help` menang jika drift.

## Waktu Sesi IDX (WIB)

```text
08:45–08:56  PRE-OPEN INPUT; screen live opsional
08:56–08:58  NCP LOCKED INPUT; baseline IEV 08:56, capture keputusan 08:57
08:58–09:00  PRE-OPEN MATCHING; bukan window keputusan produksi
09:00        sesi reguler; track opening samples
09:00+       analyze pre-open (human); paper log opsional
09:36–09:37  labels + evaluate (cron)
```

## Dua lane + tiga artifact

| Lane | Commands |
|------|----------|
| Signal / plan | `screen pre-open` (live), `research pre-open capture` (write) |
| Learning | `track` → `labels` → `evaluate` / `status` |
| Human (bukan learning) | `analyze pre-open`, `trade pre-open log` |

| Artifact | Owner |
|----------|--------|
| NCP observation | `learning_observations` via capture |
| Post-open assess | `analyze pre-open` (stdout only) |
| open_30m label | `research pre-open labels` |

## Command table

| Tujuan | Command |
|--------|---------|
| Multi-tick IEV | `saham fetch iev` (cron 08:47/50/53/56) |
| Screen live (no write) | `saham screen pre-open --top 5` |
| Capture NCP decision | `saham research pre-open capture` |
| Track open | `saham research pre-open track` |
| Post-open assess | `saham analyze pre-open --session YYYY-MM-DD` |
| Paper log | `saham trade pre-open log --observation-id … --opening-snapshot-id …` |
| Paper review | `saham trade pre-open review` |
| Outcome paper | `saham trade pre-open outcome TICKER --entry … --exit …` |
| Labels | `saham research pre-open labels` |
| Evaluate cohort | `saham research pre-open evaluate` |
| Status | `saham research pre-open status` |
| Install cron | `./install_cron.sh` |

**Retired:** `trade confirm`, `trade pre-open log (intraday type removed)`, `research pre-open grade|prompt|tune`.

## Membaca post-open assess

| Decision | Arti ringkas |
|----------|--------------|
| `ENTER` | Gate pass; gunakan plan entry/stop dari assess |
| `WAIT` | Range pass; arah belum BULLISH |
| `SKIP_GAP_UP` / `SKIP_GAP_DOWN` | Open di luar entry range (efektif) |
| `SKIP_BEARISH_CONTEXT` | Trend / distribution / regime |
| `SKIP_RISK_TOO_WIDE` | Stop terlalu lebar |
| `SKIP_LOW_VOLATILITY` | Tick-friction |
| `SKIP_INSUFFICIENT_DATA` | Harga open / plan hilang (termasuk tanpa `opening_price` di track) |

## Aturan risiko ringkas

- Maks loss per trade: acuan ~2% modal (policy kamu).
- Jangan lebih dari dua `ENTER` sekaligus jika masih paper.
- Paper journal ≠ learning label; jangan samakan dengan `evaluate`.

Lihat [runbook_pre_open.md](runbook_pre_open.md) untuk checklist harian penuh.
