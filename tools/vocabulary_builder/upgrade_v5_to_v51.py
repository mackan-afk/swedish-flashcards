from pathlib import Path
import shutil


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

PARSER_PATH = BASE_DIR / "parse_b1b2.py"
BACKUP_PATH = BASE_DIR / "parse_b1b2_v5_backup.py"


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
            f"No V5.1 parser has been written."
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
# V5.1 CONTINUATION HELPERS
# ============================================================

V51_CONTINUATION_SECTION = r'''
def english_probably_continues_v51(english):
    """
    V5.1

    Strong textual evidence that an English translation is
    unfinished.

    IMPORTANT:
    This is NOT used alone to decide that a row is a
    continuation. Geometry must also agree.
    """

    raw = str(english).rstrip()

    if not raw:
        return True

    # Existing reliable V4 signals:
    #
    # soft hyphen
    # comma
    # slash
    # hyphen
    if english_probably_continues(raw):
        return True

    low = remove_soft_hyphen(
        raw
    ).casefold()

    # These are deliberately conservative.
    #
    # They represent endings that strongly suggest the
    # translation may continue on another visual row.
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
        " one's",
        " one’s",
        " my",
        " your",
        " his",
        " her",
        " their",
        " other",
        " mother in",
        " father in",
        " brother in",
        " sister in",
    )

    if low.endswith(
        continuation_endings
    ):
        return True

    return False


def row_start_x(row):
    if not row["words"]:
        return None

    return min(
        word["x0"]
        for word in row["words"]
    )


def row_end_x(row):
    if not row["words"]:
        return None

    return max(
        word["x1"]
        for word in row["words"]
    )


def row_looks_english_by_layout(
    row,
    english_boundary_x,
):
    """
    Use X position ONLY to classify an unresolved row.

    V5 incorrectly used the learned X boundary to SPLIT rows
    into Swedish and English.

    V5.1 never does that.

    A row may be considered an English continuation only when
    its first word already begins near/in the learned English
    area.
    """

    if english_boundary_x is None:
        return False

    start_x = row_start_x(row)

    if start_x is None:
        return False

    # Slightly more tolerant than V5 because continuation rows
    # can start a few points before normal English text.
    return start_x >= (
        english_boundary_x - 12.0
    )


def row_is_short_fragment(row):
    """
    Additional safety signal.

    Most broken continuation rows in the source are short
    fragments such as:

        write is…
        vacation
        one’s mind
        other hand
        forefather
        of parliament
        book
        grandmother

    We do NOT use language detection here.
    """

    clean = normalize_basic(
        row["raw"]
    )

    tokens = clean.split()

    if not tokens:
        return False

    return len(tokens) <= 8


def same_column_continuation_geometry(
    row,
    previous_row_y,
    previous_column,
    current_column,
    previous_pdf_page,
    current_pdf_page,
):
    """
    Conservative same-column continuation geometry.
    """

    if previous_row_y is None:
        return False

    if previous_column != current_column:
        return False

    if previous_pdf_page != current_pdf_page:
        return False

    delta_y = (
        row["y"]
        - previous_row_y
    )

    return (
        0
        < delta_y
        < 27
    )


def cross_column_continuation_geometry(
    row,
    previous_row_y,
    previous_column,
    current_column,
    previous_pdf_page,
    current_pdf_page,
):
    """
    Detect a continuation from the bottom of LEFT to the top
    of RIGHT on the same physical PDF page.

    Thresholds are intentionally conservative.
    """

    if previous_row_y is None:
        return False

    if previous_pdf_page != current_pdf_page:
        return False

    if previous_column != "left":
        return False

    if current_column != "right":
        return False

    return (
        previous_row_y > 680
        and row["y"] < 150
    )


def should_join_english_continuation_v51(
    row,
    previous_card,
    previous_card_y,
    previous_card_column,
    previous_card_pdf_page,
    current_column,
    current_pdf_page,
    english_boundary_x,
):
    """
    V5.1 continuation decision.

    We require several independent signals.

    This intentionally prefers leaving an ambiguous row in
    rejected rather than corrupting a valid card.
    """

    if previous_card is None:
        return False

    if not row_is_short_fragment(
        row
    ):
        return False

    layout_signal = (
        row_looks_english_by_layout(
            row,
            english_boundary_x,
        )
    )

    if not layout_signal:
        return False

    same_column = (
        same_column_continuation_geometry(
            row,
            previous_card_y,
            previous_card_column,
            current_column,
            previous_card_pdf_page,
            current_pdf_page,
        )
    )

    cross_column = (
        cross_column_continuation_geometry(
            row,
            previous_card_y,
            previous_card_column,
            current_column,
            previous_card_pdf_page,
            current_pdf_page,
        )
    )

    if not (
        same_column
        or cross_column
    ):
        return False

    textual_signal = (
        english_probably_continues_v51(
            previous_card[
                "english"
            ]
        )
    )

    # --------------------------------------------------------
    # SAFETY POLICY
    #
    # Same-column:
    #     layout + proximity + textual evidence
    #
    # Cross-column:
    #     layout + edge-of-column geometry
    #
    # At a column break, the geometry itself is strong enough
    # because the PDF frequently wraps entries there.
    # --------------------------------------------------------

    if same_column:
        return textual_signal

    if cross_column:
        return True

    return False


def join_english_continuation_v51(
    previous,
    continuation,
):
    """
    Reuse V4's proven joining behaviour.
    """

    return join_english_continuation(
        previous,
        continuation,
    )
'''


