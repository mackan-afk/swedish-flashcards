from pathlib import Path
from collections import defaultdict
import json
import re


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"

RAW_FILE = OUTPUT_DIR / "b1b2_raw_v2.json"
REJECTED_FILE = OUTPUT_DIR / "b1b2_rejected_v2.json"

AUDIT_FILE = OUTPUT_DIR / "b1b2_audit_v2.txt"
DUPLICATES_FILE = OUTPUT_DIR / "b1b2_duplicates_v2.json"
SUSPICIOUS_FILE = OUTPUT_DIR / "b1b2_suspicious_v2.json"


# ============================================================
# HELPERS
# ============================================================

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )


def normalize(text):
    return re.sub(
        r"\s+",
        " ",
        text.strip().casefold(),
    )


# ============================================================
# SUSPICIOUS CARD DETECTION
# ============================================================

def suspicious_reasons(card):

    reasons = []

    swedish = card.get("swedish", "")
    english = card.get("english", "")
    forms = card.get("forms", "")

    # --------------------------------------------------------
    # Missing metadata
    # --------------------------------------------------------

    if card.get("page") is None:
        reasons.append("NO_PAGE")

    if card.get("chapter") is None:
        reasons.append("NO_CHAPTER")

    # --------------------------------------------------------
    # Morphology still inside Swedish field
    #
    # Examples:
    # ta (-r, tog, tagit) tid
    # hitta (-r, -de, -t) på
    # --------------------------------------------------------

    if "(" in swedish or ")" in swedish:
        reasons.append("FORMS_INSIDE_SWEDISH")

    # --------------------------------------------------------
    # Suspicious parentheses mismatch
    # --------------------------------------------------------

    if swedish.count("(") != swedish.count(")"):
        reasons.append("BROKEN_PARENTHESES_SWEDISH")

    if english.count("(") != english.count(")"):
        reasons.append("BROKEN_PARENTHESES_ENGLISH")

    # --------------------------------------------------------
    # Empty fields
    # --------------------------------------------------------

    if not swedish.strip():
        reasons.append("EMPTY_SWEDISH")

    if not english.strip():
        reasons.append("EMPTY_ENGLISH")

    # --------------------------------------------------------
    # Very short translations
    #
    # We do NOT delete them.
    # This is only a QA flag.
    # --------------------------------------------------------

    if len(english.strip()) <= 2:
        reasons.append("VERY_SHORT_ENGLISH")

    # --------------------------------------------------------
    # Translation probably cut at line/page boundary
    #
    # Examples seen in V2:
    # mother in
    # Easter eve, holy
    #
    # These endings are suspicious, not automatically wrong.
    # --------------------------------------------------------

    suspicious_endings = (
        " in",
        " of",
        " to",
        " the",
        " a",
        " an",
        " and",
        " or",
        " with",
        " for",
        " from",
        " on",
        " at",
        " by",
        " into",
        " about",
        " as",
        " one’s",
        " one's",
    )

    english_normalized = english.strip().casefold()

    if any(
        english_normalized.endswith(x)
        for x in suspicious_endings
    ):
        reasons.append("POSSIBLY_CUT_ENGLISH")

    # --------------------------------------------------------
    # Hyphenation artifacts
    # --------------------------------------------------------

    if "\u00ad" in english or "\u00ad" in swedish:
        reasons.append("SOFT_HYPHEN")

    if english.endswith("-"):
        reasons.append("ENGLISH_ENDS_HYPHEN")

    if swedish.endswith("-"):
        reasons.append("SWEDISH_ENDS_HYPHEN")

    # --------------------------------------------------------
    # Strange morphology
    # --------------------------------------------------------

    if forms:

        if forms.count("(") or forms.count(")"):
            reasons.append("PARENTHESES_INSIDE_FORMS")

        if len(forms) > 80:
            reasons.append("VERY_LONG_FORMS")

    # --------------------------------------------------------
    # Extremely long entries
    # --------------------------------------------------------

    if len(swedish) > 120:
        reasons.append("VERY_LONG_SWEDISH")

    if len(english) > 180:
        reasons.append("VERY_LONG_ENGLISH")

    return reasons


# ============================================================
# DUPLICATES
# ============================================================

def find_duplicates(cards):

    groups = defaultdict(list)

    for card in cards:

        key = (
            normalize(card["swedish"]),
            normalize(card["english"]),
        )

        groups[key].append(card)

    duplicates = []

    for key, group in groups.items():

        if len(group) > 1:

            duplicates.append(
                {
                    "swedish": group[0]["swedish"],
                    "english": group[0]["english"],
                    "count": len(group),
                    "cards": group,
                }
            )

    duplicates.sort(
        key=lambda x: (
            -x["count"],
            x["swedish"].casefold(),
        )
    )

    return duplicates


# ============================================================
# MAIN AUDIT
# ============================================================

