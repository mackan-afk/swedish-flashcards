from pathlib import Path
import shutil


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

PARSER_PATH = BASE_DIR / "parse_b1b2.py"
BACKUP_PATH = BASE_DIR / "parse_b1b2_v51_backup.py"


# ============================================================
# HELPERS
# ============================================================

def replace_once(text, old, new, description):

    count = text.count(old)

    if count != 1:

        raise RuntimeError(
            f"\nCould not safely apply patch:\n"
            f"{description}\n\n"
            f"Expected exactly 1 occurrence, "
            f"found {count}.\n"
            f"No V5.2 parser has been written."
        )

    return text.replace(
        old,
        new,
        1,
    )


def replace_section(
    text,
    start_marker,
    end_marker,
    replacement,
    description,
):

    start = text.find(
        start_marker
    )

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
# V5.2 LOCAL GAP PARSER
# ============================================================

V52_LOCAL_GAP_SECTION = r'''
# ============================================================
# V5.2 LOCAL GAP SPLITTING
# ============================================================

def token_gap(left_word, right_word):
    """
    Horizontal distance between two adjacent PDF tokens.
    """

    return (
        right_word["x0"]
        - left_word["x1"]
    )


def get_row_gaps(row):
    """
    Return all horizontal gaps between adjacent words.

    Example:

        Vad hände med…?       What happened with…?

    The Swedish/English boundary should produce a much larger
    gap than ordinary spaces inside either phrase.
    """

    words = sorted(
        row["words"],
        key=lambda w: w["x0"],
    )

    gaps = []

    for i in range(
        len(words) - 1
    ):

        gap = token_gap(
            words[i],
            words[i + 1],
        )

        gaps.append(
            {
                "index": i,
                "gap": gap,
                "left": words[i],
                "right": words[i + 1],
            }
        )

    return gaps


def split_row_at_index(
    row,
    index,
):
    """
    Split after token `index`.
    """

    words = sorted(
        row["words"],
        key=lambda w: w["x0"],
    )

    left_words = words[
        :index + 1
    ]

    right_words = words[
        index + 1:
    ]

    if not left_words:
        return None

    if not right_words:
        return None

    left_text = normalize_basic(
        " ".join(
            word["text"]
            for word in left_words
        )
    )

    right_text = normalize_basic(
        " ".join(
            word["text"]
            for word in right_words
        )
    )

    if not left_text:
        return None

    if not right_text:
        return None

    return (
        left_text,
        right_text,
    )


def local_gap_candidate(row):
    """
    Find a strong LOCAL Swedish/English boundary.

    V5 used one global X threshold. That failed because the
    actual boundary moves depending on the length of the
    Swedish expression.

    V5.2 instead asks:

        Is there one unusually large horizontal gap inside
        THIS row?

    The method is intentionally conservative.
    """

    words = sorted(
        row["words"],
        key=lambda w: w["x0"],
    )

    if len(words) < 2:
        return None

    gaps = get_row_gaps(
        row
    )

    positive = [
        item
        for item in gaps
        if item["gap"] > 0
    ]

    if not positive:
        return None

    ranked = sorted(
        positive,
        key=lambda item: item["gap"],
        reverse=True,
    )

    largest = ranked[0]

    largest_gap = (
        largest["gap"]
    )

    second_gap = 0.0

    if len(ranked) > 1:
        second_gap = (
            ranked[1]["gap"]
        )

    # --------------------------------------------------------
    # ABSOLUTE REQUIREMENT
    #
    # Normal spaces in this PDF are usually much smaller.
    # We do not split unless the candidate gap is substantial.
    # --------------------------------------------------------

    if largest_gap < 10.0:
        return None

    # --------------------------------------------------------
    # RELATIVE REQUIREMENT
    #
    # If another gap is almost as large, the boundary is
    # ambiguous.
    # --------------------------------------------------------

    if (
        second_gap > 0
        and largest_gap
        < second_gap * 1.35
    ):
        return None

    split_index = (
        largest["index"]
    )

    split = split_row_at_index(
        row,
        split_index,
    )

    if split is None:
        return None

    swedish_raw, english_raw = (
        split
    )

    # --------------------------------------------------------
    # Need meaningful content on both sides.
    # --------------------------------------------------------

    if len(
        swedish_raw.strip()
    ) < 2:
        return None

    if len(
        english_raw.strip()
    ) < 2:
        return None

    return {
        "swedish_raw": swedish_raw,
        "english_raw": english_raw,
        "gap": largest_gap,
        "second_gap": second_gap,
        "split_index": split_index,
    }


def parentheses_balanced(text):
    return (
        text.count("(")
        == text.count(")")
    )


def local_gap_split_is_safe(
    candidate
):
    """
    Safety checks before accepting a local-gap split.

    We do NOT want to reproduce the V5 problem where the split
    occurred inside:

        (-r, -de, -t)

    or inside another parenthetical expression.
    """

    swedish_raw = candidate[
        "swedish_raw"
    ]

    english_raw = candidate[
        "english_raw"
    ]

    if not parentheses_balanced(
        swedish_raw
    ):
        return False

    # English parentheses are allowed:
    #
    # Swedish mile (10 km)
    #
    # Therefore we do not require balanced English here.

    # Do not accept if Swedish ends in an obvious broken
    # morphology fragment.
    if swedish_raw.rstrip().endswith(
        (
            "(",
            ",",
            "/",
        )
    ):
        return False

    # Avoid accepting a right side that is literally only a
    # morphology suffix.
    english_clean = (
        english_raw
        .strip()
        .casefold()
    )

    suspicious_right = {
        "-t",
        "-a",
        "-en",
        "-et",
        "-er",
        "-ar",
        "-na",
        "-arna",
        "-erna",
    }

    if english_clean in suspicious_right:
        return False

    return True


def parse_by_local_gap(row):
    """
    V5.2 fallback parser.

    IMPORTANT:
    This is attempted only AFTER:

        1. Unicode separator
        2. morphology fallback

    so it cannot replace the stronger parsing methods.
    """

    candidate = (
        local_gap_candidate(
            row
        )
    )

    if candidate is None:
        return None

    if not local_gap_split_is_safe(
        candidate
    ):
        return None

    swedish_raw = candidate[
        "swedish_raw"
    ]

    english_raw = candidate[
        "english_raw"
    ]

    swedish, forms = (
        extract_morphology(
            swedish_raw
        )
    )

    english = normalize_basic(
        english_raw
    )

    if not swedish:
        return None

    if not english:
        return None

    return {
        "swedish": swedish,
        "forms": forms,
        "english": english,
        "method": (
            "LOCAL_GAP_FALLBACK"
        ),
        "gap": candidate[
            "gap"
        ],
        "second_gap": candidate[
            "second_gap"
        ],
    }


# ============================================================
# V5.2 MORPHOLOGY FALLBACK SAFETY
# ============================================================

def morphology_fallback_is_suspicious(
    parsed
):
    """
    Detect the known V4/V5/V5.1 failure:

        ringa (-r, -de, -t) in

        -> ringa
        -> EN: in

    A single Swedish particle/preposition after morphology may
    actually belong to the Swedish lexical expression.
    """

    if parsed is None:
        return False

    if (
        parsed.get("method")
        != "MORPHOLOGY_FALLBACK"
    ):
        return False

    english = (
        parsed.get(
            "english",
            "",
        )
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


# ============================================================
# V5.2 RAW ROW PREPROCESSING
# ============================================================

def row_has_unicode_separator(row):

    return (
        get_unicode_boundary_info(
            row
        )
        is not None
    )


def join_raw_rows(
    first,
    second,
):
    """
    Join two adjacent visual rows.

    Coordinates are preserved, but all words from the second
    row are moved into the combined logical row.

    Parsing still happens afterwards.
    """

    first_raw = first[
        "raw"
    ].rstrip()

    second_raw = second[
        "raw"
    ].lstrip()

    if first_raw.endswith(
        SOFT_HYPHEN
    ):

        combined_raw = (
            first_raw[:-1]
            + second_raw
        )

    else:

        combined_raw = (
            first_raw
            + " "
            + second_raw
        )

    combined_words = (
        list(first["words"])
        + list(second["words"])
    )

    return {
        "column": first[
            "column"
        ],
        "y": first[
            "y"
        ],
        "words": combined_words,
        "raw": combined_raw,
        "_v52_joined": True,
    }


def should_prejoin_rows(
    first,
    second,
):
    """
    Very conservative pre-parser row joining.

    This is primarily for broken English translations.

    We only join within the SAME visual column here.
    Cross-column ambiguity stays for QA.
    """

    if (
        first["column"]
        != second["column"]
    ):
        return False

    delta_y = (
        second["y"]
        - first["y"]
    )

    if not (
        0 < delta_y < 24
    ):
        return False

    first_clean = normalize_basic(
        first["raw"]
    )

    second_clean = normalize_basic(
        second["raw"]
    )

    if not first_clean:
        return False

    if not second_clean:
        return False

    # --------------------------------------------------------
    # Strong signal 1:
    # explicit soft-hyphen continuation.
    # --------------------------------------------------------

    if first["raw"].rstrip().endswith(
        SOFT_HYPHEN
    ):
        return True

    # --------------------------------------------------------
    # Strong signal 2:
    # first row already has a reliable Swedish/English
    # separator AND its English translation clearly continues.
    # --------------------------------------------------------

    primary = (
        split_by_unicode_separator(
            first
        )
    )

    if primary is not None:

        (
            swedish_raw,
            english_raw,
            method,
        ) = primary

        if english_probably_continues_v51(
            english_raw
        ):

            # Second row should be a short fragment.
            if row_is_short_fragment(
                second
            ):
                return True

    return False


def preprocess_rows_v52(rows):
    """
    V5.2 preprocessing pipeline.

    Broken morphology has already been repaired by
    repair_broken_rows().

    This second pass joins only strongly indicated translation
    continuations.
    """

    result = []
    events = []

    i = 0

    while i < len(rows):

        current = rows[i]

        if i + 1 < len(rows):

            next_row = rows[
                i + 1
            ]

            if should_prejoin_rows(
                current,
                next_row,
            ):

                merged = join_raw_rows(
                    current,
                    next_row,
                )

                result.append(
                    merged
                )

                events.append(
                    {
                        "type": (
                            "V52_PREJOINED_ROWS"
                        ),
                        "column": current[
                            "column"
                        ],
                        "before_1": current[
                            "raw"
                        ],
                        "before_2": next_row[
                            "raw"
                        ],
                        "after": merged[
                            "raw"
                        ],
                    }
                )

                i += 2
                continue

        result.append(
            current
        )

        i += 1

    return (
        result,
        events,
    )
'''


