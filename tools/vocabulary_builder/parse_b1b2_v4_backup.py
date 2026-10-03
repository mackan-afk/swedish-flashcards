import json
import re
from pathlib import Path
from collections import Counter, defaultdict

import pymupdf


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"

PDF_PATH = INPUT_DIR / "B1 B2.pdf"

OUTPUT_JSON = OUTPUT_DIR / "b1b2_raw_v4.json"
REJECTED_JSON = OUTPUT_DIR / "b1b2_rejected_v4.json"
QA_JSON = OUTPUT_DIR / "b1b2_qa_v4.json"


# ============================================================
# CONSTANTS
# ============================================================

LEVEL = "B1-B2"
SOURCE = "rivstart_b1b2"

SEPARATOR_CHARS = {
    "\u2002",  # EN SPACE
    "\u2003",  # EM SPACE
    "\u2009",  # THIN SPACE
    "\u202f",  # NARROW NO-BREAK SPACE
}

SOFT_HYPHEN = "\u00ad"

LEFT_MAX_X = 280
RIGHT_MIN_X = 300

ROW_Y_TOLERANCE = 1.8


# ============================================================
# TEXT HELPERS
# ============================================================

def normalize_basic(text):
    if text is None:
        return ""

    text = str(text)

    text = text.replace("\u00a0", " ")
    text = text.replace("\u200b", "")
    text = text.replace("\ufeff", "")

    # Dash normalization
    text = text.replace("–", "-")
    text = text.replace("—", "-")
    text = text.replace("−", "-")

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_forms(text):
    text = normalize_basic(text)

    # "- t" -> "-t"
    # "- de" -> "-de"
    text = re.sub(
        r"-\s+([A-Za-zÅÄÖåäöÉéÜü])",
        r"-\1",
        text,
    )

    text = re.sub(r"\s*,\s*", ", ", text)

    return text.strip()


def remove_soft_hyphen(text):
    return text.replace(SOFT_HYPHEN, "")


def contains_separator(text):
    return any(
        char in text
        for char in SEPARATOR_CHARS
    )


def strip_separator_chars(text):
    for char in SEPARATOR_CHARS:
        text = text.replace(char, "")

    return text


def clean_output_text(text):
    text = strip_separator_chars(text)
    text = remove_soft_hyphen(text)
    return normalize_basic(text)


# ============================================================
# MORPHOLOGY
# ============================================================

def morphology_group_looks_valid(text):
    """
    Decide whether (...) probably contains morphology.

    Examples:
        -en, -er, -erna
        skriver, skrev, skrivit
        ditt, dina
        -t, -a
        -et, -, -en

    We deliberately avoid treating arbitrary English
    parenthetical explanations as Swedish morphology.
    """

    forms = normalize_forms(text)

    if not forms:
        return False

    if "," in forms:
        return True

    if forms.startswith("-"):
        return True

    return False


def extract_morphology(swedish_raw):
    """
    Extract morphology appearing anywhere inside Swedish.

    lägga (lägger, la/lade, lagt) sig
        -> lägga sig
        -> lägger, la/lade, lagt

    ta (-r, tog, tagit) en dusch
        -> ta en dusch
        -> -r, tog, tagit
    """

    original = clean_output_text(swedish_raw)

    matches = list(
        re.finditer(
            r"\(([^()]*)\)",
            original,
        )
    )

    for match in matches:

        candidate = normalize_forms(
            match.group(1)
        )

        if not morphology_group_looks_valid(
            candidate
        ):
            continue

        prefix = original[:match.start()].strip()
        suffix = original[match.end():].strip()

        swedish = normalize_basic(
            f"{prefix} {suffix}"
        )

        return swedish, candidate

    return original, ""


# ============================================================
# PDF LAYOUT
# ============================================================

def word_column(x0):
    if x0 < LEFT_MAX_X:
        return "left"

    if x0 >= RIGHT_MIN_X:
        return "right"

    return None


