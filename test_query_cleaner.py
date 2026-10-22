import re

# Sample raw titles from your actual Crowe manifest
sample_titles = [
    "Lot 4012 - Panasonic FV-0511VQ1 WhisperCeiling Fan - Open Box",
    "Lot 8166 - DeWalt DCF887B 20V MAX XR 1/4 Impact Driver",
    "Lot 102 - Starbucks 24oz Cold Cup Tumbler Pink",
    "Lot 55 - Unbranded Air Purifier Filter Replacement",
]


def extract_search_query(raw_title):
    """Strips lot numbers, condition noise, and extra fluff to isolate brand and model numbers."""
    # 1. Remove Lot ID headers
    clean = re.sub(r"^Lot\s*\d+\s*[-:]?\s*", "", raw_title, flags=re.I)

    # 2. Remove common auction condition clutter
    noise_words = [
        r"\bopen box\b",
        r"\bdamaged box\b",
        r"\buntested\b",
        r"\bnib\b",
        r"\bnew\b",
        r"\bused\b",
        r"\bas is\b",
    ]
    for pattern in noise_words:
        clean = re.sub(pattern, "", clean, flags=re.I)

    # 3. Clean up leftover whitespace and dash artifacts
    clean = re.sub(r"\s+", " ", clean).strip(" -:")

    return clean


if __name__ == "__main__":
    print("--- TITLE CLEANER VERIFICATION ---")
    for raw in sample_titles:
        print(f"RAW  : {raw}")
        print(f"CLEAN: {extract_search_query(raw)}\n")