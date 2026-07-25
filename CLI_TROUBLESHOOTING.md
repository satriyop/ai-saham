# CLI Troubleshooting Guide

## "No cached data found"

```
Error: No cached data found for BBCA
Tip: Run 'saham fetch market BBCA --days 365' first to download data.
```

**Solution:** Fetch data first with `saham fetch market TICKER --days 365`

---

## "Database not found"

```
Error: Database not found at /path/to/data.db
```

**Solution:** Run `saham fetch market` for any ticker to create the database

---

## "Network connection failed"

```
Error: Network connection failed.
Tip: Check your internet connection and try again.
```

**Solution:**
- Check internet connection
- Use cached data with already-fetched tickers
- Try `--refresh` later when connection is restored

---

## "Invalid profile"

```
Error: Invalid profile 'aggresive'. Must be one of: conservative, balanced, aggressive
```

**Solution:** Check spelling of profile name

---

## "Rules file not found"

```
Error: Rules file not found: config/my_rules.yaml
```

**Solution:** Verify the path is correct, or copy from example:
```bash
cp config/custom_rules.yaml.example config/my_rules.yaml
```

---

## "Strategy not found"

```
Error: Strategy 'momentum' not found.

Searched:
  - ./momentum/strategy.yaml
  - ./strategies/momentum/strategy.yaml
  - ~/.ai-saham/strategies/momentum/strategy.yaml

Tip: Use 'saham strategy init momentum' to create a new strategy.
```

**Solution:** The strategy doesn't exist in any search location. Options:

1. **Create the strategy:**
   ```bash
   saham strategy init momentum
   ```

2. **Check spelling:** Strategy names are case-sensitive

3. **Use explicit path:** If the file is elsewhere:
   ```bash
   saham strategy backtest BBCA --strategy ./path/to/strategy.yaml
   ```

4. **List available strategies:**
   ```bash
   saham strategy list
   ```

---

## "Strategy already exists"

```
Error: Strategy already exists at strategies/momentum/strategy.yaml
Use --force to overwrite.
```

**Solution:** Either use a different name or add `--force`:
```bash
saham strategy init momentum --force
```

---

## "Unknown indicator" in rules

```
Error: Rule references undefined indicator 'SMOOTH_RSI'.
Define it in the 'indicators' section, use a built-in, or register a formula.
```

**Solution:** The indicator isn't defined anywhere. Options:

1. **Create and save the formula:**
   ```bash
   saham indicator create "smoothed RSI" --name SMOOTH_RSI --provider mock
   ```

2. **Define it in the rules file:**
   ```yaml
   indicators:
     smooth_rsi:
       formula: "SMA(RSI(14), 10)"
   ```

3. **Use a built-in instead:** RSI, SMA, EMA, ATR

Check available indicators with:
```bash
saham indicator list
```

---

## "AI explanation unavailable"

```
AI explanation unavailable: DEEPSEEK_API_KEY not set
Tip: Set the appropriate API key environment variable.
```

**Solution:**
- Set DeepSeek API key (default): `export DEEPSEEK_API_KEY=sk-...`
- Set Claude API key: `export ANTHROPIC_API_KEY=sk-...`
- Or use local Ollama: `--provider ollama`
- Or use mock for testing: `--provider mock`

---

## "Stockbit session not found"

```
No session found.
Run: saham fetch stockbit login
```

**Solution:** Stockbit browser session is missing. Run `saham fetch stockbit login` to create a persistent profile:

1. Install dependencies: `pip install -e ".[browser]" && playwright install chromium`
2. Login: `saham fetch stockbit login`
3. Check: `saham fetch stockbit status`

---

## "Stockbit session expired"

```
Session may be expired — re-run login.
```

**Solution:** Browser sessions can expire. Refresh with:
```bash
saham fetch stockbit login
```

Or use IDX provider (no auth needed):
```bash
saham fetch broker BBCA
```

---

## "IDX API returned 403 Forbidden"

```
Error: IDX API returned 403 Forbidden.
```

**Solution:** The IDX API may be temporarily unavailable or blocking requests. Wait a few minutes and retry. If persistent, the API endpoint may have changed.

---

## "No broker data found"

```
No data found. Run 'saham fetch broker BBCA' first.
```

**Solution:** Fetch broker data before viewing:
```bash
saham fetch broker BBCA --days 30
saham view ticker flow BBCA
```

---

**More help:**
- CLI Reference: `CLI_REFERENCE.md`
- Tutorial & Workflows: `CLI_GUIDE.md`