def get_visual_lines(page):
    """
    Build visual rows separately for left and right columns.
    """

    words = page.get_text(
        "words",
        sort=True,
    )

    columns = {
        "left": [],
        "right": [],
    }

    for word in words:

        (
            x0,
            y0,
            x1,
            y1,
            text,
            block_no,
            line_no,
            word_no,
        ) = word

        column = word_column(x0)

        if column is None:
            continue

        columns[column].append(
            {
                "x0": x0,
                "y0": y0,
                "x1": x1,
                "y1": y1,
                "text": text,
            }
        )

    result = []

    for column_name in (
        "left",
        "right",
    ):

        column_words = sorted(
            columns[column_name],
            key=lambda w: (
                w["y0"],
                w["x0"],
            ),
        )

        rows = []

        for word in column_words:

            if not rows:

                rows.append(
                    {
                        "column": column_name,
                        "y": word["y0"],
                        "words": [word],
                    }
                )

                continue

            last_row = rows[-1]

            if (
                abs(
                    word["y0"]
                    - last_row["y"]
                )
                <= ROW_Y_TOLERANCE
            ):

                last_row["words"].append(
                    word
                )

                ys = [
                    w["y0"]
                    for w in last_row["words"]
                ]

                last_row["y"] = (
                    sum(ys) / len(ys)
                )

            else:

                rows.append(
                    {
                        "column": column_name,
                        "y": word["y0"],
                        "words": [word],
                    }
                )

        for row in rows:

            row["words"].sort(
                key=lambda w: w["x0"]
            )

            row["raw"] = " ".join(
                w["text"]
                for w in row["words"]
            )

            result.append(row)

    # Reading order:
    # complete left column -> complete right column
    result.sort(
        key=lambda r: (
            0
            if r["column"] == "left"
            else 1,
            r["y"],
        )
    )

    return result


# ============================================================
# METADATA
# ============================================================

def detect_chapter(text):
    text = normalize_basic(text)

    match = re.search(
        r"\bKapitel\s*(\d+)\b",
        text,
        re.IGNORECASE,
    )

    if match:
        return int(match.group(1))

    return None


def detect_book_page(text):
    """
    Handles:
        Sidan 8
        Sidan8
        sidan 30
    """

    text = normalize_basic(text)

    match = re.search(
        r"\bSidan\s*(\d+)\b",
        text,
        re.IGNORECASE,
    )

    if match:
        return int(match.group(1))

    return None


# ============================================================
# NOISE
# ============================================================

def is_header_or_noise(text):
    t = normalize_basic(text)
    low = t.casefold()

    if not t:
        return True

    # Physical PDF page number
    if re.fullmatch(r"\d{1,3}", t):
        return True

    # Header
    if (
        "b1+b2" in low
        and "ordlista" in low
    ):
        return True

    if re.fullmatch(
        r"\(?\s*engelska\s*\)?",
        low,
    ):
        return True

    if re.fullmatch(
        r"\(?\s*svenska\s*\)?",
        low,
    ):
        return True

    if re.fullmatch(
        r"svenska\s+engelska",
        low,
    ):
        return True

    if re.match(
        r"^kopieringsunderlag",
        low,
    ):
        return True

    if low.startswith("©"):
        return True

    if low.startswith("isbn"):
        return True

    return False


# ============================================================
# PRIMARY SWEDISH / ENGLISH SPLIT
# ============================================================

def split_by_unicode_separator(row):
    """
    Preferred split.

    Uses the special spacing character embedded in the PDF
    between Swedish and English.
    """

    words = row["words"]

    boundary_index = None

    for i, word in enumerate(words):

        if contains_separator(
            word["text"]
        ):
            boundary_index = i
            break

    if boundary_index is None:
        return None

    swedish_parts = []
    english_parts = []

    for i, word in enumerate(words):

        text = word["text"]

        if i <= boundary_index:
            swedish_parts.append(text)
        else:
            english_parts.append(text)

    swedish_raw = " ".join(
        swedish_parts
    )

    english_raw = " ".join(
        english_parts
    )

    swedish_raw = strip_separator_chars(
        swedish_raw
    )

    return (
        normalize_basic(swedish_raw),
        normalize_basic(english_raw),
        "UNICODE_SEPARATOR",
    )


# ============================================================
# FALLBACK SPLIT USING MORPHOLOGY
# ============================================================