# ============================================================
# V5.2 PARSER
# ============================================================

V52_PARSER = r'''
def parse_pdf():

    doc = pymupdf.open(
        PDF_PATH
    )

    cards = []
    rejected = []
    qa_events = []

    current_chapter = None
    current_book_page = None

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
        # STEP 1
        #
        # Existing successful V5 broken morphology repair.
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
        # STEP 2
        #
        # V5.2 conservative translation-row preprocessing.
        # ----------------------------------------------------

        rows, prejoin_events = (
            preprocess_rows_v52(
                rows
            )
        )

        for event in prejoin_events:

            event[
                "source_pdf_page"
            ] = source_pdf_page

            qa_events.append(
                event
            )

        # ----------------------------------------------------
        # get_visual_lines already returns:
        #
        # LEFT complete column
        # RIGHT complete column
        #
        # Keep this reading order.
        # ----------------------------------------------------

        for row in rows:

            column = row[
                "column"
            ]

            raw = row[
                "raw"
            ]

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
            # METHODS 1 + 2
            #
            # Existing strongest parsers.
            # --------------------------------------------

            parsed = (
                parse_vocabulary_row(
                    row
                )
            )

            # --------------------------------------------
            # Reject known dangerous morphology fallback.
            # --------------------------------------------

            if (
                parsed is not None
                and morphology_fallback_is_suspicious(
                    parsed
                )
            ):

                qa_events.append(
                    {
                        "type": (
                            "REJECTED_SUSPICIOUS_MORPHOLOGY"
                        ),
                        "source_pdf_page": (
                            source_pdf_page
                        ),
                        "column": column,
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

                parsed = None

            # --------------------------------------------
            # METHOD 3
            #
            # V5.2 local gap.
            # --------------------------------------------

            if parsed is None:

                parsed = (
                    parse_by_local_gap(
                        row
                    )
                )

            # --------------------------------------------
            # ACCEPT
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
                    == "LOCAL_GAP_FALLBACK"
                ):

                    qa_events.append(
                        {
                            "type": (
                                "LOCAL_GAP_FALLBACK"
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
                            "gap": parsed[
                                "gap"
                            ],
                            "second_gap": parsed[
                                "second_gap"
                            ],
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
                    "y": row[
                        "y"
                    ],
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
            f"Parser not found:\n"
            f"{PARSER_PATH}"
        )

    source = PARSER_PATH.read_text(
        encoding="utf-8"
    )

    # --------------------------------------------------------
    # SAFETY CHECK
    # --------------------------------------------------------

    required_markers = [
        "SVENSKAKORT - B1/B2 PARSER V5.1",
        'b1b2_raw_v51.json',
        'b1b2_rejected_v51.json',
        'b1b2_qa_v51.json',
        "def repair_broken_rows(",
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
            "\nThis does not look like the expected V5.1.\n"
            "Missing markers:\n"
            + "\n".join(
                f"  - {item}"
                for item in missing
            )
        )

    # --------------------------------------------------------
    # BACKUP
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
    # OUTPUT NAMES
    # --------------------------------------------------------

    source = replace_once(
        source,
        'OUTPUT_JSON = OUTPUT_DIR / "b1b2_raw_v51.json"',
        'OUTPUT_JSON = OUTPUT_DIR / "b1b2_raw_v52.json"',
        "OUTPUT_JSON V5.1 -> V5.2",
    )

    source = replace_once(
        source,
        'REJECTED_JSON = OUTPUT_DIR / "b1b2_rejected_v51.json"',
        'REJECTED_JSON = OUTPUT_DIR / "b1b2_rejected_v52.json"',
        "REJECTED_JSON V5.1 -> V5.2",
    )

    source = replace_once(
        source,
        'QA_JSON = OUTPUT_DIR / "b1b2_qa_v51.json"',
        'QA_JSON = OUTPUT_DIR / "b1b2_qa_v52.json"',
        "QA_JSON V5.1 -> V5.2",
    )

    # --------------------------------------------------------
    # INSERT V5.2 HELPERS
    #
    # Put them immediately before parse_pdf().
    # --------------------------------------------------------

    parser_marker = (
        "def parse_pdf():"
    )

    parser_pos = source.find(
        parser_marker
    )

    if parser_pos == -1:

        raise RuntimeError(
            "\nCould not find parse_pdf()."
        )

    source = (
        source[:parser_pos]
        + V52_LOCAL_GAP_SECTION.rstrip()
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
        V52_PARSER,
        "V5.2 parse_pdf",
    )

    # --------------------------------------------------------
    # QA:
    # Add V5.2 event groups before return.
    # --------------------------------------------------------

    old = '''    broken_row_events = [
        event
        for event in qa_events
        if event["type"]
        == "AUTO_JOINED_BROKEN_ROW"
    ]

    return {'''

    new = '''    broken_row_events = [
        event
        for event in qa_events
        if event["type"]
        == "AUTO_JOINED_BROKEN_ROW"
    ]

    local_gap_events = [
        event
        for event in qa_events
        if event["type"]
        == "LOCAL_GAP_FALLBACK"
    ]

    prejoined_events = [
        event
        for event in qa_events
        if event["type"]
        == "V52_PREJOINED_ROWS"
    ]

    suspicious_morphology_events = [
        event
        for event in qa_events
        if event["type"]
        == "REJECTED_SUSPICIOUS_MORPHOLOGY"
    ]

    return {'''

    source = replace_once(
        source,
        old,
        new,
        "V5.2 QA event groups",
    )

    # --------------------------------------------------------
    # QA OUTPUT
    # --------------------------------------------------------

    old = '''        "auto_joined_broken_rows": (
            broken_row_events
        ),
        "exact_duplicates": (
            duplicates
        ),
    }'''

    new = '''        "auto_joined_broken_rows": (
            broken_row_events
        ),
        "local_gap_fallbacks": (
            local_gap_events
        ),
        "v52_prejoined_rows": (
            prejoined_events
        ),
        "rejected_suspicious_morphology": (
            suspicious_morphology_events
        ),
        "exact_duplicates": (
            duplicates
        ),
    }'''

    source = replace_once(
        source,
        old,
        new,
        "V5.2 QA output",
    )

    # --------------------------------------------------------
    # REPORT TITLE
    # --------------------------------------------------------

    source = replace_once(
        source,
        '"SVENSKAKORT - B1/B2 PARSER V5.1"',
        '"SVENSKAKORT - B1/B2 PARSER V5.2"',
        "V5.2 report title",
    )

    # --------------------------------------------------------
    # REPORT COUNTERS
    # --------------------------------------------------------

    old = '''    print(
        f"Broken rows repaired:     "
        f"{len(qa_report['auto_joined_broken_rows'])}"
    )

    print(
        f"Exact duplicate groups:   "
        f"{len(qa_report['exact_duplicates'])}"
    )'''

    new = '''    print(
        f"Broken rows repaired:     "
        f"{len(qa_report['auto_joined_broken_rows'])}"
    )

    print(
        f"Local-gap cards:          "
        f"{len(qa_report['local_gap_fallbacks'])}"
    )

    print(
        f"Rows prejoined V5.2:      "
        f"{len(qa_report['v52_prejoined_rows'])}"
    )

    print(
        f"Suspicious morphology:    "
        f"{len(qa_report['rejected_suspicious_morphology'])}"
    )

    print(
        f"Exact duplicate groups:   "
        f"{len(qa_report['exact_duplicates'])}"
    )'''

    source = replace_once(
        source,
        old,
        new,
        "V5.2 report counters",
    )

    # --------------------------------------------------------
    # REPORT DETAILS
    #
    # Insert before NO PAGE section.
    # --------------------------------------------------------

    marker = '''    # --------------------------------------------------------
    # No-page examples
    # --------------------------------------------------------'''

    insertion = '''    # --------------------------------------------------------
    # V5.2 local-gap examples
    # --------------------------------------------------------

    print()
    print(
        "LOCAL GAP FALLBACK - FIRST 30"
    )
    print("-" * 72)

    for event in (
        qa_report[
            "local_gap_fallbacks"
        ][:30]
    ):

        print(
            f"PDF "
            f"{event['source_pdf_page']:2d}"
            f" | "
            f"{event['column']:5s}"
            f" | gap="
            f"{event['gap']:.2f}"
            f" | second="
            f"{event['second_gap']:.2f}"
        )

        print(
            f"    RAW: "
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
    # V5.2 prejoined rows
    # --------------------------------------------------------

    print()
    print(
        "V5.2 PREJOINED ROWS - FIRST 20"
    )
    print("-" * 72)

    for event in (
        qa_report[
            "v52_prejoined_rows"
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
    # Suspicious morphology
    # --------------------------------------------------------

    print()
    print(
        "SUSPICIOUS MORPHOLOGY - FIRST 20"
    )
    print("-" * 72)

    for event in (
        qa_report[
            "rejected_suspicious_morphology"
        ][:20]
    ):

        print(
            f"PDF "
            f"{event['source_pdf_page']:2d}"
            f" | "
            f"{event['column']:5s}"
        )

        print(
            f"    RAW: "
            f"{event['raw']}"
        )

        print(
            f"    attempted: "
            f"{event['swedish']} "
            f"| forms="
            f"{event['forms']} "
            f"| EN="
            f"{event['english']}"
        )

    # --------------------------------------------------------
    # No-page examples
    # --------------------------------------------------------'''

    source = replace_once(
        source,
        marker,
        insertion,
        "V5.2 detailed report",
    )

    # --------------------------------------------------------
    # WRITE
    # --------------------------------------------------------

    PARSER_PATH.write_text(
        source,
        encoding="utf-8",
    )

    print("=" * 72)
    print(
        "SVENSKAKORT V5.1 -> V5.2 UPGRADE COMPLETE"
    )
    print("=" * 72)

    print()
    print(
        f"Updated parser:\n"
        f"{PARSER_PATH}"
    )

    print()
    print(
        f"V5.1 backup:\n"
        f"{BACKUP_PATH}"
    )

    print()
    print(
        "V5.2 changes:"
    )

    print(
        "  - added local token-gap detection"
    )

    print(
        "  - no global-X card splitting"
    )

    print(
        "  - kept broken-row repair"
    )

    print(
        "  - added conservative row preprocessing"
    )

    print(
        "  - blocks suspicious one-token "
        "morphology translations"
    )

    print()
    print(
        "Now run:\n\n"
        "py tools/vocabulary_builder/parse_b1b2.py"
    )


if __name__ == "__main__":
    main()