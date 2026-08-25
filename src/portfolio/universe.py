"""The investable universe, frozen as of January 2016.

Selection rule (applied once, by hand, and never revised):
  - Stocks must have been S&P 500 members on 1 January 2016.
  - Within each GICS sector we take the largest companies by market cap at
    end-2015, keeping four per sector so that sector caps are meaningful.
  - Stocks must have a full daily price history from April 2008 (the month
    Philip Morris International listed), because the tuning period (2011-2015)
    and the three-year estimation window both need it.  This excluded Facebook (IPO May 2012) and LyondellBasell
    (listed April 2010); Oracle and PPG took their places.
  - Companies whose ticker did not survive continuously to 2026 (mergers,
    delistings such as Dow/DuPont, Monsanto, Praxair) were skipped because
    yfinance cannot serve their history.  This is a residual survivorship
    bias and is disclosed in the docs.
  - Sector labels follow GICS as of late 2016 (Real Estate became its own
    sector in September 2016).  Alphabet, Meta, Disney and Comcast are
    labelled as they were then, before Communication Services existed (2018).

Three non-equity assets give the optimiser somewhere to hide:
  AGG (broad US bonds), GLD (gold), and CASH (3-month T-bill rate).
"""

from __future__ import annotations

# yfinance symbol -> (company name, GICS sector as of 2016)
STOCKS: dict[str, tuple[str, str]] = {
    # Information Technology
    "AAPL": ("Apple", "Information Technology"),
    "MSFT": ("Microsoft", "Information Technology"),
    "GOOGL": ("Alphabet", "Information Technology"),
    "ORCL": ("Oracle", "Information Technology"),
    "INTC": ("Intel", "Information Technology"),
    "CSCO": ("Cisco", "Information Technology"),
    # Health Care
    "JNJ": ("Johnson & Johnson", "Health Care"),
    "PFE": ("Pfizer", "Health Care"),
    "MRK": ("Merck", "Health Care"),
    "GILD": ("Gilead Sciences", "Health Care"),
    "AMGN": ("Amgen", "Health Care"),
    "UNH": ("UnitedHealth", "Health Care"),
    # Financials
    "BRK-B": ("Berkshire Hathaway", "Financials"),
    "JPM": ("JPMorgan Chase", "Financials"),
    "WFC": ("Wells Fargo", "Financials"),
    "BAC": ("Bank of America", "Financials"),
    "C": ("Citigroup", "Financials"),
    # Consumer Discretionary
    "AMZN": ("Amazon", "Consumer Discretionary"),
    "HD": ("Home Depot", "Consumer Discretionary"),
    "DIS": ("Walt Disney", "Consumer Discretionary"),
    "CMCSA": ("Comcast", "Consumer Discretionary"),
    "MCD": ("McDonald's", "Consumer Discretionary"),
    "NKE": ("Nike", "Consumer Discretionary"),
    # Consumer Staples
    "PG": ("Procter & Gamble", "Consumer Staples"),
    "KO": ("Coca-Cola", "Consumer Staples"),
    "PEP": ("PepsiCo", "Consumer Staples"),
    "WMT": ("Walmart", "Consumer Staples"),
    "PM": ("Philip Morris", "Consumer Staples"),
    # Energy
    "XOM": ("Exxon Mobil", "Energy"),
    "CVX": ("Chevron", "Energy"),
    "SLB": ("Schlumberger", "Energy"),
    "COP": ("ConocoPhillips", "Energy"),
    # Industrials
    "GE": ("General Electric", "Industrials"),
    "BA": ("Boeing", "Industrials"),
    "MMM": ("3M", "Industrials"),
    "UNP": ("Union Pacific", "Industrials"),
    "HON": ("Honeywell", "Industrials"),
    # Materials
    "PPG": ("PPG Industries", "Materials"),
    "ECL": ("Ecolab", "Materials"),
    "SHW": ("Sherwin-Williams", "Materials"),
    "APD": ("Air Products", "Materials"),
    # Utilities
    "NEE": ("NextEra Energy", "Utilities"),
    "DUK": ("Duke Energy", "Utilities"),
    "SO": ("Southern Company", "Utilities"),
    "D": ("Dominion Energy", "Utilities"),
    # Real Estate
    "SPG": ("Simon Property", "Real Estate"),
    "AMT": ("American Tower", "Real Estate"),
    "PSA": ("Public Storage", "Real Estate"),
    "CCI": ("Crown Castle", "Real Estate"),
    # Telecommunication Services
    "T": ("AT&T", "Telecommunication Services"),
    "VZ": ("Verizon", "Telecommunication Services"),
}

ETFS: dict[str, tuple[str, str]] = {
    "AGG": ("iShares Core US Aggregate Bond", "Bonds"),
    "GLD": ("SPDR Gold Shares", "Gold"),
}

CASH = "CASH"                 # synthetic asset accruing the 3-month T-bill rate
BENCHMARK = "SPY"             # not investable by the model; used for comparison

TICKERS: list[str] = list(STOCKS) + list(ETFS)          # everything priced via yfinance
ASSETS: list[str] = TICKERS + [CASH]                     # everything the model may hold

SECTOR: dict[str, str] = {t: s for t, (_, s) in {**STOCKS, **ETFS}.items()} | {CASH: "Cash"}
NAME: dict[str, str] = {t: n for t, (n, _) in {**STOCKS, **ETFS}.items()} | {CASH: "Cash (T-bills)"}