def split_by_morphology(text):
    """
    Recover rows where the PDF lost the Unicode separator.

    Examples:

        bild (-en, -er, -erna) picture

        skriva (skriver, skrev, skrivit) write

        din (ditt, dina) your

        svarsalternativ (-et, -, -en)
        multiple choice answer

    The closing ')' gives us a strong anchor.

    Important:
    Swedish may continue after morphology:

        lägga (...) sig lie down

    Therefore we test possible split positions after the
    morphology group instead of blindly splitting at ')'.
    """

    text = normalize_basic(text)

    matches = list(
        re.finditer(
            r"\(([^()]*)\)",
            text,
        )
    )

    if not matches:
        return None

    morphology_match = None

    for match in matches:

        if morphology_group_looks_valid(
            match.group(1)
        ):

            morphology_match = match
            break

    if morphology_match is None:
        return None

    before = text[
        :morphology_match.start()
    ].strip()

    forms = normalize_forms(
        morphology_match.group(1)
    )

    after = text[
        morphology_match.end():
    ].strip()

    if not before or not after:
        return None

    # --------------------------------------------------------
    # Most common case:
    #
    # bild (...) picture
    #
    # The first token after ')' is English.
    # --------------------------------------------------------

    after_tokens = after.split()

    if not after_tokens:
        return None

    # Swedish particles/reflexives that commonly appear
    # after morphology inside a lexical expression.
    #
    # This list is intentionally conservative.
    swedish_suffix_tokens = {
        "sig",
        "mig",
        "dig",
        "oss",
        "er",
        "på",
        "av",
        "om",
        "upp",
        "ner",
        "ned",
        "ut",
        "in",
        "fram",
        "till",
        "över",
        "under",
        "ihop",
        "igen",
        "bort",
        "hem",
        "med",
        "för",
        "efter",
        "före",
        "mot",
        "en",
        "ett",
    }

    suffix = []
    english_start = 0

    # We allow at most 3 Swedish suffix tokens.
    # This covers things such as:
    #
    # ta (...) en dusch
    #
    # but we only consume the suffix if there is still
    # something left for the English translation.
    for i, token in enumerate(
        after_tokens[:3]
    ):

        token_clean = token.strip(
            ".,;:!?"
        ).casefold()

        if token_clean in swedish_suffix_tokens:

            if i + 1 < len(after_tokens):

                suffix.append(token)
                english_start = i + 1

                continue

        break

    english_tokens = after_tokens[
        english_start:
    ]

    if not english_tokens:
        return None

    swedish = before

    if suffix:
        swedish += " " + " ".join(suffix)

    english = " ".join(
        english_tokens
    )

    swedish = normalize_basic(swedish)
    english = normalize_basic(english)

    if not swedish or not english:
        return None

    return (
        swedish,
        forms,
        english,
        "MORPHOLOGY_FALLBACK",
    )


# ============================================================
# BUILD CARD FROM ROW
# ============================================================

def parse_vocabulary_row(row):
    """
    Returns:
        {
            swedish,
            forms,
            english,
            method
        }

    or None.
    """

    # --------------------------------------------------------
    # METHOD 1 - Unicode separator
    # --------------------------------------------------------

    primary = split_by_unicode_separator(
        row
    )

    if primary is not None:

        (
            swedish_raw,
            english_raw,
            method,
        ) = primary

        swedish, forms = (
            extract_morphology(
                swedish_raw
            )
        )

        english = normalize_basic(
            english_raw
        )

        if swedish and english:

            return {
                "swedish": swedish,
                "forms": forms,
                "english": english,
                "method": method,
            }

    # --------------------------------------------------------
    # METHOD 2 - morphology fallback
    # --------------------------------------------------------

    fallback = split_by_morphology(
        row["raw"]
    )

    if fallback is not None:

        (
            swedish,
            forms,
            english,
            method,
        ) = fallback

        return {
            "swedish": swedish,
            "forms": forms,
            "english": english,
            "method": method,
        }

    return None


# ============================================================
# CONTINUATIONS
# ============================================================

def english_probably_continues(
    english
):
    english = english.rstrip()

    if not english:
        return True

    if english.endswith(
        SOFT_HYPHEN
    ):
        return True

    if english.endswith(
        (
            ",",
            "/",
            "-",
            "–",
            "—",
        )
    ):
        return True

    return False


def join_english_continuation(
    previous,
    continuation,
):
    previous = previous.rstrip()
    continuation = continuation.strip()

    if previous.endswith(
        SOFT_HYPHEN
    ):

        previous = previous[:-1]

        return normalize_basic(
            previous + continuation
        )

    if previous.endswith("-"):

        return normalize_basic(
            previous + continuation
        )

    if previous.endswith("/"):

        return normalize_basic(
            previous + " " + continuation
        )

    return normalize_basic(
        previous + " " + continuation
    )


