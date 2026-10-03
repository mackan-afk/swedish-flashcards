from pathlib import Path
import shutil
import re


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

PARSER_PATH = BASE_DIR / "parse_b1b2.py"
BACKUP_PATH = BASE_DIR / "parse_b1b2_v4_backup.py"


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
            f"No V5 file has been written."
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
# V5 LAYOUT + PARSER
# ============================================================

V5_PARSER_SECTION = r'''
# ============================================================
# V5 LAYOUT HELPERS
# ============================================================

def get_unicode_boundary_info(row):
    """
    Return information about the reliable Unicode separator.

    The PDF usually stores the Swedish/English boundary as a
    special spacing character at the end of the final Swedish
    token.

    Returns None if the separator is not present.
    """

    words = row["words"]

    for i, word in enumerate(words):

        if contains_separator(word["text"]):

            english_x = None

            if i + 1 < len(words):
                english_x = words[i + 1]["x0"]

            return {
                "separator_index": i,
                "english_x": english_x,
            }

    return None


def median(values):
    values = sorted(values)

    if not values:
        return None

    n = len(values)
    middle = n // 2

    if n % 2:
        return values[middle]

    return (
        values[middle - 1]
        + values[middle]
    ) / 2


def calibrate_english_boundaries(rows):
    """
    Estimate where the English column begins inside each of the
    two vocabulary columns.

    We ONLY calibrate using rows containing the reliable Unicode
    separator.

    This means V5 does not guess the English X position from
    arbitrary text.
    """

    samples = {
        "left": [],
        "right": [],
    }

    for row in rows:

        info = get_unicode_boundary_info(row)

        if info is None:
            continue

        english_x = info["english_x"]

        if english_x is None:
            continue

        samples[row["column"]].append(
            english_x
        )

    boundaries = {}

    for column in ("left", "right"):

        values = samples[column]

        if len(values) >= 3:
            boundaries[column] = median(
                values
            )
        else:
            boundaries[column] = None

    return boundaries


def split_by_layout(row, english_boundary_x):
    """
    V5 fallback.

    Split a row using the X position learned from reliable rows
    on the SAME physical PDF page.

    This is especially useful for entries where the Unicode
    separator disappeared completely.

    Example:

        Vad hände med...?    What happened with...?

    IMPORTANT:
    This method is deliberately conservative. We require words
    on BOTH sides of the calibrated boundary.
    """

    if english_boundary_x is None:
        return None

    words = row["words"]

    swedish_words = []
    english_words = []

    # Small tolerance because individual glyph positioning in
    # the PDF is not perfectly identical from row to row.
    tolerance = 3.0

    for word in words:

        if word["x0"] < (
            english_boundary_x - tolerance
        ):
            swedish_words.append(
                word["text"]
            )
        else:
            english_words.append(
                word["text"]
            )

    if not swedish_words:
        return None

    if not english_words:
        return None

    swedish_raw = normalize_basic(
        " ".join(swedish_words)
    )

    english_raw = normalize_basic(
        " ".join(english_words)
    )

    if not swedish_raw or not english_raw:
        return None

    swedish, forms = extract_morphology(
        swedish_raw
    )

    english = normalize_basic(
        english_raw
    )

    if not swedish or not english:
        return None

    return {
        "swedish": swedish,
        "forms": forms,
        "english": english,
        "method": "LAYOUT_FALLBACK",
    }


def row_is_probably_english_continuation(
    row,
    english_boundary_x,
):
    """
    Determine whether an unresolved row visually starts inside
    the English part of the vocabulary column.

    This is much safer than deciding based on whether the text
    'looks English'.
    """

    if english_boundary_x is None:
        return False

    words = row["words"]

    if not words:
        return False

    first_x = min(
        word["x0"]
        for word in words
    )

    # Give the PDF a few points of positioning tolerance.
    return first_x >= (
        english_boundary_x - 4.0
    )


def swedish_structure_is_broken(text):
    """
    Detect a Swedish entry broken over two visual rows.

    Typical source examples:

        vetenskapsman (
            -nen, vetenskapsmän, vetenskapsmännen)

        överensstämma (
            överensstämmer, överensstämde, överensstämt)

    A soft hyphen plus an unmatched opening parenthesis is a
    particularly strong signal.
    """

    raw = str(text)

    opens = raw.count("(")
    closes = raw.count(")")

    if opens > closes:
        return True

    if (
        SOFT_HYPHEN in raw
        and opens > 0
        and closes == 0
    ):
        return True

    return False


def merge_visual_rows(first, second):
    """
    Merge two physical PDF rows while preserving word
    coordinates.

    Used only for strongly indicated broken entries.
    """

    first_raw = first["raw"].rstrip()

    if first_raw.endswith(SOFT_HYPHEN):
        first_raw = first_raw[:-1]
        separator = ""
    else:
        separator = " "

    merged_raw = (
        first_raw
        + separator
        + second["raw"].lstrip()
    )

    merged_words = (
        list(first["words"])
        + list(second["words"])
    )

    merged_words.sort(
        key=lambda w: (
            w["y0"],
            w["x0"],
        )
    )

    return {
        "column": first["column"],
        "y": first["y"],
        "words": merged_words,
        "raw": merged_raw,
        "_merged_from_rows": 2,
    }


def repair_broken_rows(rows):
    """
    Pre-pass for strongly broken Swedish morphology.

    We intentionally do NOT merge arbitrary adjacent rows.

    Only rows with an unmatched Swedish parenthesis are
    candidates.
    """

    repaired = []
    events = []

    i = 0

    while i < len(rows):

        row = rows[i]

        if (
            swedish_structure_is_broken(
                row["raw"]
            )
            and i + 1 < len(rows)
        ):

            next_row = rows[i + 1]

            # Same visual vocabulary column only.
            if (
                next_row["column"]
                == row["column"]
            ):

                merged = merge_visual_rows(
                    row,
                    next_row,
                )

                events.append(
                    {
                        "type": (
                            "AUTO_JOINED_BROKEN_ROW"
                        ),
                        "column": row["column"],
                        "before_1": row["raw"],
                        "before_2": next_row["raw"],
                        "after": merged["raw"],
                    }
                )

                repaired.append(
                    merged
                )

                i += 2
                continue

        repaired.append(
            row
        )

        i += 1

    return repaired, events


def english_probably_continues_v5(english):
    """
    Strong textual signal that the English translation is
    unfinished.

    V5 keeps all V4 signals and adds several cases frequently
    observed in the actual Rivstart PDF.
    """

    raw = str(english).rstrip()

    if not raw:
        return True

    if english_probably_continues(raw):
        return True

    low = remove_soft_hyphen(
        raw
    ).casefold()

    continuation_endings = (
        " in",
        " of",
        " the",
        " a",
        " an",
        " to",
        " with",
        " from",
        " for",
        " one",
        " my",
        " your",
        " his",
        " her",
        " their",
        " other",
        " civil",
        " human",
        " per",
        " mother in",
        " father in",
        " brother in",
        " sister in",
    )

    return low.endswith(
        continuation_endings
    )


def join_cross_column_continuation(
    previous,
    continuation,
):
    """
    Join an English continuation using the existing V4 joining
    logic.
    """

    return join_english_continuation(
        previous,
        continuation,
    )


# ============================================================
# V5 PARSER
# ============================================================

def parse_pdf():

    doc = pymupdf.open(
        PDF_PATH
    )

    cards = []
    rejected = []
    qa_events = []

    current_chapter = None
    current_book_page = None

    # --------------------------------------------------------
    # V5 IMPORTANT CHANGE
    #
    # These are global across the reading flow.
    #
    # V4 reset them when entering the right column, which meant
    # a translation broken at:
    #
    #     bottom LEFT -> top RIGHT
    #
    # could never be reconstructed.
    # --------------------------------------------------------

    previous_card = None
    previous_card_y = None
    previous_card_column = None
    previous_card_pdf_page = None

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
        # Learn English X positions BEFORE repairing rows.
        # Reliable Unicode rows provide calibration.
        # ----------------------------------------------------

        english_boundaries = (
            calibrate_english_boundaries(
                rows
            )
        )

        # ----------------------------------------------------
        # Repair strongly broken morphology rows.
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

        # ----------------------------------------------------
        # Actual reading order:
        #
        # LEFT top -> bottom
        # RIGHT top -> bottom
        #
        # previous_card is NOT reset between them.
        # ----------------------------------------------------

        for column, column_rows in (
            ("left", left_rows),
            ("right", right_rows),
        ):

            boundary_x = (
                english_boundaries.get(
                    column
                )
            )

            for row_index, row in enumerate(
                column_rows
            ):

                raw = row["raw"]

                clean = normalize_basic(
                    raw
                )

                if not clean:
                    continue

                # --------------------------------------------
                # Chapter marker
                # --------------------------------------------

                chapter = detect_chapter(
                    clean
                )

                if chapter is not None:

                    current_chapter = chapter

                    # Do not throw away previous_card here.
                    # It is harmless to retain it because later
                    # continuation checks require strong layout
                    # evidence.

                    continue

                # --------------------------------------------
                # Textbook page marker
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
                # Noise
                # --------------------------------------------

                if is_header_or_noise(
                    clean
                ):
                    continue

                # --------------------------------------------
                # METHOD 1 + 2
                #
                # Existing V4 parser:
                #
                # Unicode separator
                # Morphology fallback
                # --------------------------------------------

                parsed = parse_vocabulary_row(
                    row
                )

                # --------------------------------------------
                # METHOD 3
                #
                # V5 X-position layout fallback.
                # --------------------------------------------

                if parsed is None:

                    parsed = split_by_layout(
                        row,
                        boundary_x,
                    )

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
                                "column": column,
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

                    if (
                        parsed["method"]
                        == "LAYOUT_FALLBACK"
                    ):

                        qa_events.append(
                            {
                                "type": (
                                    "LAYOUT_FALLBACK"
                                ),
                                "source_pdf_page": (
                                    source_pdf_page
                                ),
                                "column": column,
                                "chapter": (
                                    current_chapter
                                ),
                                "page": (
                                    current_book_page
                                ),
                                "boundary_x": (
                                    boundary_x
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
                    previous_card_y = row["y"]
                    previous_card_column = (
                        column
                    )
                    previous_card_pdf_page = (
                        source_pdf_page
                    )

                    continue

                # --------------------------------------------
                # V5 ENGLISH CONTINUATION
                # --------------------------------------------

                visual_english = (
                    row_is_probably_english_continuation(
                        row,
                        boundary_x,
                    )
                )

                textual_signal = False

                if previous_card is not None:

                    textual_signal = (
                        english_probably_continues_v5(
                            previous_card[
                                "english"
                            ]
                        )
                    )

                # Same-column continuation:
                #
                # keep V4's proximity requirement.
                same_column_close = (
                    previous_card is not None
                    and previous_card_y
                    is not None
                    and previous_card_column
                    == column
                    and previous_card_pdf_page
                    == source_pdf_page
                    and 0
                    < (
                        row["y"]
                        - previous_card_y
                    )
                    < 26
                )

                # Cross-column continuation:
                #
                # previous card must be near the bottom of the
                # left column and unresolved row near the top
                # of the right column.
                cross_column_close = (
                    previous_card is not None
                    and previous_card_column
                    == "left"
                    and column == "right"
                    and previous_card_pdf_page
                    == source_pdf_page
                    and previous_card_y
                    is not None
                    and previous_card_y
                    > 700
                    and row["y"]
                    < 120
                )

                should_join = (
                    previous_card is not None
                    and visual_english
                    and (
                        (
                            same_column_close
                            and textual_signal
                        )
                        or (
                            cross_column_close
                            and textual_signal
                        )
                    )
                )

                if should_join:

                    old_english = (
                        previous_card[
                            "english"
                        ]
                    )

                    new_english = (
                        join_cross_column_continuation(
                            old_english,
                            clean,
                        )
                    )

                    previous_card[
                        "english"
                    ] = new_english

                    qa_events.append(
                        {
                            "type": (
                                "AUTO_JOINED_ENGLISH_V5"
                            ),
                            "source_pdf_page": (
                                source_pdf_page
                            ),
                            "column": column,
                            "chapter": (
                                current_chapter
                            ),
                            "page": (
                                current_book_page
                            ),
                            "swedish": (
                                previous_card[
                                    "swedish"
                                ]
                            ),
                            "before": (
                                old_english
                            ),
                            "continuation": (
                                clean
                            ),
                            "after": (
                                new_english
                            ),
                            "cross_column": (
                                cross_column_close
                            ),
                        }
                    )

                    previous_card_y = row["y"]
                    previous_card_column = (
                        column
                    )
                    previous_card_pdf_page = (
                        source_pdf_page
                    )

                    continue

                # --------------------------------------------
                # UNRESOLVED
                # --------------------------------------------

                rejected.append(
                    {
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
                        "column": column,
                        "y": row["y"],
                        "english_boundary_x": (
                            boundary_x
                        ),
                        "looks_like_english": (
                            visual_english
                        ),
                    }
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
    # TEMPORARY IDS
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
    )
'''


