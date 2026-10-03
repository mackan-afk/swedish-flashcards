from pathlib import Path
import shutil


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

PARSER_PATH = BASE_DIR / "parse_b1b2.py"
V51_BACKUP_PATH = BASE_DIR / "parse_b1b2_v51_backup.py"
V52_BACKUP_PATH = BASE_DIR / "parse_b1b2_v52_backup.py"


# ============================================================
# HELPERS
# ============================================================

def replace_once(text, old, new, description):

    count = text.count(old)

    if count != 1:
        raise RuntimeError(
            f"\nCould not safely apply patch:\n"
            f"{description}\n\n"
            f"Expected exactly 1 occurrence, found {count}.\n"
            f"No V5.3 parser has been written."
        )

    return text.replace(old, new, 1)


def replace_section(
    text,
    start_marker,
    end_marker,
    replacement,
    description,
):

    start = text.find(start_marker)

    if start == -1:
        raise RuntimeError(
            f"\nCould not find start marker for:\n"
            f"{description}"
        )

    end = text.find(
        end_marker,
        start + len(start_marker),
    )

    if end == -1:
        raise RuntimeError(
            f"\nCould not find end marker for:\n"
            f"{description}"
        )

    return (
        text[:start]
        + replacement.rstrip()
        + "\n\n\n"
        + text[end:]
    )


# ============================================================
# V5.3 SAFE MORPHOLOGY CHECK
# ============================================================

V53_SAFE_HELPERS = r'''
# ============================================================
# V5.3 SAFE QA HELPERS
# ============================================================

def morphology_fallback_is_suspicious_v53(parsed):
    """
    Prevent known false parsing such as:

        ringa (-r, -de, -t) in

    becoming:

        Swedish: ringa
        English: in

    or:

        lura (-r, -de, -t) till sig

    becoming:

        Swedish: lura till
        English: sig

    We do NOT try to repair these automatically.
    They go to manual review.
    """

    if parsed is None:
        return False

    if (
        parsed.get("method")
        != "MORPHOLOGY_FALLBACK"
    ):
        return False

    english = (
        parsed.get("english", "")
        .strip()
        .casefold()
    )

    suspicious_single_tokens = {
        "in",
        "ut",
        "upp",
        "ner",
        "ned",
        "på",
        "av",
        "om",
        "till",
        "med",
        "över",
        "under",
        "fram",
        "bort",
        "hem",
        "igen",
        "ihop",
        "sig",
        "mig",
        "dig",
        "oss",
        "er",
    }

    return (
        english
        in suspicious_single_tokens
    )


def compact_card_for_review(card):
    """
    Store only useful context in the manual-review file.
    """

    if card is None:
        return None

    return {
        "id": card.get("id"),
        "swedish": card.get("swedish", ""),
        "forms": card.get("forms", ""),
        "english": card.get("english", ""),
        "chapter": card.get("chapter"),
        "page": card.get("page"),
        "source_pdf_page": card.get(
            "source_pdf_page"
        ),
    }


def make_manual_review_item(
    row,
    reason,
    source_pdf_page,
    chapter,
    book_page,
    previous_card=None,
    next_row=None,
    attempted_parse=None,
):
    """
    Create a rich QA item without inventing a correction.
    """

    item = {
        "status": "REVIEW",
        "reason": reason,
        "source_pdf_page": source_pdf_page,
        "column": row.get("column"),
        "chapter": chapter,
        "page": book_page,
        "y": row.get("y"),
        "raw": row.get("raw", ""),
        "previous_card": (
            compact_card_for_review(
                previous_card
            )
        ),
        "next_row": (
            next_row.get("raw", "")
            if next_row is not None
            else None
        ),
    }

    if attempted_parse is not None:
        item["attempted_parse"] = {
            "swedish": attempted_parse.get(
                "swedish",
                "",
            ),
            "forms": attempted_parse.get(
                "forms",
                "",
            ),
            "english": attempted_parse.get(
                "english",
                "",
            ),
            "method": attempted_parse.get(
                "method",
                "",
            ),
        }

    return item
'''


# ============================================================
# V5.3 PARSER
# ============================================================

