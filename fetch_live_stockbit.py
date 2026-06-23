from src.infrastructure.browser.playwright_stockbit import PlaywrightStockbitProvider


def main():
    print("Initializing Playwright Stockbit Provider...")
    provider = PlaywrightStockbitProvider()
    tickers = ["BUMI", "BBCA", "BNBR", "GOTO"]

    print("\nLive Order Books (09:05 WIB+)")
    print("=" * 60)
    print(f"{'TICKER':<6} | {'BEST BID':>10} | {'BEST OFFER':>10} | {'PRE-OPEN IEP':>12}")
    print("-" * 60)

    # These were the IEP values captured at 08:58:54 WIB
    iep_map = {
        "BUMI": "175",
        "BBCA": "6,400",
        "BNBR": "122",
        "GOTO": "50"
    }

    for ticker in tickers:
        try:
            ob = provider.fetch_order_book_top_of_book(ticker)
            if ob and ob.bid:
                # Based on the error, OrderBookBid might use 'volume' instead of 'lots'
                bid_vol = getattr(ob.bid, 'volume', getattr(ob.bid, 'lot', getattr(ob.bid, 'lots', 0)))
                offer_vol = getattr(ob.offer, 'volume', getattr(ob.offer, 'lot', getattr(ob.offer, 'lots', 0)))
                print(f"{ticker:<6} | {ob.bid.price:>10,} | {ob.offer.price:>10,} | {iep_map[ticker]:>12}")
            else:
                print(f"{ticker:<6} | {'NO DATA':>10} | {'NO DATA':>10} | {iep_map[ticker]:>12}")
        except Exception as e:
            print(f"{ticker:<6} | Error - {e}")

if __name__ == "__main__":
    main()