# ============================================================
# V5.1 PARSER
# ============================================================

V51_PARSER = r'''
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
    # Context survives LEFT -> RIGHT.
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
        # X positions are learned only from reliable Unicode
        # separator rows.
        #
        # V5.1 uses these positions ONLY for continuation
        # classification.
        #
        # THEY ARE NEVER USED TO SPLIT A CARD.
        # ----------------------------------------------------

        english_boundaries = (
            calibrate_english_boundaries(
                rows
            )
        )

        # ----------------------------------------------------
        # Keep V5's successful broken-row repair.
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

        for column, column_rows in (
            ("left", left_rows),
            ("right", right_rows),
        ):

            boundary_x = (
                english_boundaries.get(
                    column
                )
            )

            for row in column_rows:

                raw = row["raw"]

                clean = normalize_basic(
                    raw
                )

                if not clean:
                    continue

                # --------------------------------------------
                # CHAPTER
                # --------------------------------------------

                chapter = detect_chapter(
                    clean
                )

                if chapter is not None:

                    current_chapter = (
                        chapter
                    )

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
                # NORMAL PARSING
                #
                # ONLY:
                #
                # 1. Unicode separator
                # 2. morphology fallback
                #
                # V5 layout splitting is intentionally removed.
                # --------------------------------------------

                parsed = (
                    parse_vocabulary_row(
                        row
                    )
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

                    previous_card = card
                    previous_card_y = (
                        row["y"]
                    )
                    previous_card_column = (
                        column
                    )
                    previous_card_pdf_page = (
                        source_pdf_page
                    )

                    continue

                # --------------------------------------------
                # V5.1 ENGLISH CONTINUATION
                # --------------------------------------------

                should_join = (
                    should_join_english_continuation_v51(
                        row=row,
                        previous_card=previous_card,
                        previous_card_y=(
                            previous_card_y
                        ),
                        previous_card_column=(
                            previous_card_column
                        ),
                        previous_card_pdf_page=(
                            previous_card_pdf_page
                        ),
                        current_column=column,
                        current_pdf_page=(
                            source_pdf_page
                        ),
                        english_boundary_x=(
                            boundary_x
                        ),
                    )
                )

                if should_join:

                    old_english = (
                        previous_card[
                            "english"
                        ]
                    )

                    new_english = (
                        join_english_continuation_v51(
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
                                "AUTO_JOINED_ENGLISH_V51"
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
                            "previous_column": (
                                previous_card_column
                            ),
                            "current_column": (
                                column
                            ),
                        }
                    )

                    previous_card_y = (
                        row["y"]
                    )
                    previous_card_column = (
                        column
                    )
                    previous_card_pdf_page = (
                        source_pdf_page
                    )

                    continue

                # --------------------------------------------
                # UNRESOLVED
                #
                # Ambiguous is better than corrupted.
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
                            row_looks_english_by_layout(
                                row,
                                boundary_x,
                            )
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
# APPLY PATCH
# ============================================================

def main():

    if not PARSER_PATH.exists():

        raise FileNotFoundError(
            f"Parser not found:\n"
            f"{PARSER_PATH}"
        )

    source = PARSER_PATH.read_text(
        encoding="utf-8"
    )

    # --------------------------------------------------------
    # Safety check
    # --------------------------------------------------------

    required_markers = [
        "SVENSKAKORT - B1/B2 PARSER V5",
        'b1b2_raw_v5.json',
        'b1b2_rejected_v5.json',
        'b1b2_qa_v5.json',
        "def split_by_layout(",
        "def repair_broken_rows(",
        "def parse_pdf():",
    ]

    missing = [
        marker
        for marker in required_markers
        if marker not in source
    ]

    if missing:

        raise RuntimeError(
            "\nThis does not look like the expected V5.\n"
            "Missing markers:\n"
            + "\n".join(
                f"  - {item}"
                for item in missing
            )
        )

    # --------------------------------------------------------
    # Backup V5
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
    # Output filenames
    # --------------------------------------------------------

    source = replace_once(
        source,
        'OUTPUT_JSON = OUTPUT_DIR / "b1b2_raw_v5.json"',
        'OUTPUT_JSON = OUTPUT_DIR / "b1b2_raw_v51.json"',
        "OUTPUT_JSON V5 -> V5.1",
    )

    source = replace_once(
        source,
        'REJECTED_JSON = OUTPUT_DIR / "b1b2_rejected_v5.json"',
        'REJECTED_JSON = OUTPUT_DIR / "b1b2_rejected_v51.json"',
        "REJECTED_JSON V5 -> V5.1",
    )

    source = replace_once(
        source,
        'QA_JSON = OUTPUT_DIR / "b1b2_qa_v5.json"',
        'QA_JSON = OUTPUT_DIR / "b1b2_qa_v51.json"',
        "QA_JSON V5 -> V5.1",
    )

    # --------------------------------------------------------
    # Replace V5 continuation helper area.
    #
    # Keep:
    #   get_unicode_boundary_info
    #   median
    #   calibrate_english_boundaries
    #   split_by_layout (unused, but harmless)
    #   repair_broken_rows
    #
    # Replace from english_probably_continues_v5 onward.
    # --------------------------------------------------------

    start_marker = (
        "def english_probably_continues_v5("
    )

    end_marker = (
        "# ============================================================\n"
        "# V5 PARSER\n"
        "# ============================================================"
    )

    start = source.find(
        start_marker
    )

    if start == -1:
        raise RuntimeError(
            "\nCould not find V5 continuation helper section."
        )

    end = source.find(
        end_marker,
        start,
    )

    if end == -1:
        raise RuntimeError(
            "\nCould not find V5 parser marker."
        )

    source = (
        source[:start]
        + V51_CONTINUATION_SECTION.rstrip()
        + "\n\n\n"
        + source[end:]
    )

    # --------------------------------------------------------
    # Replace entire parse_pdf()
    # --------------------------------------------------------

    source = replace_section(
        source,
        "def parse_pdf():",
        "# ============================================================\n# QA\n# ============================================================",
        V51_PARSER,
        "V5.1 parse_pdf",
    )

    # --------------------------------------------------------
    # QA event collection
    # --------------------------------------------------------

    old = '''    joined_events = [
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
    ]'''

    new = '''    joined_events = [
        event
        for event in qa_events
        if event["type"]
        in {
            "AUTO_JOINED_ENGLISH",
            "AUTO_JOINED_ENGLISH_V5",
            "AUTO_JOINED_ENGLISH_V51",
        }
    ]

    layout_events = [
        event
        for event in qa_events
        if event["type"]
        == "LAYOUT_FALLBACK"
    ]'''

    source = replace_once(
        source,
        old,
        new,
        "V5.1 joined event QA",
    )

    # --------------------------------------------------------
    # Report title
    # --------------------------------------------------------

    source = replace_once(
        source,
        '"SVENSKAKORT - B1/B2 PARSER V5"',
        '"SVENSKAKORT - B1/B2 PARSER V5.1"',
        "V5.1 report title",
    )

    # --------------------------------------------------------
    # Replace misleading layout counter label.
    #
    # It should now always be zero because V5.1 does not create
    # cards using layout fallback.
    # --------------------------------------------------------

    source = replace_once(
        source,
        'f"Layout fallbacks:         "',
        'f"Layout-created cards:     "',
        "V5.1 layout report label",
    )

    # --------------------------------------------------------
    # Write V5.1
    # --------------------------------------------------------

    PARSER_PATH.write_text(
        source,
        encoding="utf-8",
    )

    print("=" * 72)
    print(
        "SVENSKAKORT V5 -> V5.1 UPGRADE COMPLETE"
    )
    print("=" * 72)

    print()
    print(
        f"Updated parser:\n"
        f"{PARSER_PATH}"
    )

    print()
    print(
        f"V5 backup:\n"
        f"{BACKUP_PATH}"
    )

    print()
    print(
        "V5.1 changes:"
    )

    print(
        "  - disabled layout-based card splitting"
    )

    print(
        "  - kept broken-row repair"
    )

    print(
        "  - added conservative layout-assisted "
        "English continuation detection"
    )

    print(
        "  - preserved LEFT -> RIGHT context"
    )

    print()
    print(
        "Now run:\n\n"
        "py tools/vocabulary_builder/parse_b1b2.py"
    )


if __name__ == "__main__":
    main()