V53_PARSER = r'''
def parse_pdf():

    doc = pymupdf.open(
        PDF_PATH
    )

    cards = []
    rejected = []
    qa_events = []
    manual_review = []

    current_chapter = None
    current_book_page = None

    previous_card = None

    for pdf_page_index, page in enumerate(
        doc
    ):

        source_pdf_page = (
            pdf_page_index + 1
        )

        rows = get_visual_lines(
            page
        )

        # ----------------------------------------------------
        # KEEP THE SUCCESSFUL V5 BROKEN-ROW REPAIR
        # ----------------------------------------------------

        rows, repair_events = (
            repair_broken_rows(
                rows
            )
        )

        for event in repair_events:

            event[
                "source_pdf_page"
            ] = source_pdf_page

            qa_events.append(
                event
            )

        # ----------------------------------------------------
        # Preserve the normal PDF reading structure:
        # left column, then right column.
        #
        # No V5.2 prejoining.
        # No automatic local-gap splitting.
        # ----------------------------------------------------

        left_rows = [
            row
            for row in rows
            if row["column"] == "left"
        ]

        right_rows = [
            row
            for row in rows
            if row["column"] == "right"
        ]

        ordered_rows = (
            left_rows
            + right_rows
        )

        for row_index, row in enumerate(
            ordered_rows
        ):

            raw = row["raw"]

            clean = normalize_basic(
                raw
            )

            if not clean:
                continue

            # --------------------------------------------
            # NEXT ROW CONTEXT FOR MANUAL QA
            # --------------------------------------------

            next_row = None

            if (
                row_index + 1
                < len(ordered_rows)
            ):
                next_row = ordered_rows[
                    row_index + 1
                ]

            # --------------------------------------------
            # CHAPTER
            # --------------------------------------------

            chapter = detect_chapter(
                clean
            )

            if chapter is not None:

                current_chapter = chapter
                continue

            # --------------------------------------------
            # TEXTBOOK PAGE
            # --------------------------------------------

            book_page = detect_book_page(
                clean
            )

            if book_page is not None:

                current_book_page = (
                    book_page
                )

                continue

            # --------------------------------------------
            # NOISE
            # --------------------------------------------

            if is_header_or_noise(
                clean
            ):
                continue

            # --------------------------------------------
            # STANDARD V5.1 PARSING
            #
            # This keeps the reliable Unicode separator
            # parsing and morphology parsing.
            # --------------------------------------------

            parsed = (
                parse_vocabulary_row(
                    row
                )
            )

            # --------------------------------------------
            # KNOWN DANGEROUS MORPHOLOGY CASE
            # --------------------------------------------

            if (
                parsed is not None
                and morphology_fallback_is_suspicious_v53(
                    parsed
                )
            ):

                manual_review.append(
                    make_manual_review_item(
                        row=row,
                        reason=(
                            "SUSPICIOUS_MORPHOLOGY_FALLBACK"
                        ),
                        source_pdf_page=(
                            source_pdf_page
                        ),
                        chapter=(
                            current_chapter
                        ),
                        book_page=(
                            current_book_page
                        ),
                        previous_card=(
                            previous_card
                        ),
                        next_row=(
                            next_row
                        ),
                        attempted_parse=(
                            parsed
                        ),
                    )
                )

                qa_events.append(
                    {
                        "type": (
                            "REJECTED_SUSPICIOUS_MORPHOLOGY"
                        ),
                        "source_pdf_page": (
                            source_pdf_page
                        ),
                        "column": row[
                            "column"
                        ],
                        "chapter": (
                            current_chapter
                        ),
                        "page": (
                            current_book_page
                        ),
                        "raw": raw,
                        "swedish": parsed[
                            "swedish"
                        ],
                        "forms": parsed[
                            "forms"
                        ],
                        "english": parsed[
                            "english"
                        ],
                    }
                )

                rejected.append(
                    {
                        "reason": (
                            "SUSPICIOUS_MORPHOLOGY_FALLBACK"
                        ),
                        "raw": raw,
                        "chapter": (
                            current_chapter
                        ),
                        "page": (
                            current_book_page
                        ),
                        "source_pdf_page": (
                            source_pdf_page
                        ),
                        "column": row[
                            "column"
                        ],
                        "y": row[
                            "y"
                        ],
                    }
                )

                continue

            # --------------------------------------------
            # ACCEPT NORMAL CARD
            # --------------------------------------------

            if parsed is not None:

                card = {
                    "id": None,
                    "swedish": parsed[
                        "swedish"
                    ],
                    "forms": parsed[
                        "forms"
                    ],
                    "english": parsed[
                        "english"
                    ],
                    "level": LEVEL,
                    "chapter": (
                        current_chapter
                    ),
                    "page": (
                        current_book_page
                    ),
                    "source": SOURCE,
                    "source_pdf_page": (
                        source_pdf_page
                    ),
                    "parse_method": (
                        parsed["method"]
                    ),
                }

                cards.append(
                    card
                )

                if (
                    parsed["method"]
                    == "MORPHOLOGY_FALLBACK"
                ):

                    qa_events.append(
                        {
                            "type": (
                                "MORPHOLOGY_FALLBACK"
                            ),
                            "source_pdf_page": (
                                source_pdf_page
                            ),
                            "column": row[
                                "column"
                            ],
                            "chapter": (
                                current_chapter
                            ),
                            "page": (
                                current_book_page
                            ),
                            "raw": raw,
                            "swedish": card[
                                "swedish"
                            ],
                            "forms": card[
                                "forms"
                            ],
                            "english": card[
                                "english"
                            ],
                        }
                    )

                previous_card = card

                continue

            # --------------------------------------------
            # UNRESOLVED -> MANUAL REVIEW
            #
            # We deliberately do not guess.
            # --------------------------------------------

            rejected_item = {
                "reason": (
                    "UNRESOLVED_ROW"
                ),
                "raw": raw,
                "chapter": (
                    current_chapter
                ),
                "page": (
                    current_book_page
                ),
                "source_pdf_page": (
                    source_pdf_page
                ),
                "column": row[
                    "column"
                ],
                "y": row[
                    "y"
                ],
            }

            rejected.append(
                rejected_item
            )

            manual_review.append(
                make_manual_review_item(
                    row=row,
                    reason=(
                        "UNRESOLVED_ROW"
                    ),
                    source_pdf_page=(
                        source_pdf_page
                    ),
                    chapter=(
                        current_chapter
                    ),
                    book_page=(
                        current_book_page
                    ),
                    previous_card=(
                        previous_card
                    ),
                    next_row=(
                        next_row
                    ),
                )
            )

    doc.close()

    # --------------------------------------------------------
    # FINAL CLEANUP
    # --------------------------------------------------------

    for card in cards:

        card["swedish"] = (
            clean_output_text(
                card["swedish"]
            )
        )

        card["forms"] = (
            normalize_forms(
                card["forms"]
            )
        )

        card["english"] = (
            clean_output_text(
                card["english"]
            )
        )

    # --------------------------------------------------------
    # TEMPORARY IDs
    # --------------------------------------------------------

    for i, card in enumerate(
        cards,
        start=1,
    ):

        card["id"] = (
            f"riv_b_{i:04d}"
        )

    return (
        cards,
        rejected,
        qa_events,
        manual_review,
    )
'''


