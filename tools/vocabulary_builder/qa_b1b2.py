import json
import re
from pathlib import Path
from collections import Counter, defaultdict


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"

INPUT_FILE = OUTPUT_DIR / "b1b2_clean.json"

REPORT_FILE = OUTPUT_DIR / "b1b2_qa_report.txt"
SUSPICIOUS_FILE = OUTPUT_DIR / "b1b2_qa_suspicious.json"
DUPLICATES_FILE = OUTPUT_DIR / "b1b2_qa_duplicates.json"


# ============================================================
# SETTINGS
# ============================================================

EXPECTED_COUNT = 6164
EXPECTED_LEVEL = "B1-B2"
EXPECTED_CHAPTERS = set(range(1, 19))

REQUIRED_FIELDS = [
    "id",
    "swedish",
    "forms",
    "english",
    "level",
    "chapter",
    "page",
    "source",
    "source_pdf_page",
    "parse_method",
]


# Characters which commonly indicate PDF extraction problems
BAD_CHARACTERS = {
    "\u00ad": "soft hyphen",
    "\u200b": "zero width space",
    "\ufffd": "replacement character",
    "\x00": "NULL character",
}


# Things that are suspicious if they appear literally
SUSPICIOUS_TEXT_PATTERNS = [
    (r"\bnull\b", "literal NULL"),
    (r"\bnone\b", "literal NONE"),
    (r"\bnan\b", "literal NAN"),
    (r"\bundefined\b", "literal UNDEFINED"),
]


# ============================================================
# HELPERS
# ============================================================