# ============================================================
# APPLY UPGRADE
# ============================================================

def main():

    if not PARSER_PATH.exists():
        raise FileNotFoundError(
            f"Parser not found:\n{PARSER_PATH}"
        )

    source = PARSER_PATH.read_text(
        encoding="utf-8"
    )

    # --------------------------------------------------------
    # Safety check:
    # make sure this really is our V4.
    # --------------------------------------------------------

    required_markers = [
        "SVENSKAKORT - B1/B2 PARSER V4",
        'b1b2_raw_v4.json',
        'b1b2_rejected_v4.json',
        'b1b2_qa_v4.json',
        "def parse_pdf():",
        "def run_qa(",
    ]

    missing = [
        marker
        for marker in required_markers
        if marker not in source
    ]

    if missing:
        raise RuntimeError(
            "\nThis does not look like the expected V4.\n"
            "Missing markers:\n"
            + "\n".join(
                f"  - {item}"
                for item in missing
            )
        )

    # --------------------------------------------------------
    # Backup V4.
    # --------------------------------------------------------

    shutil.copy2(
        PARSER_PATH,
        BACKUP_PATH,
    )

    print(
        f"Backup created:\n"
        f"{BACKUP_PATH}\n"
    )

    # --------------------------------------------------------
    # Output filenames.
    # --------------------------------------------------------

    source = replace_once(
        source,
        'OUTPUT_JSON = OUTPUT_DIR / "b1b2_raw_v4.json"',
        'OUTPUT_JSON = OUTPUT_DIR / "b1b2_raw_v5.json"',
        "OUTPUT_JSON V4 -> V5",
    )

    source = replace_once(
        source,
        'REJECTED_JSON = OUTPUT_DIR / "b1b2_rejected_v4.json"',
        'REJECTED_JSON = OUTPUT_DIR / "b1b2_rejected_v5.json"',
        "REJECTED_JSON V4 -> V5",
    )

    source = replace_once(
        source,
        'QA_JSON = OUTPUT_DIR / "b1b2_qa_v4.json"',
        'QA_JSON = OUTPUT_DIR / "b1b2_qa_v5.json"',
        "QA_JSON V4 -> V5",
    )

    # --------------------------------------------------------
    # Replace V4 PAGE STATE + PARSER with V5 implementation.
    #
    # We leave the earlier V4 helper functions intact because
    # V5 deliberately builds on them.
    # --------------------------------------------------------

    source = replace_section(
        source,
        "# ============================================================\n# PAGE STATE\n# ============================================================",
        "# ============================================================\n# QA\n# ============================================================",
        V5_PARSER_SECTION,
        "V5 parser section",
    )

    # --------------------------------------------------------
    # Extend QA event collection.
    # --------------------------------------------------------

    old = '''    joined_events = [
        event
        for event in qa_events
        if event["type"]
        == "AUTO_JOINED_ENGLISH"
    ]

    return {'''

    new = '''    joined_events = [
        event
        for event in qa_events
        if event["type"]
        in {
            "AUTO_JOINED_ENGLISH",
            "AUTO_JOINED_ENGLISH_V5",
        }
    ]

    layout_events = [
        event
        for event in qa_events
        if event["type"]
        == "LAYOUT_FALLBACK"
    ]

    broken_row_events = [
        event
        for event in qa_events
        if event["type"]
        == "AUTO_JOINED_BROKEN_ROW"
    ]

    return {'''

    source = replace_once(
        source,
        old,
        new,
        "QA event groups",
    )

    # --------------------------------------------------------
    # Add V5 QA groups to returned JSON.
    # --------------------------------------------------------

    old = '''        "auto_joined_english": (
            joined_events
        ),
        "exact_duplicates": (
            duplicates
        ),
    }'''

    new = '''        "auto_joined_english": (
            joined_events
        ),
        "layout_fallbacks": (
            layout_events
        ),
        "auto_joined_broken_rows": (
            broken_row_events
        ),
        "exact_duplicates": (
            duplicates
        ),
    }'''

    source = replace_once(
        source,
        old,
        new,
        "QA V5 output groups",
    )

    # --------------------------------------------------------
    # Report title.
    # --------------------------------------------------------

    source = replace_once(
        source,
        '"SVENSKAKORT - B1/B2 PARSER V4"',
        '"SVENSKAKORT - B1/B2 PARSER V5"',
        "report title",
    )

    # --------------------------------------------------------
    # Add V5 counters to report.
    # --------------------------------------------------------

    old = '''    print(
        f"English continuations:    "
        f"{len(qa_report['auto_joined_english'])}"
    )

    print(
        f"Exact duplicate groups:   "
        f"{len(qa_report['exact_duplicates'])}"
    )'''

    new = '''    print(
        f"English continuations:    "
        f"{len(qa_report['auto_joined_english'])}"
    )

    print(
        f"Layout fallbacks:         "
        f"{len(qa_report['layout_fallbacks'])}"
    )

    print(
        f"Broken rows repaired:     "
        f"{len(qa_report['auto_joined_broken_rows'])}"
    )

    print(
        f"Exact duplicate groups:   "
        f"{len(qa_report['exact_duplicates'])}"
    )'''

    source = replace_once(
        source,
        old,
        new,
        "V5 report counters",
    )

    # --------------------------------------------------------
    # Insert V5 report sections before NO PAGE.
    # --------------------------------------------------------

    marker = '''    # --------------------------------------------------------
    # No-page examples
    # --------------------------------------------------------'''

    insertion = '''    # --------------------------------------------------------
    # V5 layout fallback examples
    # --------------------------------------------------------

    print()
    print(
        "LAYOUT FALLBACK - FIRST 30"
    )
    print("-" * 72)

    for event in (
        qa_report[
            "layout_fallbacks"
        ][:30]
    ):

        print(
            f"PDF "
            f"{event['source_pdf_page']:2d}"
            f" | "
            f"{event['column']:5s}"
            f" | X="
            f"{event['boundary_x']}"
        )

        print(
            f"    RAW:   "
            f"{event['raw']}"
        )

        print(
            f"    -> SV: "
            f"{event['swedish']}"
        )

        print(
            f"       FORMS: "
            f"{event['forms']}"
        )

        print(
            f"       EN: "
            f"{event['english']}"
        )

    # --------------------------------------------------------
    # V5 broken-row repairs
    # --------------------------------------------------------

    print()
    print(
        "BROKEN ROW REPAIRS - FIRST 20"
    )
    print("-" * 72)

    for event in (
        qa_report[
            "auto_joined_broken_rows"
        ][:20]
    ):

        print(
            f"PDF "
            f"{event['source_pdf_page']:2d}"
            f" | "
            f"{event['column']:5s}"
        )

        print(
            f"    1: "
            f"{event['before_1']}"
        )

        print(
            f"    2: "
            f"{event['before_2']}"
        )

        print(
            f"    -> "
            f"{event['after']}"
        )

    # --------------------------------------------------------
    # No-page examples
    # --------------------------------------------------------'''

    source = replace_once(
        source,
        marker,
        insertion,
        "V5 report detail sections",
    )

    # --------------------------------------------------------
    # Write upgraded parser.
    # --------------------------------------------------------

    PARSER_PATH.write_text(
        source,
        encoding="utf-8",
    )

    print("=" * 72)
    print("SVENSKAKORT V4 -> V5 UPGRADE COMPLETE")
    print("=" * 72)

    print()
    print(
        f"Updated parser:\n"
        f"{PARSER_PATH}"
    )

    print()
    print(
        "V4 backup:\n"
        f"{BACKUP_PATH}"
    )

    print()
    print(
        "Now run:\n\n"
        "py tools/vocabulary_builder/parse_b1b2.py"
    )


if __name__ == "__main__":
    main()