# ============================================================
# PAGE STATE
# ============================================================

def infer_start_page_for_right_column(
    left_end_page,
    right_rows,
):
    """
    If the right column starts before its own next Sidan marker,
    it continues the page active at the end of the left column.

    Example physical PDF page 1:

        LEFT:
            Sidan 8
            ...

        RIGHT:
            kylskåp ...
            ...
            Sidan 9

    Entries before Sidan 9 still belong to Sidan 8.
    """

    return left_end_page


# ============================================================
# PARSER
# ============================================================

def parse_pdf():

    doc = pymupdf.open(
        PDF_PATH
    )

    cards = []
    rejected = []
    qa_events = []

    current_chapter = None

    # Global textbook page state.
    #
    # This is carried across physical PDF pages.
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
        # Process columns in actual reading order:
        # LEFT -> RIGHT
        # ----------------------------------------------------

        for column, column_rows in (
            ("left", left_rows),
            ("right", right_rows),
        ):

            # Right column inherits page state reached
            # at the end of the left column.
            if column == "right":

                current_book_page = (
                    infer_start_page_for_right_column(
                        current_book_page,
                        right_rows,
                    )
                )

            previous_card = None
            previous_card_y = None

            for row in column_rows:

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

                    current_chapter = (
                        chapter
                    )

                    previous_card = None
                    previous_card_y = None

                    continue

                # --------------------------------------------
                # Sidan marker
                # --------------------------------------------

                book_page = detect_book_page(
                    clean
                )

                if book_page is not None:

                    current_book_page = (
                        book_page
                    )

                    previous_card = None
                    previous_card_y = None

                    continue

                # --------------------------------------------
                # Noise
                # --------------------------------------------

                if is_header_or_noise(
                    clean
                ):
                    continue

                # --------------------------------------------
                # Vocabulary
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

                    continue

                # --------------------------------------------
                # Possible English continuation
                # --------------------------------------------

                close_to_previous = (
                    previous_card is not None
                    and previous_card_y
                    is not None
                    and 0
                    < (
                        row["y"]
                        - previous_card_y
                    )
                    < 24
                )

                strong_continuation = (
                    previous_card is not None
                    and english_probably_continues(
                        previous_card[
                            "english"
                        ]
                    )
                )

                if (
                    close_to_previous
                    and strong_continuation
                ):

                    old_english = (
                        previous_card[
                            "english"
                        ]
                    )

                    new_english = (
                        join_english_continuation(
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
                                "AUTO_JOINED_ENGLISH"
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
                        }
                    )

                    previous_card_y = (
                        row["y"]
                    )

                    continue

                # --------------------------------------------
                # Unresolved
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


# ============================================================
# QA
# ============================================================

