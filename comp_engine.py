import json
import os
import re
from ebay_api_client import fetch_lowest_active_bin


def clean_title_for_search(raw_title):
    """Strips lot numbers, condition noise, and appends active negative terms from noise_rules.json."""
    if not raw_title or not isinstance(raw_title, str):
        return ""

    text = raw_title.strip()

    # Remove Lot prefix numbers
    text = re.sub(r"(?i)\blot\s*#?\d+[:\s-]*", "", text)

    # Remove condition noise
    noise_patterns = r"\b(open box|damaged box|appears new|brand new|as-is|damaged packaging|missing box|used|parts only)\b"
    text = re.sub(r"(?i)" + noise_patterns, "", text)

    # Clean characters
    text = re.sub(r"[^\w\s-]", " ", text)
    clean_text = " ".join(text.split())

    # Truncate to top 6 essential search words
    words = clean_text.split()
    if len(words) > 6:
        clean_text = " ".join(words[:6])

    # Append active negative terms from noise_rules.json
    negative_str = ""
    if os.path.exists("noise_rules.json"):
        try:
            with open("noise_rules.json", "r") as f:
                noise_list = json.load(f)
                if noise_list:
                    negative_str = " " + " ".join(
                        [f"-{term}" for term in noise_list]
                    )
        except Exception:
            pass

    return f"{clean_text}{negative_str}".strip()


def estimate_market_value(raw_title):
    """Cleans title, queries ebay_api_client with multi-pass fallback,
    and returns a (floor_price, comps) tuple across all execution paths.
    """
    cleaned_title = clean_title_for_search(raw_title)
    if not cleaned_title:
        return 0.0, []

    # Pass 1: Primary query with negative terms attached
    api_floor, comps = fetch_lowest_active_bin(cleaned_title)
    if api_floor and api_floor > 0:
        return api_floor, comps

    # Pass 2: Secondary retry using top 3 brand/product words
    core_words = " ".join(cleaned_title.split()[:3])
    if core_words and core_words != cleaned_title:
        api_floor, comps = fetch_lowest_active_bin(core_words)
        if api_floor and api_floor > 0:
            return api_floor, comps

    # Pass 3: Category Fallbacks
    title_lower = raw_title.lower()
    pricing_rules = [
        (r"tankless|water heater|boiler", 180.00),
        (r"panasonic|exhaust fan|vent fan|whisperceiling", 110.00),
        (r"faucet|shower valve|plumbing|rough-in|kohler|delta|moen", 65.00),
        (r"thermostat|nest|ecobee|honeywell", 75.00),
        (r"dewalt|milwaukee|makita|bosch|ryobi|craftsman|ridgid", 95.00),
        (r"air compressor|generator|pressure washer|inverter", 140.00),
        (r"chainsaw|lawn mower|string trimmer|leaf blower", 85.00),
        (r"mini fridge|refrigerator|freezer|ice maker", 110.00),
        (r"air purifier|dehumidifier|humidifier|dyson", 85.00),
        (r"microwave|oven|air fryer|instant pot", 60.00),
        (r"light fixture|chandelier|pendant light|led panel", 55.00),
        (r"door lock|smart lock|deadbolt|schlage|kwikset", 50.00),
        (r"vacuum|shark|bissell|hoover|robot vacuum", 70.00),
        (r"bidet|toilet seat|flush valve", 45.00),
        (r"rug|mat|runner", 40.00),
    ]

    for pattern, fallback_price in pricing_rules:
        if re.search(pattern, title_lower):
            return fallback_price, []  # Properly returns tuple (float, list)

    return 25.00, []