def load_json(path):
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with path.open("w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )


def normalize_text(value):
    if not isinstance(value, str):
        return ""

    return " ".join(value.strip().split()).casefold()


def short_card(card):
    return {
        "id": card.get("id"),
        "swedish": card.get("swedish"),
        "forms": card.get("forms"),
        "english": card.get("english"),
        "chapter": card.get("chapter"),
        "page": card.get("page"),
        "source_pdf_page": card.get("source_pdf_page"),
        "parse_method": card.get("parse_method"),
    }


def add_issue(issues, category, card, reason):
    issues.append({
        "category": category,
        "reason": reason,
        "card": short_card(card),
    })


# ============================================================
# STRUCTURAL QA
# ============================================================

def check_structure(cards):
    errors = []
    warnings = []

    if not isinstance(cards, list):
        errors.append("Top-level JSON is not a list.")
        return errors, warnings

    if len(cards) != EXPECTED_COUNT:
        errors.append(
            f"Expected {EXPECTED_COUNT} cards, found {len(cards)}."
        )

    ids = []

    for index, card in enumerate(cards):

        if not isinstance(card, dict):
            errors.append(
                f"Card index {index} is not an object."
            )
            continue

        missing_fields = [
            field
            for field in REQUIRED_FIELDS
            if field not in card
        ]

        if missing_fields:
            errors.append(
                f"Card index {index} missing fields: "
                f"{missing_fields}"
            )

        card_id = card.get("id")

        if not card_id:
            errors.append(
                f"Card index {index} has no ID."
            )
        else:
            ids.append(card_id)

        if not isinstance(card.get("swedish"), str):
            errors.append(
                f"{card_id}: Swedish is not a string."
            )

        if not isinstance(card.get("english"), str):
            errors.append(
                f"{card_id}: English is not a string."
            )

        if not isinstance(card.get("forms"), str):
            errors.append(
                f"{card_id}: forms is not a string."
            )

        if card.get("level") != EXPECTED_LEVEL:
            errors.append(
                f"{card_id}: unexpected level "
                f"{card.get('level')!r}."
            )

        chapter = card.get("chapter")

        if chapter not in EXPECTED_CHAPTERS:
            errors.append(
                f"{card_id}: invalid chapter {chapter!r}."
            )

        pdf_page = card.get("source_pdf_page")

        if not isinstance(pdf_page, int):
            errors.append(
                f"{card_id}: invalid source_pdf_page "
                f"{pdf_page!r}."
            )

        page = card.get("page")

        # page=None is allowed for introductory vocabulary
        if page is not None and not isinstance(page, int):
            errors.append(
                f"{card_id}: invalid page {page!r}."
            )

    id_counts = Counter(ids)

    duplicate_ids = [
        card_id
        for card_id, count in id_counts.items()
        if count > 1
    ]

    if duplicate_ids:
        errors.append(
            f"Duplicate IDs: {duplicate_ids}"
        )

    return errors, warnings


# ============================================================
# EMPTY DATA
# ============================================================

def check_empty_fields(cards):
    issues = []

    for card in cards:

        swedish = card.get("swedish")
        english = card.get("english")

        if isinstance(swedish, str) and not swedish.strip():
            add_issue(
                issues,
                "EMPTY_SWEDISH",
                card,
                "Swedish field is empty.",
            )

        if isinstance(english, str) and not english.strip():
            add_issue(
                issues,
                "EMPTY_ENGLISH",
                card,
                "English field is empty.",
            )

    return issues


# ============================================================
# PDF / TEXT ARTIFACTS
# ============================================================

def check_text_artifacts(cards):
    issues = []

    for card in cards:

        for field in ("swedish", "forms", "english"):

            value = card.get(field)

            if not isinstance(value, str):
                continue

            # --------------------------------------------
            # invisible / broken Unicode characters
            # --------------------------------------------

            for char, name in BAD_CHARACTERS.items():

                if char in value:
                    add_issue(
                        issues,
                        "BAD_CHARACTER",
                        card,
                        f"{field}: contains {name}.",
                    )

            # --------------------------------------------
            # tabs / newlines
            # --------------------------------------------

            if "\n" in value or "\r" in value or "\t" in value:
                add_issue(
                    issues,
                    "WHITESPACE_ARTIFACT",
                    card,
                    f"{field}: contains newline/tab.",
                )

            # --------------------------------------------
            # repeated whitespace
            # --------------------------------------------

            if re.search(r" {2,}", value):
                add_issue(
                    issues,
                    "DOUBLE_SPACE",
                    card,
                    f"{field}: repeated spaces.",
                )

            # --------------------------------------------
            # suspicious literal values
            # --------------------------------------------

            normalized = normalize_text(value)

            for pattern, description in SUSPICIOUS_TEXT_PATTERNS:

                if re.search(pattern, normalized):
                    add_issue(
                        issues,
                        "SUSPICIOUS_TEXT",
                        card,
                        f"{field}: {description}.",
                    )

            # --------------------------------------------
            # suspicious unfinished hyphenated word
            #
            # Example:
            # identifica-
            # --------------------------------------------

            if re.search(r"[A-Za-zÅÄÖåäö]{3,}-$", value.strip()):
                add_issue(
                    issues,
                    "TRAILING_HYPHEN",
                    card,
                    f"{field}: possible broken word.",
                )

    return issues


# ============================================================
# SUSPICIOUS SHORT TEXT
# ============================================================

def check_short_values(cards):
    issues = []

    for card in cards:

        swedish = card.get("swedish", "").strip()
        english = card.get("english", "").strip()

        # One-letter vocabulary is possible, so this is only
        # a review flag, not an error.

        if len(swedish) == 1:
            add_issue(
                issues,
                "VERY_SHORT_SWEDISH",
                card,
                "Swedish contains only one character.",
            )

        if len(english) == 1:
            add_issue(
                issues,
                "VERY_SHORT_ENGLISH",
                card,
                "English contains only one character.",
            )

    return issues


# ============================================================
# SUSPICIOUS PARSE METHODS
# ============================================================

def check_parse_methods(cards):
    issues = []

    method_counts = Counter(
        card.get("parse_method")
        for card in cards
    )

    known_methods = {
        "UNICODE_SEPARATOR",
        "MORPHOLOGY_FALLBACK",
        "MANUAL_REVIEW_FIXED",
        "MANUAL_REVIEW",
    }

    for card in cards:

        method = card.get("parse_method")

        if method not in known_methods:
            add_issue(
                issues,
                "UNKNOWN_PARSE_METHOD",
                card,
                f"Unknown parse method: {method!r}",
            )

    return issues, method_counts


# ============================================================
# DUPLICATES
# ============================================================

def find_duplicates(cards):
    """
    We intentionally do NOT automatically treat the same Swedish
    spelling as a duplicate.

    Homographs and different senses are valid.

    Instead we produce several groups for manual inspection.
    """

    exact_groups = defaultdict(list)
    same_sw_en_groups = defaultdict(list)
    same_swedish_groups = defaultdict(list)

    for card in cards:

        sw = normalize_text(card.get("swedish"))
        forms = normalize_text(card.get("forms"))
        en = normalize_text(card.get("english"))

        exact_key = (
            sw,
            forms,
            en,
        )

        sw_en_key = (
            sw,
            en,
        )

        exact_groups[exact_key].append(card)
        same_sw_en_groups[sw_en_key].append(card)
        same_swedish_groups[sw].append(card)

    exact_duplicates = []

    for key, group in exact_groups.items():

        if len(group) > 1:
            exact_duplicates.append({
                "swedish": key[0],
                "forms": key[1],
                "english": key[2],
                "count": len(group),
                "cards": [
                    short_card(card)
                    for card in group
                ],
            })

    same_sw_en = []

    for key, group in same_sw_en_groups.items():

        if len(group) > 1:
            same_sw_en.append({
                "swedish": key[0],
                "english": key[1],
                "count": len(group),
                "cards": [
                    short_card(card)
                    for card in group
                ],
            })

    same_swedish = []

    for swedish, group in same_swedish_groups.items():

        if len(group) > 1:
            same_swedish.append({
                "swedish": swedish,
                "count": len(group),
                "cards": [
                    short_card(card)
                    for card in group
                ],
            })

    exact_duplicates.sort(
        key=lambda x: (-x["count"], x["swedish"])
    )

    same_sw_en.sort(
        key=lambda x: (-x["count"], x["swedish"])
    )

    same_swedish.sort(
        key=lambda x: (-x["count"], x["swedish"])
    )

    return {
        "exact_duplicates": exact_duplicates,
        "same_swedish_and_english": same_sw_en,
        "same_swedish_any_meaning": same_swedish,
    }


# ============================================================
# CHAPTER / PAGE QA
# ============================================================

def check_distribution(cards):
    chapter_counts = Counter()
    pdf_page_counts = Counter()

    pages_per_chapter = defaultdict(list)

    for card in cards:

        chapter = card.get("chapter")
        page = card.get("page")
        pdf_page = card.get("source_pdf_page")

        chapter_counts[chapter] += 1
        pdf_page_counts[pdf_page] += 1

        if isinstance(page, int):
            pages_per_chapter[chapter].append(page)

    chapter_info = {}

    for chapter in sorted(chapter_counts):

        pages = pages_per_chapter.get(chapter, [])

        chapter_info[chapter] = {
            "cards": chapter_counts[chapter],
            "min_book_page": min(pages) if pages else None,
            "max_book_page": max(pages) if pages else None,
        }

    return chapter_info, pdf_page_counts


# ============================================================
# MANUAL REVIEW QA
# ============================================================

def check_manual_cards(cards):
    manual_fixed = []
    manual_added = []

    for card in cards:

        method = card.get("parse_method")

        if method == "MANUAL_REVIEW_FIXED":
            manual_fixed.append(short_card(card))

        elif method == "MANUAL_REVIEW":
            manual_added.append(short_card(card))

    return manual_fixed, manual_added


# ============================================================
# REPORT
# ============================================================

def build_report(
    cards,
    structural_errors,
    structural_warnings,
    issues,
    duplicates,
    method_counts,
    chapter_info,
    manual_fixed,
    manual_added,
):
    lines = []

    lines.append("=" * 78)
    lines.append("B1-B2 FINAL QA REPORT")
    lines.append("=" * 78)
    lines.append("")

    lines.append("SUMMARY")
    lines.append("-" * 78)

    lines.append(
        f"Total cards:                 {len(cards)}"
    )

    lines.append(
        f"Structural errors:           {len(structural_errors)}"
    )

    lines.append(
        f"Structural warnings:         {len(structural_warnings)}"
    )

    lines.append(
        f"Suspicious records:          {len(issues)}"
    )

    lines.append(
        f"Exact duplicate groups:      "
        f"{len(duplicates['exact_duplicates'])}"
    )

    lines.append(
        f"Same SW+EN groups:           "
        f"{len(duplicates['same_swedish_and_english'])}"
    )

    lines.append(
        f"Same Swedish groups:         "
        f"{len(duplicates['same_swedish_any_meaning'])}"
    )

    lines.append(
        f"Manual fixed cards:          {len(manual_fixed)}"
    )

    lines.append(
        f"Manual added cards:          {len(manual_added)}"
    )

    # ========================================================
    # STRUCTURE
    # ========================================================

    lines.append("")
    lines.append("STRUCTURAL ERRORS")
    lines.append("-" * 78)

    if structural_errors:
        lines.extend(structural_errors)
    else:
        lines.append("NONE")

    lines.append("")
    lines.append("STRUCTURAL WARNINGS")
    lines.append("-" * 78)

    if structural_warnings:
        lines.extend(structural_warnings)
    else:
        lines.append("NONE")

    # ========================================================
    # PARSE METHODS
    # ========================================================

    lines.append("")
    lines.append("PARSE METHODS")
    lines.append("-" * 78)

    for method, count in sorted(
        method_counts.items(),
        key=lambda x: str(x[0]),
    ):
        lines.append(
            f"{str(method):30} {count}"
        )

    # ========================================================
    # CHAPTERS
    # ========================================================

    lines.append("")
    lines.append("CHAPTER DISTRIBUTION")
    lines.append("-" * 78)

    for chapter in sorted(chapter_info):

        info = chapter_info[chapter]

        lines.append(
            f"Chapter {chapter:>2}: "
            f"{info['cards']:>4} cards | "
            f"book pages "
            f"{info['min_book_page']} - "
            f"{info['max_book_page']}"
        )

    # ========================================================
    # ISSUE TYPES
    # ========================================================

    issue_counts = Counter(
        issue["category"]
        for issue in issues
    )

    lines.append("")
    lines.append("SUSPICIOUS RECORD TYPES")
    lines.append("-" * 78)

    if issue_counts:

        for category, count in issue_counts.most_common():
            lines.append(
                f"{category:30} {count}"
            )

    else:
        lines.append("NONE")

    # ========================================================
    # EXACT DUPLICATES
    # ========================================================

    lines.append("")
    lines.append("EXACT DUPLICATE GROUPS")
    lines.append("-" * 78)

    if duplicates["exact_duplicates"]:

        for group in duplicates["exact_duplicates"]:

            lines.append("")
            lines.append(
                f"{group['swedish']} | "
                f"{group['english']} | "
                f"count={group['count']}"
            )

            for card in group["cards"]:

                lines.append(
                    f"  {card['id']} | "
                    f"ch {card['chapter']} | "
                    f"page {card['page']} | "
                    f"PDF {card['source_pdf_page']}"
                )

    else:
        lines.append("NONE")

    # ========================================================
    # MANUAL REVIEW
    # ========================================================

    lines.append("")
    lines.append("MANUAL REVIEW CHECK")
    lines.append("-" * 78)

    lines.append(
        f"MANUAL_REVIEW_FIXED: {len(manual_fixed)}"
    )

    lines.append(
        f"MANUAL_REVIEW:       {len(manual_added)}"
    )

    lines.append("")
    lines.append("=" * 78)

    if structural_errors:
        lines.append(
            "RESULT: FAIL - structural errors found."
        )
    else:
        lines.append(
            "RESULT: STRUCTURE OK - inspect QA candidate files."
        )

    lines.append("=" * 78)

    return "\n".join(lines)


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 78)
    print("B1-B2 FINAL QA")
    print("=" * 78)
    print()

    print("Loading:")
    print(INPUT_FILE)
    print()

    cards = load_json(INPUT_FILE)

    print(f"Cards loaded: {len(cards)}")
    print()

    # --------------------------------------------------------
    # STRUCTURE
    # --------------------------------------------------------

    print("1/7 Checking structure...")

    structural_errors, structural_warnings = (
        check_structure(cards)
    )

    # --------------------------------------------------------
    # EMPTY DATA
    # --------------------------------------------------------

    print("2/7 Checking empty fields...")

    issues = check_empty_fields(cards)

    # --------------------------------------------------------
    # TEXT
    # --------------------------------------------------------

    print("3/7 Checking text/PDF artifacts...")

    issues.extend(
        check_text_artifacts(cards)
    )

    # --------------------------------------------------------
    # SHORT VALUES
    # --------------------------------------------------------

    print("4/7 Checking suspicious short values...")

    issues.extend(
        check_short_values(cards)
    )

    # --------------------------------------------------------
    # PARSE METHODS
    # --------------------------------------------------------

    print("5/7 Checking parse methods...")

    parse_issues, method_counts = (
        check_parse_methods(cards)
    )

    issues.extend(parse_issues)

    # --------------------------------------------------------
    # DUPLICATES
    # --------------------------------------------------------

    print("6/7 Checking duplicates...")

    duplicates = find_duplicates(cards)

    # --------------------------------------------------------
    # DISTRIBUTION
    # --------------------------------------------------------

    print("7/7 Checking chapter/page distribution...")

    chapter_info, pdf_page_counts = (
        check_distribution(cards)
    )

    manual_fixed, manual_added = (
        check_manual_cards(cards)
    )

    # --------------------------------------------------------
    # OUTPUT
    # --------------------------------------------------------

    report = build_report(
        cards,
        structural_errors,
        structural_warnings,
        issues,
        duplicates,
        method_counts,
        chapter_info,
        manual_fixed,
        manual_added,
    )

    REPORT_FILE.write_text(
        report,
        encoding="utf-8",
    )

    save_json(
        SUSPICIOUS_FILE,
        issues,
    )

    save_json(
        DUPLICATES_FILE,
        duplicates,
    )

    print()
    print("=" * 78)
    print("QA COMPLETE")
    print("=" * 78)
    print()

    print(f"Structural errors:  {len(structural_errors)}")
    print(f"Suspicious records: {len(issues)}")

    print(
        "Exact duplicate groups:",
        len(duplicates["exact_duplicates"]),
    )

    print(
        "Same SW+EN groups:     ",
        len(duplicates["same_swedish_and_english"]),
    )

    print(
        "Same Swedish groups:   ",
        len(duplicates["same_swedish_any_meaning"]),
    )

    print()

    print(
        "Manual fixed cards: ",
        len(manual_fixed),
    )

    print(
        "Manual added cards: ",
        len(manual_added),
    )

    print()

    print("Created:")
    print(REPORT_FILE)
    print(SUSPICIOUS_FILE)
    print(DUPLICATES_FILE)
    print()

    if structural_errors:

        print(
            "RESULT: FAIL - structural errors must be fixed."
        )

    else:

        print(
            "RESULT: STRUCTURE OK"
        )

        print(
            "Next step: inspect suspicious records and "
            "duplicate groups."
        )

    print()


if __name__ == "__main__":
    main()