def run_qa(
    cards,
    rejected,
    qa_events,
):

    qa = []

    # --------------------------------------------------------
    # Remaining parentheses
    # --------------------------------------------------------

    for card in cards:

        if (
            "(" in card["swedish"]
            or ")" in card["swedish"]
        ):

            qa.append(
                {
                    "reasons": [
                        "PARENTHESES_REMAIN_IN_SWEDISH"
                    ],
                    "card": card,
                }
            )

    # --------------------------------------------------------
    # Missing page/chapter
    # --------------------------------------------------------

    for card in cards:

        reasons = []

        if card["page"] is None:
            reasons.append(
                "NO_PAGE"
            )

        if card["chapter"] is None:
            reasons.append(
                "NO_CHAPTER"
            )

        if reasons:

            qa.append(
                {
                    "reasons": reasons,
                    "card": card,
                }
            )

    # --------------------------------------------------------
    # Soft hyphen
    # --------------------------------------------------------

    for card in cards:

        if (
            SOFT_HYPHEN
            in card["swedish"]
            or SOFT_HYPHEN
            in card["forms"]
            or SOFT_HYPHEN
            in card["english"]
        ):

            qa.append(
                {
                    "reasons": [
                        "SOFT_HYPHEN_REMAINS"
                    ],
                    "card": card,
                }
            )

    # --------------------------------------------------------
    # Empty fields
    # --------------------------------------------------------

    for card in cards:

        reasons = []

        if not card[
            "swedish"
        ].strip():

            reasons.append(
                "EMPTY_SWEDISH"
            )

        if not card[
            "english"
        ].strip():

            reasons.append(
                "EMPTY_ENGLISH"
            )

        if reasons:

            qa.append(
                {
                    "reasons": reasons,
                    "card": card,
                }
            )

    # --------------------------------------------------------
    # Suspicious endings
    # --------------------------------------------------------

    for card in cards:

        english = card[
            "english"
        ]

        reasons = []

        if english.endswith(","):
            reasons.append(
                "ENGLISH_ENDS_COMMA"
            )

        if english.endswith("-"):
            reasons.append(
                "ENGLISH_ENDS_HYPHEN"
            )

        if english.endswith("/"):
            reasons.append(
                "ENGLISH_ENDS_SLASH"
            )

        if reasons:

            qa.append(
                {
                    "reasons": reasons,
                    "card": card,
                }
            )

    # --------------------------------------------------------
    # Exact duplicates
    # --------------------------------------------------------

    duplicate_map = defaultdict(
        list
    )

    for card in cards:

        key = (
            card["swedish"].casefold(),
            card["forms"].casefold(),
            card["english"].casefold(),
        )

        duplicate_map[key].append(
            card
        )

    duplicates = []

    for key, group in (
        duplicate_map.items()
    ):

        if len(group) > 1:

            duplicates.append(
                {
                    "swedish": (
                        group[0][
                            "swedish"
                        ]
                    ),
                    "forms": (
                        group[0][
                            "forms"
                        ]
                    ),
                    "english": (
                        group[0][
                            "english"
                        ]
                    ),
                    "count": len(
                        group
                    ),
                    "cards": group,
                }
            )

    fallback_events = [
        event
        for event in qa_events
        if event["type"]
        == "MORPHOLOGY_FALLBACK"
    ]

    joined_events = [
        event
        for event in qa_events
        if event["type"]
        == "AUTO_JOINED_ENGLISH"
    ]

    return {
        "summary": {
            "cards": len(cards),
            "rejected_rows": (
                len(rejected)
            ),
            "qa_items": len(qa),
            "morphology_fallbacks": (
                len(fallback_events)
            ),
            "auto_joined_english": (
                len(joined_events)
            ),
            "exact_duplicate_groups": (
                len(duplicates)
            ),
        },
        "qa": qa,
        "morphology_fallbacks": (
            fallback_events
        ),
        "auto_joined_english": (
            joined_events
        ),
        "exact_duplicates": (
            duplicates
        ),
    }


# ============================================================
# SAVE
# ============================================================

def save_json(
    path,
    data,
):

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )


# ============================================================
# REPORT
# ============================================================

