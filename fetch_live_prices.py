from datetime import date
from src.infrastructure.data_providers.yahoo import YahooFinanceProvider

def main():
    provider = YahooFinanceProvider()
    tickers = ["BBCA", "GOTO", "BUMI", "BNBR"]
    today = date.today()
    
    print("Fetching live prices...")
    for ticker in tickers:
        try:
            candles = provider.fetch_candles(ticker, start_date=today, end_date=today)
            if candles:
                c = candles[-1]
                print(f"{ticker}: Open={c.open}, High={c.high}, Low={c.low}, Current={c.close}, Vol={c.volume}")
            else:
                print(f"{ticker}: No live data found for today.")
        except Exception as e:
            print(f"{ticker}: Error - {e}")

if __name__ == "__main__":
    main()