def main():

    cards = load_json(RAW_FILE)
    rejected = load_json(REJECTED_FILE)

    print("=" * 72)
    print("SVENSKAKORT - B1/B2 FULL V2 AUDIT")
    print("=" * 72)

    print()
    print(f"Cards:          {len(cards)}")
    print(f"Rejected rows:  {len(rejected)}")

    # --------------------------------------------------------
    # Suspicious cards
    # --------------------------------------------------------

    suspicious = []

    reason_counts = defaultdict(int)

    for card in cards:

        reasons = suspicious_reasons(card)

        if reasons:

            suspicious.append(
                {
                    "reasons": reasons,
                    "card": card,
                }
            )

            for reason in reasons:
                reason_counts[reason] += 1

    # --------------------------------------------------------
    # Duplicates
    # --------------------------------------------------------

    duplicates = find_duplicates(cards)

    # --------------------------------------------------------
    # Save machine-readable files
    # --------------------------------------------------------

    save_json(
        SUSPICIOUS_FILE,
        suspicious,
    )

    save_json(
        DUPLICATES_FILE,
        duplicates,
    )

    # --------------------------------------------------------
    # Human-readable report
    # --------------------------------------------------------

    lines = []

    lines.append("=" * 72)
    lines.append("SVENSKAKORT - B1/B2 FULL V2 AUDIT")
    lines.append("=" * 72)
    lines.append("")

    lines.append(f"TOTAL CARDS: {len(cards)}")
    lines.append(f"REJECTED ROWS: {len(rejected)}")
    lines.append(f"SUSPICIOUS CARDS: {len(suspicious)}")
    lines.append(f"DUPLICATE GROUPS: {len(duplicates)}")

    lines.append("")
    lines.append("=" * 72)
    lines.append("SUSPICIOUS REASON COUNTS")
    lines.append("=" * 72)

    for reason, count in sorted(
        reason_counts.items(),
        key=lambda x: (-x[1], x[0]),
    ):
        lines.append(
            f"{reason:30} {count}"
        )

    # --------------------------------------------------------
    # Suspicious cards
    # --------------------------------------------------------

    lines.append("")
    lines.append("=" * 72)
    lines.append("ALL SUSPICIOUS CARDS")
    lines.append("=" * 72)

    for index, item in enumerate(
        suspicious,
        start=1,
    ):

        card = item["card"]

        lines.append("")
        lines.append(
            f"{index:04}. "
            f"{card['id']} "
            f"[{', '.join(item['reasons'])}]"
        )

        lines.append(
            f"      SV:    {card['swedish']}"
        )

        lines.append(
            f"      FORMS: {card['forms']}"
        )

        lines.append(
            f"      EN:    {card['english']}"
        )

        lines.append(
            f"      CHAPTER: {card['chapter']} "
            f"PAGE: {card['page']} "
            f"PDF: {card['source_pdf_page']}"
        )

    # --------------------------------------------------------
    # Duplicate groups
    # --------------------------------------------------------

    lines.append("")
    lines.append("=" * 72)
    lines.append("ALL EXACT DUPLICATE GROUPS")
    lines.append("=" * 72)

    for index, group in enumerate(
        duplicates,
        start=1,
    ):

        lines.append("")
        lines.append(
            f"{index:04}. "
            f"{group['swedish']} -> "
            f"{group['english']} "
            f"[{group['count']}x]"
        )

        for card in group["cards"]:

            lines.append(
                f"      {card['id']} | "
                f"chapter={card['chapter']} | "
                f"page={card['page']} | "
                f"pdf={card['source_pdf_page']} | "
                f"forms={card['forms']}"
            )

    # --------------------------------------------------------
    # Rejected rows
    # --------------------------------------------------------

    lines.append("")
    lines.append("=" * 72)
    lines.append("ALL REJECTED ROWS")
    lines.append("=" * 72)

    for index, item in enumerate(
        rejected,
        start=1,
    ):

        lines.append("")
        lines.append(
            f"{index:04}. "
            f"PDF={item.get('source_pdf_page')} "
            f"COLUMN={item.get('column')} "
            f"Y={item.get('y')} "
            f"CHAPTER={item.get('chapter')} "
            f"PAGE={item.get('page')}"
        )

        lines.append(
            f"      {item.get('text')}"
        )

    with open(
        AUDIT_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        f.write(
            "\n".join(lines)
        )

    # --------------------------------------------------------
    # Terminal summary
    # --------------------------------------------------------

    print()
    print("=" * 72)
    print("RESULT")
    print("=" * 72)

    print(
        f"Suspicious cards:   {len(suspicious)}"
    )

    print(
        f"Duplicate groups:   {len(duplicates)}"
    )

    print()
    print("Suspicious reasons:")

    for reason, count in sorted(
        reason_counts.items(),
        key=lambda x: (-x[1], x[0]),
    ):

        print(
            f"  {reason:30} {count}"
        )

    print()
    print("Created:")
    print(f"  {AUDIT_FILE}")
    print(f"  {SUSPICIOUS_FILE}")
    print(f"  {DUPLICATES_FILE}")

    print()
    print("=" * 72)
    print("DONE")
    print("=" * 72)


if __name__ == "__main__":
    main()