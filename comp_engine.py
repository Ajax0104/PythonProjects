import re
from ebay_api_client import fetch_lowest_active_bin


def clean_title_for_search(raw_title):
    """Strips lot numbers, condition noise, and limits title to top search terms."""
    if not raw_title or not isinstance(raw_title, str):
        return ""

    text = raw_title.strip()

    # Remove Lot prefix numbers (e.g., "Lot 104 -", "Lot #12:")
    text = re.sub(r"(?i)\blot\s*#?\d+[:\s-]*", "", text)

    # Remove condition noise that skews search engine results
    noise_patterns = r"\b(open box|damaged box|appears new|brand new|as-is|damaged packaging|missing box|used|parts only)\b"
    text = re.sub(r"(?i)" + noise_patterns, "", text)

    # Remove special characters, keep letters, numbers, spaces, and hyphens
    text = re.sub(r"[^\w\s-]", " ", text)

    # Collapse spaces
    clean_text = " ".join(text.split())

    # Truncate to top 6 essential search words if title is overly verbose
    words = clean_text.split()
    if len(words) > 6:
        clean_text = " ".join(words[:6])

    return clean_text


def estimate_market_value(raw_title):
    """Cleans title, queries ebay_api_client with multi-pass fallback,

    and applies expanded rule tables if API yields $0.
    """
    cleaned_title = clean_title_for_search(raw_title)
    if not cleaned_title:
        return 0.0, []

    # Pass 1: Primary query to eBay API Client using clean search title
    api_floor, comps = fetch_lowest_active_bin(cleaned_title)

    if api_floor and api_floor > 0:
        return api_floor, comps

    # Pass 2: Secondary retry using top 3 brand/product words if full title returned $0
    core_words = " ".join(cleaned_title.split()[:3])
    if core_words and core_words != cleaned_title:
        api_floor, comps = fetch_lowest_active_bin(core_words)

        if api_floor and api_floor > 0:
            return api_floor, comps

    # Pass 3: Expanded Hardware & Liquidation Category Fallbacks
    title_lower = raw_title.lower()
    pricing_rules = [
        # HVAC, Water Heaters & Plumbing
        (r"tankless|water heater|boiler", 180.00),
        (r"panasonic|exhaust fan|vent fan|whisperceiling", 110.00),
        (r"faucet|shower valve|plumbing|rough-in|kohler|delta|moen", 65.00),
        (r"thermostat|nest|ecobee|honeywell", 75.00),
        # Power Tools & Outdoor Equipment
        (r"dewalt|milwaukee|makita|bosch|ryobi|craftsman|ridgid", 95.00),
        (r"air compressor|generator|pressure washer|inverter", 140.00),
        (r"chainsaw|lawn mower|string trimmer|leaf blower", 85.00),
        # Appliances & Air Quality
        (r"mini fridge|refrigerator|freezer|ice maker", 110.00),
        (r"air purifier|dehumidifier|humidifier|dyson", 85.00),
        (r"microwave|oven|air fryer|instant pot", 60.00),
        # Home Improvement & General Liquidation
        (r"light fixture|chandelier|pendant light|led panel", 55.00),
        (r"door lock|smart lock|deadbolt|schlage|kwikset", 50.00),
        (r"vacuum|shark|bissell|hoover|robot vacuum", 70.00),
        (r"bidet|toilet seat|flush valve", 45.00),
        (r"rug|mat|runner", 40.00),
    ]

    for pattern, fallback_price in pricing_rules:
        if re.search(pattern, title_lower):
            return fallback_price

    return 25.00, []