def print_report(
    cards,
    rejected,
    qa_report,
):

    print()
    print("=" * 72)
    print(
        "SVENSKAKORT - B1/B2 PARSER V4"
    )
    print("=" * 72)

    print(
        f"Parsed cards:             "
        f"{len(cards)}"
    )

    print(
        f"Rejected rows:            "
        f"{len(rejected)}"
    )

    chapters = sorted(
        {
            card["chapter"]
            for card in cards
            if card["chapter"]
            is not None
        }
    )

    print(
        f"Chapters detected:        "
        f"{chapters}"
    )

    no_page = [
        card
        for card in cards
        if card["page"] is None
    ]

    print(
        f"Cards without page:       "
        f"{len(no_page)}"
    )

    parentheses_remaining = [
        card
        for card in cards
        if (
            "(" in card["swedish"]
            or ")" in card["swedish"]
        )
    ]

    print(
        f"Parentheses remaining:    "
        f"{len(parentheses_remaining)}"
    )

    soft_hyphens = [
        card
        for card in cards
        if (
            SOFT_HYPHEN
            in card["swedish"]
            or SOFT_HYPHEN
            in card["forms"]
            or SOFT_HYPHEN
            in card["english"]
        )
    ]

    print(
        f"Soft hyphens remaining:   "
        f"{len(soft_hyphens)}"
    )

    print(
        f"Morphology fallbacks:     "
        f"{len(qa_report['morphology_fallbacks'])}"
    )

    print(
        f"English continuations:    "
        f"{len(qa_report['auto_joined_english'])}"
    )

    print(
        f"Exact duplicate groups:   "
        f"{len(qa_report['exact_duplicates'])}"
    )

    # --------------------------------------------------------
    # Cards per chapter
    # --------------------------------------------------------

    chapter_counts = Counter(
        card["chapter"]
        for card in cards
    )

    print()
    print(
        "CARDS PER CHAPTER"
    )
    print("-" * 72)

    for chapter in sorted(
        c
        for c in chapter_counts
        if c is not None
    ):

        print(
            f"Chapter {chapter:2d}: "
            f"{chapter_counts[chapter]}"
        )

    # --------------------------------------------------------
    # Morphology tests
    # --------------------------------------------------------

    wanted_examples = [
        "lägga sig",
        "åka till",
        "tänka på",
        "må bra",
        "bygga upp",
        "känna sig/mig",
        "stryka under",
        "ta en dusch",
        "komma ihåg",
        "ringa till",
    ]

    print()
    print(
        "MORPHOLOGY TEST"
    )
    print("-" * 72)

    card_by_swedish = (
        defaultdict(list)
    )

    for card in cards:

        card_by_swedish[
            card[
                "swedish"
            ].casefold()
        ].append(card)

    for wanted in wanted_examples:

        found = card_by_swedish.get(
            wanted.casefold(),
            [],
        )

        if found:

            card = found[0]

            print(
                f"OK   "
                f"{card['swedish']} "
                f"| forms="
                f"{card['forms']} "
                f"| EN="
                f"{card['english']}"
            )

        else:

            print(
                f"MISS {wanted}"
            )

    # --------------------------------------------------------
    # Fallback examples
    # --------------------------------------------------------

    print()
    print(
        "MORPHOLOGY FALLBACK - FIRST 30"
    )
    print("-" * 72)

    for event in (
        qa_report[
            "morphology_fallbacks"
        ][:30]
    ):

        print(
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
    # Continuations
    # --------------------------------------------------------

    print()
    print(
        "AUTO-JOINED ENGLISH - FIRST 20"
    )
    print("-" * 72)

    for event in (
        qa_report[
            "auto_joined_english"
        ][:20]
    ):

        print(
            f"{event['swedish']}: "
            f"{event['before']!r} "
            f"+ "
            f"{event['continuation']!r} "
            f"-> "
            f"{event['after']!r}"
        )

    # --------------------------------------------------------
    # No-page examples
    # --------------------------------------------------------

    print()
    print(
        "NO PAGE - FIRST 30"
    )
    print("-" * 72)

    for card in no_page[:30]:

        print(
            f"PDF "
            f"{card['source_pdf_page']:2d}"
            f" | chapter="
            f"{card['chapter']}"
            f" | "
            f"{card['swedish']}"
            f" -> "
            f"{card['english']}"
        )

    # --------------------------------------------------------
    # Rejected
    # --------------------------------------------------------

    print()
    print(
        "REJECTED ROWS - FIRST 50"
    )
    print("-" * 72)

    for item in rejected[:50]:

        print(
            f"PDF "
            f"{item['source_pdf_page']:2d}"
            f" | "
            f"{item['column']:5s}"
            f" | chapter="
            f"{item['chapter']}"
            f" | page="
            f"{item['page']}"
            f" | "
            f"{item['reason']}"
            f" | "
            f"{item['raw']}"
        )

    print()
    print(
        "OUTPUT FILES"
    )
    print("-" * 72)

    print(OUTPUT_JSON)
    print(REJECTED_JSON)
    print(QA_JSON)

    print()
    print("=" * 72)
    print("DONE")
    print("=" * 72)


# ============================================================
# MAIN
# ============================================================

def main():

    if not PDF_PATH.exists():

        raise FileNotFoundError(
            f"PDF not found:\n"
            f"{PDF_PATH}"
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    (
        cards,
        rejected,
        qa_events,
    ) = parse_pdf()

    qa_report = run_qa(
        cards,
        rejected,
        qa_events,
    )

    save_json(
        OUTPUT_JSON,
        cards,
    )

    save_json(
        REJECTED_JSON,
        rejected,
    )

    save_json(
        QA_JSON,
        qa_report,
    )

    print_report(
        cards,
        rejected,
        qa_report,
    )


if __name__ == "__main__":
    main()