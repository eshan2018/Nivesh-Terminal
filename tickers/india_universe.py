# ================================================================
# NIVESH TERMINAL — INDIAN MARKET UNIVERSE
# 100 Nifty 100 constituents + 10 NSE-listed ETFs
# Source: Nifty 100 index as of April 2026
# All tickers use Yahoo Finance .NS suffix (data via yfinance)
# ================================================================

INDIA_UNIVERSE = [

    # ════════════════════════════════════════════════════════
    # BANKING & FINANCE (25 stocks)
    # Backbone of Indian economy — most liquid, most tracked
    # ════════════════════════════════════════════════════════
    {"ticker": "HDFCBANK.NS",    "name": "HDFC Bank",              "category": "Stabilizer",  "type": "equity",  "sector": "Banking",          "tier": "Nifty 100"},
    {"ticker": "ICICIBANK.NS",   "name": "ICICI Bank",             "category": "Stabilizer",  "type": "equity",  "sector": "Banking",          "tier": "Nifty 100"},
    {"ticker": "KOTAKBANK.NS",   "name": "Kotak Mahindra Bank",    "category": "Stabilizer",  "type": "equity",  "sector": "Banking",          "tier": "Nifty 100"},
    {"ticker": "AXISBANK.NS",    "name": "Axis Bank",              "category": "Stabilizer",  "type": "equity",  "sector": "Banking",          "tier": "Nifty 100"},
    {"ticker": "SBIN.NS",        "name": "State Bank of India",    "category": "Stabilizer",  "type": "equity",  "sector": "Banking",          "tier": "Nifty 100"},
    {"ticker": "BAJFINANCE.NS",  "name": "Bajaj Finance",          "category": "High Growth", "type": "equity",  "sector": "NBFC",             "tier": "Nifty 100"},
    {"ticker": "BAJAJFINSV.NS",  "name": "Bajaj Finserv",          "category": "High Growth", "type": "equity",  "sector": "NBFC",             "tier": "Nifty 100"},
    {"ticker": "SBILIFE.NS",     "name": "SBI Life Insurance",     "category": "Stabilizer",  "type": "equity",  "sector": "Insurance",        "tier": "Nifty 100"},
    {"ticker": "HDFCLIFE.NS",    "name": "HDFC Life Insurance",    "category": "Stabilizer",  "type": "equity",  "sector": "Insurance",        "tier": "Nifty 100"},
    {"ticker": "ICICIPRULI.NS",  "name": "ICICI Prudential Life",  "category": "Stabilizer",  "type": "equity",  "sector": "Insurance",        "tier": "Nifty 100"},
    {"ticker": "ICICIGI.NS",     "name": "ICICI Lombard General",  "category": "Stabilizer",  "type": "equity",  "sector": "Insurance",        "tier": "Nifty 100"},
    {"ticker": "SHRIRAMFIN.NS",  "name": "Shriram Finance",        "category": "High Growth", "type": "equity",  "sector": "NBFC",             "tier": "Nifty 100"},
    {"ticker": "CHOLAFIN.NS",    "name": "Cholamandalam Finance",  "category": "High Growth", "type": "equity",  "sector": "NBFC",             "tier": "Nifty 100"},
    {"ticker": "MUTHOOTFIN.NS",  "name": "Muthoot Finance",        "category": "High Growth", "type": "equity",  "sector": "NBFC",             "tier": "Nifty 100"},
    {"ticker": "PFC.NS",         "name": "Power Finance Corp",     "category": "Stabilizer",  "type": "equity",  "sector": "Finance",          "tier": "Nifty 100"},
    {"ticker": "RECLTD.NS",      "name": "REC Limited",            "category": "Stabilizer",  "type": "equity",  "sector": "Finance",          "tier": "Nifty 100"},
    {"ticker": "CDSL.NS",        "name": "CDSL",                   "category": "High Growth", "type": "equity",  "sector": "Capital Markets",  "tier": "Nifty 100"},
    {"ticker": "POLICYBZR.NS",   "name": "PB Fintech",             "category": "High Growth", "type": "equity",  "sector": "Fintech",          "tier": "Nifty 100"},
    {"ticker": "PAYTM.NS",       "name": "Paytm (One97 Comm)",     "category": "High Growth", "type": "equity",  "sector": "Fintech",          "tier": "Nifty 100"},
    {"ticker": "JIOFIN.NS",      "name": "Jio Financial Services", "category": "High Growth", "type": "equity",  "sector": "Fintech",          "tier": "Nifty 100"},
    {"ticker": "BANKINDIA.NS",   "name": "Bank of India",          "category": "Stabilizer",  "type": "equity",  "sector": "Banking",          "tier": "Nifty 100"},
    {"ticker": "CANBK.NS",       "name": "Canara Bank",            "category": "Stabilizer",  "type": "equity",  "sector": "Banking",          "tier": "Nifty 100"},
    {"ticker": "FEDERALBNK.NS",  "name": "Federal Bank",           "category": "Stabilizer",  "type": "equity",  "sector": "Banking",          "tier": "Nifty 100"},
    {"ticker": "INDUSINDBK.NS",  "name": "IndusInd Bank",          "category": "Stabilizer",  "type": "equity",  "sector": "Banking",          "tier": "Nifty 100"},
    {"ticker": "BANDHANBNK.NS",  "name": "Bandhan Bank",           "category": "High Growth", "type": "equity",  "sector": "Banking",          "tier": "Nifty 100"},

    # ════════════════════════════════════════════════════════
    # IT & TECHNOLOGY (15 stocks)
    # India's global export engine — USD revenue = INR hedge
    # ════════════════════════════════════════════════════════
    {"ticker": "TCS.NS",         "name": "Tata Consultancy",       "category": "Stabilizer",  "type": "equity",  "sector": "IT Services",      "tier": "Nifty 100"},
    {"ticker": "INFY.NS",        "name": "Infosys",                "category": "Stabilizer",  "type": "equity",  "sector": "IT Services",      "tier": "Nifty 100"},
    {"ticker": "HCLTECH.NS",     "name": "HCL Technologies",       "category": "Stabilizer",  "type": "equity",  "sector": "IT Services",      "tier": "Nifty 100"},
    {"ticker": "WIPRO.NS",       "name": "Wipro",                  "category": "Stabilizer",  "type": "equity",  "sector": "IT Services",      "tier": "Nifty 100"},
    {"ticker": "TECHM.NS",       "name": "Tech Mahindra",          "category": "Stabilizer",  "type": "equity",  "sector": "IT Services",      "tier": "Nifty 100"},
    {"ticker": "LTIM.NS",        "name": "LTIMindtree",            "category": "High Growth", "type": "equity",  "sector": "IT Services",      "tier": "Nifty 100"},
    {"ticker": "PERSISTENT.NS",  "name": "Persistent Systems",     "category": "High Growth", "type": "equity",  "sector": "IT Services",      "tier": "Nifty 100"},
    {"ticker": "COFORGE.NS",     "name": "Coforge",                "category": "High Growth", "type": "equity",  "sector": "IT Services",      "tier": "Nifty 100"},
    {"ticker": "MPHASIS.NS",     "name": "Mphasis",                "category": "High Growth", "type": "equity",  "sector": "IT Services",      "tier": "Nifty 100"},
    {"ticker": "HAPPSTMNDS.NS",  "name": "Happiest Minds",         "category": "High Growth", "type": "equity",  "sector": "IT Services",      "tier": "Nifty 100"},
    {"ticker": "OFSS.NS",        "name": "Oracle Financial Svcs",  "category": "Stabilizer",  "type": "equity",  "sector": "IT Services",      "tier": "Nifty 100"},
    {"ticker": "KPITTECH.NS",    "name": "KPIT Technologies",      "category": "High Growth", "type": "equity",  "sector": "IT Services",      "tier": "Nifty 100"},
    {"ticker": "TATAELXSI.NS",   "name": "Tata Elxsi",             "category": "High Growth", "type": "equity",  "sector": "IT Services",      "tier": "Nifty 100"},
    {"ticker": "DIXON.NS",       "name": "Dixon Technologies",     "category": "High Growth", "type": "equity",  "sector": "Electronics",      "tier": "Nifty 100"},
    {"ticker": "ZOMATO.NS",      "name": "Eternal (Zomato)",       "category": "High Growth", "type": "equity",  "sector": "Consumer Tech",    "tier": "Nifty 100"},

    # ════════════════════════════════════════════════════════
    # CONSUMER & FMCG (12 stocks)
    # Defensive — India's consumption story is multi-decade
    # ════════════════════════════════════════════════════════
    {"ticker": "HINDUNILVR.NS",  "name": "Hindustan Unilever",     "category": "Stabilizer",  "type": "equity",  "sector": "FMCG",             "tier": "Nifty 100"},
    {"ticker": "NESTLEIND.NS",   "name": "Nestle India",           "category": "Stabilizer",  "type": "equity",  "sector": "FMCG",             "tier": "Nifty 100"},
    {"ticker": "BRITANNIA.NS",   "name": "Britannia Industries",   "category": "Stabilizer",  "type": "equity",  "sector": "FMCG",             "tier": "Nifty 100"},
    {"ticker": "DABUR.NS",       "name": "Dabur India",            "category": "Stabilizer",  "type": "equity",  "sector": "FMCG",             "tier": "Nifty 100"},
    {"ticker": "MARICO.NS",      "name": "Marico",                 "category": "Stabilizer",  "type": "equity",  "sector": "FMCG",             "tier": "Nifty 100"},
    {"ticker": "TATACONSUM.NS",  "name": "Tata Consumer Products", "category": "Stabilizer",  "type": "equity",  "sector": "FMCG",             "tier": "Nifty 100"},
    {"ticker": "ITC.NS",         "name": "ITC Limited",            "category": "Stabilizer",  "type": "equity",  "sector": "FMCG",             "tier": "Nifty 100"},
    {"ticker": "COLPAL.NS",      "name": "Colgate-Palmolive India","category": "Stabilizer",  "type": "equity",  "sector": "FMCG",             "tier": "Nifty 100"},
    {"ticker": "TITAN.NS",       "name": "Titan Company",          "category": "High Growth", "type": "equity",  "sector": "Consumer",         "tier": "Nifty 100"},
    {"ticker": "TRENT.NS",       "name": "Trent (Zudio)",          "category": "High Growth", "type": "equity",  "sector": "Retail",           "tier": "Nifty 100"},
    {"ticker": "DMART.NS",       "name": "Avenue Supermarts (DMart)","category":"High Growth","type": "equity",  "sector": "Retail",           "tier": "Nifty 100"},
    {"ticker": "NYKAA.NS",       "name": "Nykaa (FSN E-Commerce)", "category": "High Growth", "type": "equity",  "sector": "E-Commerce",       "tier": "Nifty 100"},

    # ════════════════════════════════════════════════════════
    # HEALTHCARE & PHARMA (10 stocks)
    # Recession-proof — India is the pharmacy of the world
    # ════════════════════════════════════════════════════════
    {"ticker": "SUNPHARMA.NS",   "name": "Sun Pharmaceutical",     "category": "Stabilizer",  "type": "equity",  "sector": "Pharma",           "tier": "Nifty 100"},
    {"ticker": "DRREDDY.NS",     "name": "Dr Reddy's Labs",        "category": "Stabilizer",  "type": "equity",  "sector": "Pharma",           "tier": "Nifty 100"},
    {"ticker": "CIPLA.NS",       "name": "Cipla",                  "category": "Stabilizer",  "type": "equity",  "sector": "Pharma",           "tier": "Nifty 100"},
    {"ticker": "DIVISLAB.NS",    "name": "Divi's Laboratories",    "category": "High Growth", "type": "equity",  "sector": "Pharma",           "tier": "Nifty 100"},
    {"ticker": "APOLLOHOSP.NS",  "name": "Apollo Hospitals",       "category": "High Growth", "type": "equity",  "sector": "Healthcare",       "tier": "Nifty 100"},
    {"ticker": "TORNTPHARM.NS",  "name": "Torrent Pharma",         "category": "Stabilizer",  "type": "equity",  "sector": "Pharma",           "tier": "Nifty 100"},
    {"ticker": "AUROPHARMA.NS",  "name": "Aurobindo Pharma",       "category": "Stabilizer",  "type": "equity",  "sector": "Pharma",           "tier": "Nifty 100"},
    {"ticker": "LUPIN.NS",       "name": "Lupin",                  "category": "Stabilizer",  "type": "equity",  "sector": "Pharma",           "tier": "Nifty 100"},
    {"ticker": "MAXHEALTH.NS",   "name": "Max Healthcare",         "category": "High Growth", "type": "equity",  "sector": "Healthcare",       "tier": "Nifty 100"},
    {"ticker": "FORTIS.NS",      "name": "Fortis Healthcare",      "category": "High Growth", "type": "equity",  "sector": "Healthcare",       "tier": "Nifty 100"},

    # ════════════════════════════════════════════════════════
    # INDUSTRIAL, INFRA & ENERGY (15 stocks)
    # India's capex supercycle — govt spending tailwind
    # ════════════════════════════════════════════════════════
    {"ticker": "RELIANCE.NS",    "name": "Reliance Industries",    "category": "Stabilizer",  "type": "equity",  "sector": "Conglomerate",     "tier": "Nifty 100"},
    {"ticker": "LT.NS",          "name": "Larsen & Toubro",        "category": "Stabilizer",  "type": "equity",  "sector": "Engineering",      "tier": "Nifty 100"},
    {"ticker": "SIEMENS.NS",     "name": "Siemens India",          "category": "High Growth", "type": "equity",  "sector": "Engineering",      "tier": "Nifty 100"},
    {"ticker": "ABB.NS",         "name": "ABB India",              "category": "High Growth", "type": "equity",  "sector": "Engineering",      "tier": "Nifty 100"},
    {"ticker": "NTPC.NS",        "name": "NTPC",                   "category": "Stabilizer",  "type": "equity",  "sector": "Power",            "tier": "Nifty 100"},
    {"ticker": "POWERGRID.NS",   "name": "Power Grid Corp",        "category": "Safe Haven",  "type": "equity",  "sector": "Power",            "tier": "Nifty 100"},
    {"ticker": "ADANIGREEN.NS",  "name": "Adani Green Energy",     "category": "High Growth", "type": "equity",  "sector": "Renewable Energy", "tier": "Nifty 100"},
    {"ticker": "ADANIPORTS.NS",  "name": "Adani Ports & SEZ",      "category": "Stabilizer",  "type": "equity",  "sector": "Infrastructure",   "tier": "Nifty 100"},
    {"ticker": "ADANIENT.NS",    "name": "Adani Enterprises",      "category": "High Growth", "type": "equity",  "sector": "Conglomerate",     "tier": "Nifty 100"},
    {"ticker": "TATAPOWER.NS",   "name": "Tata Power",             "category": "High Growth", "type": "equity",  "sector": "Power",            "tier": "Nifty 100"},
    {"ticker": "IRCTC.NS",       "name": "IRCTC",                  "category": "High Growth", "type": "equity",  "sector": "Travel & Tourism", "tier": "Nifty 100"},
    {"ticker": "RAILTEL.NS",     "name": "RailTel Corporation",    "category": "High Growth", "type": "equity",  "sector": "Telecom Infra",    "tier": "Nifty 100"},
    {"ticker": "HAL.NS",         "name": "Hindustan Aeronautics",  "category": "High Growth", "type": "equity",  "sector": "Defence",          "tier": "Nifty 100"},
    {"ticker": "BEL.NS",         "name": "Bharat Electronics",     "category": "High Growth", "type": "equity",  "sector": "Defence",          "tier": "Nifty 100"},
    {"ticker": "BHEL.NS",        "name": "Bharat Heavy Electricals","category":"Stabilizer",  "type": "equity",  "sector": "Engineering",      "tier": "Nifty 100"},

    # ════════════════════════════════════════════════════════
    # MATERIALS, METALS & CHEMICALS (10 stocks)
    # Commodity cycle plays + specialty chemicals boom
    # ════════════════════════════════════════════════════════
    {"ticker": "TATASTEEL.NS",   "name": "Tata Steel",             "category": "High Growth", "type": "equity",  "sector": "Metals",           "tier": "Nifty 100"},
    {"ticker": "JSWSTEEL.NS",    "name": "JSW Steel",              "category": "High Growth", "type": "equity",  "sector": "Metals",           "tier": "Nifty 100"},
    {"ticker": "HINDALCO.NS",    "name": "Hindalco Industries",    "category": "Stabilizer",  "type": "equity",  "sector": "Metals",           "tier": "Nifty 100"},
    {"ticker": "COALINDIA.NS",   "name": "Coal India",             "category": "Stabilizer",  "type": "equity",  "sector": "Mining",           "tier": "Nifty 100"},
    {"ticker": "ASIANPAINT.NS",  "name": "Asian Paints",           "category": "Stabilizer",  "type": "equity",  "sector": "Chemicals",        "tier": "Nifty 100"},
    {"ticker": "PIDILITIND.NS",  "name": "Pidilite Industries",    "category": "Stabilizer",  "type": "equity",  "sector": "Chemicals",        "tier": "Nifty 100"},
    {"ticker": "GRASIM.NS",      "name": "Grasim Industries",      "category": "Stabilizer",  "type": "equity",  "sector": "Materials",        "tier": "Nifty 100"},
    {"ticker": "ULTRACEMCO.NS",  "name": "UltraTech Cement",       "category": "Stabilizer",  "type": "equity",  "sector": "Cement",           "tier": "Nifty 100"},
    {"ticker": "SHREECEM.NS",    "name": "Shree Cement",           "category": "Stabilizer",  "type": "equity",  "sector": "Cement",           "tier": "Nifty 100"},
    {"ticker": "ONGC.NS",        "name": "ONGC",                   "category": "Stabilizer",  "type": "equity",  "sector": "Oil & Gas",        "tier": "Nifty 100"},

    # ════════════════════════════════════════════════════════
    # AUTOMOBILES (8 stocks)
    # EV transition + premiumisation trend in India
    # ════════════════════════════════════════════════════════
    {"ticker": "TATAMOTORS.NS",  "name": "Tata Motors",            "category": "High Growth", "type": "equity",  "sector": "Automobiles",      "tier": "Nifty 100"},
    {"ticker": "MARUTI.NS",      "name": "Maruti Suzuki",          "category": "Stabilizer",  "type": "equity",  "sector": "Automobiles",      "tier": "Nifty 100"},
    {"ticker": "M&M.NS",         "name": "Mahindra & Mahindra",    "category": "High Growth", "type": "equity",  "sector": "Automobiles",      "tier": "Nifty 100"},
    {"ticker": "BAJAJ-AUTO.NS",  "name": "Bajaj Auto",             "category": "Stabilizer",  "type": "equity",  "sector": "Automobiles",      "tier": "Nifty 100"},
    {"ticker": "HEROMOTOCO.NS",  "name": "Hero MotoCorp",          "category": "Stabilizer",  "type": "equity",  "sector": "Automobiles",      "tier": "Nifty 100"},
    {"ticker": "EICHERMOT.NS",   "name": "Eicher Motors",          "category": "High Growth", "type": "equity",  "sector": "Automobiles",      "tier": "Nifty 100"},
    {"ticker": "TVSMOTOR.NS",    "name": "TVS Motor Company",      "category": "High Growth", "type": "equity",  "sector": "Automobiles",      "tier": "Nifty 100"},
    {"ticker": "BOSCHLTD.NS",    "name": "Bosch India",            "category": "Stabilizer",  "type": "equity",  "sector": "Auto Components",  "tier": "Nifty 100"},

    # ════════════════════════════════════════════════════════
    # TELECOM & MEDIA (3 stocks)
    # ════════════════════════════════════════════════════════
    {"ticker": "BHARTIARTL.NS",  "name": "Bharti Airtel",          "category": "Stabilizer",  "type": "equity",  "sector": "Telecom",          "tier": "Nifty 100"},
    {"ticker": "INDIAMART.NS",   "name": "IndiaMART InterMESH",    "category": "High Growth", "type": "equity",  "sector": "B2B Tech",         "tier": "Nifty 100"},
    {"ticker": "ZEEL.NS",        "name": "Zee Entertainment",      "category": "Stabilizer",  "type": "equity",  "sector": "Media",            "tier": "Nifty 100"},

    # ════════════════════════════════════════════════════════
    # REAL ESTATE (2 stocks)
    # ════════════════════════════════════════════════════════
    {"ticker": "DLF.NS",         "name": "DLF Limited",            "category": "High Growth", "type": "equity",  "sector": "Real Estate",      "tier": "Nifty 100"},
    {"ticker": "OBEROIRLTY.NS",  "name": "Oberoi Realty",          "category": "High Growth", "type": "equity",  "sector": "Real Estate",      "tier": "Nifty 100"},

    # ════════════════════════════════════════════════════════
    # NSE ETFs — Top 10 for Indian Investors
    # Best for SIP, low cost, liquid, tax-efficient
    # ════════════════════════════════════════════════════════
    {"ticker": "NIFTYBEES.NS",   "name": "Nippon Nifty BeES",      "category": "Stabilizer",  "type": "etf",  "sector": "Index ETF",        "tier": "ETF"},
    {"ticker": "JUNIORBEES.NS",  "name": "Nippon Junior BeES",     "category": "High Growth", "type": "etf",  "sector": "Index ETF",        "tier": "ETF"},
    {"ticker": "BANKBEES.NS",    "name": "Nippon Bank BeES",       "category": "Stabilizer",  "type": "etf",  "sector": "Sector ETF",       "tier": "ETF"},
    {"ticker": "GOLDBEES.NS",    "name": "Nippon Gold BeES",       "category": "Safe Haven",  "type": "etf",  "sector": "Commodity ETF",    "tier": "ETF"},
    {"ticker": "MON100.NS",      "name": "Motilal Nasdaq 100 ETF", "category": "High Growth", "type": "etf",  "sector": "Global ETF",       "tier": "ETF"},
    {"ticker": "MAFANG.NS",      "name": "Mirae FANG+ ETF",        "category": "High Growth", "type": "etf",  "sector": "Global ETF",       "tier": "ETF"},
    {"ticker": "SETFNN50.NS",    "name": "SBI Nifty Next 50 ETF",  "category": "High Growth", "type": "etf",  "sector": "Index ETF",        "tier": "ETF"},
    {"ticker": "ICICIB22.NS",    "name": "ICICI Bharat 22 ETF",    "category": "Stabilizer",  "type": "etf",  "sector": "Index ETF",        "tier": "ETF"},
    {"ticker": "ITBEES.NS",      "name": "Nippon IT BeES",         "category": "High Growth", "type": "etf",  "sector": "Sector ETF",       "tier": "ETF"},
    {"ticker": "PHARMABEES.NS",  "name": "Nippon Pharma BeES",     "category": "Stabilizer",  "type": "etf",  "sector": "Sector ETF",       "tier": "ETF"},
]

# ── Helper metadata ──────────────────────────────────────────
INDIA_TICKERS = [a["ticker"] for a in INDIA_UNIVERSE]
INDIA_META    = {a["ticker"]: a for a in INDIA_UNIVERSE}

def is_inr_native(ticker: str) -> bool:
    """All Indian tickers are INR-native — no conversion needed."""
    return True  # Every ticker in this universe is .NS or ^ Indian index

def get_india_platform(ticker: str) -> str:
    """Which app to use to buy this asset."""
    if ticker.startswith("^"):
        return "Benchmark (not investable)"
    elif ticker in [a["ticker"] for a in INDIA_UNIVERSE if a["tier"] == "ETF"]:
        return "Zerodha / Groww / Kite"
    else:
        return "Zerodha / Groww / Upstox"