# ============================================================
# APPLY UPGRADE
# ============================================================

def main():

    # --------------------------------------------------------
    # REQUIRE V5.1 BACKUP
    # --------------------------------------------------------

    if not V51_BACKUP_PATH.exists():

        raise FileNotFoundError(
            "\nV5.1 backup not found:\n"
            f"{V51_BACKUP_PATH}\n\n"
            "Do not continue automatically."
        )

    if not PARSER_PATH.exists():

        raise FileNotFoundError(
            f"Current parser not found:\n"
            f"{PARSER_PATH}"
        )

    # --------------------------------------------------------
    # SAVE CURRENT V5.2
    # --------------------------------------------------------

    shutil.copy2(
        PARSER_PATH,
        V52_BACKUP_PATH,
    )

    print(
        f"V5.2 backup created:\n"
        f"{V52_BACKUP_PATH}\n"
    )

    # --------------------------------------------------------
    # LOAD V5.1 AS CLEAN BASE
    # --------------------------------------------------------

    source = V51_BACKUP_PATH.read_text(
        encoding="utf-8"
    )

    required_markers = [
        "SVENSKAKORT - B1/B2 PARSER V5.1",
        'b1b2_raw_v51.json',
        'b1b2_rejected_v51.json',
        'b1b2_qa_v51.json',
        "def repair_broken_rows(",
        "def parse_pdf():",
        "def run_qa(",
        "def main():",
    ]

    missing = [
        marker
        for marker in required_markers
        if marker not in source
    ]

    if missing:

        raise RuntimeError(
            "\nThe backup does not look like "
            "the expected V5.1 parser.\n"
            "Missing markers:\n"
            + "\n".join(
                f"  - {item}"
                for item in missing
            )
        )

    print(
        "V5.1 backup verified."
    )

    print(
        "Using V5.1 as the clean V5.3 base.\n"
    )

    # --------------------------------------------------------
    # OUTPUT FILENAMES
    # --------------------------------------------------------

    source = replace_once(
        source,
        'OUTPUT_JSON = OUTPUT_DIR / "b1b2_raw_v51.json"',
        'OUTPUT_JSON = OUTPUT_DIR / "b1b2_raw_v53.json"',
        "V5.3 raw output",
    )

    source = replace_once(
        source,
        'REJECTED_JSON = OUTPUT_DIR / "b1b2_rejected_v51.json"',
        'REJECTED_JSON = OUTPUT_DIR / "b1b2_rejected_v53.json"',
        "V5.3 rejected output",
    )

    source = replace_once(
        source,
        'QA_JSON = OUTPUT_DIR / "b1b2_qa_v51.json"',
        'QA_JSON = OUTPUT_DIR / "b1b2_qa_v53.json"',
        "V5.3 QA output",
    )

    # --------------------------------------------------------
    # ADD MANUAL REVIEW OUTPUT CONSTANT
    # --------------------------------------------------------

    old = '''QA_JSON = OUTPUT_DIR / "b1b2_qa_v53.json"'''

    new = '''QA_JSON = OUTPUT_DIR / "b1b2_qa_v53.json"
MANUAL_REVIEW_JSON = OUTPUT_DIR / "b1b2_manual_review_v53.json"'''

    source = replace_once(
        source,
        old,
        new,
        "V5.3 manual-review output path",
    )

    # --------------------------------------------------------
    # INSERT SAFE HELPERS BEFORE parse_pdf()
    # --------------------------------------------------------

    parser_pos = source.find(
        "def parse_pdf():"
    )

    if parser_pos == -1:

        raise RuntimeError(
            "\nCould not find parse_pdf() "
            "in V5.1 backup."
        )

    source = (
        source[:parser_pos]
        + V53_SAFE_HELPERS.rstrip()
        + "\n\n\n"
        + source[parser_pos:]
    )

    # --------------------------------------------------------
    # REPLACE parse_pdf()
    # --------------------------------------------------------

    source = replace_section(
        source,
        "def parse_pdf():",
        "# ============================================================\n# QA\n# ============================================================",
        V53_PARSER,
        "V5.3 parse_pdf",
    )

    # --------------------------------------------------------
    # VERSION TITLE
    # --------------------------------------------------------

    source = replace_once(
        source,
        '"SVENSKAKORT - B1/B2 PARSER V5.1"',
        '"SVENSKAKORT - B1/B2 PARSER V5.3"',
        "V5.3 title",
    )

    # --------------------------------------------------------
    # MODIFY main() CALL
    # --------------------------------------------------------

    old = '''    (
        cards,
        rejected,
        qa_events,
    ) = parse_pdf()'''

    new = '''    (
        cards,
        rejected,
        qa_events,
        manual_review,
    ) = parse_pdf()'''

    source = replace_once(
        source,
        old,
        new,
        "V5.3 parse_pdf return values",
    )

        # --------------------------------------------------------
    # WRITE MANUAL REVIEW JSON
    #
    # V5.1 uses the existing save_json() helper.
    # Insert manual review directly after rejected JSON.
    # --------------------------------------------------------

    old = '''    save_json(
        REJECTED_JSON,
        rejected,
    )'''

    new = '''    save_json(
        REJECTED_JSON,
        rejected,
    )

    save_json(
        MANUAL_REVIEW_JSON,
        manual_review,
    )'''

    source = replace_once(
        source,
        old,
        new,
        "V5.3 manual review JSON writing",
    )

    # --------------------------------------------------------
    # REPORT MANUAL REVIEW COUNT
    # --------------------------------------------------------

    marker = '''    print(
        f"Rejected rows:            "
        f"{len(rejected)}"
    )'''

    replacement = '''    print(
        f"Rejected rows:            "
        f"{len(rejected)}"
    )

    print(
        f"Manual review items:      "
        f"{len(manual_review)}"
    )'''

    source = replace_once(
        source,
        marker,
        replacement,
        "V5.3 manual-review count",
    )

        # --------------------------------------------------------
    # OUTPUT FILE LIST
    # --------------------------------------------------------

    old = '''    print(OUTPUT_JSON)
    print(REJECTED_JSON)
    print(QA_JSON)'''

    new = '''    print(OUTPUT_JSON)
    print(REJECTED_JSON)
    print(QA_JSON)
    print(MANUAL_REVIEW_JSON)'''

    source = replace_once(
        source,
        old,
        new,
        "V5.3 output file list",
    )

    # --------------------------------------------------------
    # WRITE NEW PARSER
    # --------------------------------------------------------

    PARSER_PATH.write_text(
        source,
        encoding="utf-8",
    )

    print("=" * 72)
    print(
        "SVENSKAKORT V5.2 -> V5.3 UPGRADE COMPLETE"
    )
    print("=" * 72)

    print()
    print(
        "IMPORTANT:"
    )

    print(
        "  V5.3 was rebuilt from the clean "
        "V5.1 backup."
    )

    print(
        "  V5.2 automatic prejoining has "
        "NOT been carried over."
    )

    print()
    print(
        f"Current parser:\n"
        f"{PARSER_PATH}"
    )

    print()
    print(
        f"V5.2 backup:\n"
        f"{V52_BACKUP_PATH}"
    )

    print()
    print(
        "V5.3 output files:"
    )

    print(
        "  b1b2_raw_v53.json"
    )

    print(
        "  b1b2_rejected_v53.json"
    )

    print(
        "  b1b2_qa_v53.json"
    )

    print(
        "  b1b2_manual_review_v53.json"
    )

    print()
    print(
        "Now run:\n\n"
        "py tools/vocabulary_builder/parse_b1b2.py"
    )


if __name__ == "__main__":
    main()