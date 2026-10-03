from pathlib import Path
import json
from collections import Counter


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"

RAW_FILE = OUTPUT_DIR / "b1b2_raw.json"
REJECTED_FILE = OUTPUT_DIR / "b1b2_rejected.json"


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    cards = load_json(RAW_FILE)
    rejected = load_json(REJECTED_FILE)

    print("=" * 70)
    print("SVENSKAKORT - B1/B2 PARSER ANALYSIS")
    print("=" * 70)

    print()
    print(f"Accepted cards: {len(cards)}")
    print(f"Rejected lines: {len(rejected)}")

    # ========================================================
    # ACCEPTED PER CHAPTER
    # ========================================================

    chapter_counts = Counter(
        card["chapter"] for card in cards
    )

    print()
    print("=" * 70)
    print("ACCEPTED CARDS PER CHAPTER")
    print("=" * 70)

    for chapter in sorted(chapter_counts):
        print(
            f"Chapter {chapter:2}: "
            f"{chapter_counts[chapter]:4} cards"
        )

    # ========================================================
    # REJECTED PER CHAPTER
    # ========================================================

    rejected_counts = Counter(
        item["chapter"] for item in rejected
    )

    print()
    print("=" * 70)
    print("REJECTED LINES PER CHAPTER")
    print("=" * 70)

    for chapter in sorted(
        rejected_counts,
        key=lambda x: (x is None, x if x is not None else 999)
    ):
        print(
            f"Chapter {str(chapter):>4}: "
            f"{rejected_counts[chapter]:4} lines"
        )

    # ========================================================
    # SAMPLE REJECTED LINES
    # ========================================================

    print()
    print("=" * 70)
    print("FIRST 100 REJECTED LINES")
    print("=" * 70)

    for i, item in enumerate(rejected[:100], start=1):

        print(
            f"{i:03}. "
            f"[chapter={item['chapter']} "
            f"book_page={item['page']} "
            f"pdf_page={item['source_pdf_page']}]"
        )

        print(f"     {item['text']}")

    # ========================================================
    # SUSPICIOUS ACCEPTED CARDS
    # ========================================================

    suspicious = []

    for card in cards:

        reasons = []

        if card["page"] is None:
            reasons.append("NO_PAGE")

        if len(card["swedish"]) > 80:
            reasons.append("LONG_SWEDISH")

        if len(card["english"]) > 120:
            reasons.append("LONG_ENGLISH")

        if card["swedish"].lower().startswith("sidan "):
            reasons.append("PAGE_AS_WORD")

        if card["swedish"].lower().startswith("kapitel "):
            reasons.append("CHAPTER_AS_WORD")

        if "ordlista" in card["swedish"].lower():
            reasons.append("HEADER")

        if reasons:
            suspicious.append(
                {
                    "card": card,
                    "reasons": reasons,
                }
            )

    print()
    print("=" * 70)
    print("SUSPICIOUS ACCEPTED CARDS")
    print("=" * 70)

    print(f"Total suspicious: {len(suspicious)}")

    for i, item in enumerate(suspicious[:50], start=1):

        card = item["card"]

        print()
        print(
            f"{i:03}. {card['id']} "
            f"[{', '.join(item['reasons'])}]"
        )

        print(
            f"     SV: {card['swedish']}"
        )

        print(
            f"     FORMS: {card['forms']}"
        )

        print(
            f"     EN: {card['english']}"
        )

        print(
            f"     chapter={card['chapter']} "
            f"page={card['page']} "
            f"pdf_page={card['source_pdf_page']}"
        )

    print()
    print("=" * 70)
    print("DONE")
    print("=" * 70)


if __name__ == "__main__":
    main()