
import pandas as pd
import yfinance as yf


def main():
    tickers = ["BBCA.JK", "BUMI.JK", "BNBR.JK", "GOTO.JK"]
    print("Fetching 5-minute data for today from yfinance...\n")

    for ticker in tickers:
        print(f"=== {ticker} ===")
        try:
            # Fetch 1 day of 5-minute data
            data = yf.download(ticker, period="1d", interval="5m", progress=False)
            if data.empty:
                print("No intraday data found.\n")
                continue

            # Format and print the first 6 candles (first 30 minutes of open)
            data.index = data.index.tz_convert('Asia/Jakarta')

            # Flatten multiindex columns if they exist (yfinance sometimes returns multiindex)
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = [c[0] for c in data.columns]

            # Slice the first hour roughly
            morning_data = data.between_time('09:00', '10:00')

            for index, row in morning_data.iterrows():
                print(f"Time: {index.strftime('%H:%M')} | Open: {row['Open']:>6.0f} | High: {row['High']:>6.0f} | Low: {row['Low']:>6.0f} | Close: {row['Close']:>6.0f} | Vol: {row['Volume']:>9,.0f}")
            print("\n")
        except Exception as e:
            print(f"Error fetching data: {e}\n")

if __name__ == "__main__":
    main()
