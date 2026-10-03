import json
import re
import unicodedata
from collections import Counter
from pathlib import Path


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

WORDS_FILE = BASE_DIR / "words.json"
LEXICON_FILE = BASE_DIR / "lexicon-sv" / "lexicon.txt"

OUTPUT_FILE = BASE_DIR / "nst_ipa_audit_v5.json"

SAFE_FILE = BASE_DIR / "nst_ipa_safe_v5.json"
REVIEW_FILE = BASE_DIR / "nst_ipa_review_v5.json"
TWO_WORD_FILE = BASE_DIR / "nst_ipa_two_word_review_v5.json"
MISSING_FILE = BASE_DIR / "nst_ipa_missing_v5.json"
SKIPPED_FILE = BASE_DIR / "nst_ipa_skipped_v5.json"


# ============================================================
# SAMPA -> IPA
#
# Direct NST SAMPA -> IPA conversion.
#
# IMPORTANT:
# - no consonant-length inference
# - no pitch-accent inference
# - no pronunciation guessing
# - no modification of words.json
# ============================================================

SAMPA_TO_IPA = {

    # Vowels
    "i:": "iː",
    "I": "ɪ",

    "y:": "yː",
    "Y": "ʏ",

    "u0": "ɵ",
    "}:": "ʉː",

    "e:": "eː",
    "e": "e",

    "2:": "øː",
    "9": "œ",

    "E:": "ɛː",
    "E": "ɛ",

    "u:": "uː",
    "U": "ʊ",

    "o:": "oː",
    "O": "ɔ",

    "A:": "ɑː",
    "a": "a",

    "@": "ə",

    # Diphthongs
    "a*U": "aʊ",
    "E*U": "ɛʊ",

    # Stops
    "p": "p",
    "b": "b",
    "t": "t",
    "d": "d",
    "k": "k",
    "g": "ɡ",

    # Retroflex stops
    "t`": "ʈ",
    "d`": "ɖ",

    # Nasals
    "m": "m",
    "n": "n",
    "N": "ŋ",
    "n`": "ɳ",

    # Fricatives
    "f": "f",
    "v": "v",
    "s": "s",
    "h": "h",

    # Swedish sounds
    "s'": "ɕ",
    "S": "ɧ",
    "x\\": "ɧ",
    "s`": "ʂ",

    # Approximants / liquids
    "r": "r",
    "l": "l",
    "j": "j",
    "l`": "ɭ",

    # Foreign phones
    "w": "w",
    "T": "θ",
    "D": "ð",
    "tC": "tɕ",
}


# ============================================================
# BASIC NORMALIZATION
# ============================================================

def normalize_unicode(text):
    return unicodedata.normalize(
        "NFC",
        str(text),
    )


def normalize_spaces(text):
    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


# ============================================================
# INFLECTION CLEANING - NEW IN V5
# ============================================================

def remove_inflection_annotations(text):
    """
    Remove dictionary-style inflection information from the
    Swedish flashcard expression.

    Examples:

        fika (-t)
            -> fika

        vattengympa (-n)
            -> vattengympa

        logisk(-t, -a)
            -> logisk

        utländsk(-t, -a)
            -> utländsk

        tysk(-t, -a)
            -> tysk

        ledig (-t, -a)
            -> ledig

    IMPORTANT:
    We only remove parentheses that look like morphological /
    inflection annotations.

    We do NOT blindly remove every parenthesized expression.
    """

    original = text

    # --------------------------------------------------------
    # Pattern:
    #
    # (...)
    #
    # is treated as an inflection annotation if the content
    # consists only of:
    #
    # letters
    # hyphens
    # commas
    # spaces
    # slashes
    #
    # AND contains at least one hyphen.
    #
    # This targets forms such as:
    #
    # (-n)
    # (-t)
    # (-a)
    # (-t, -a)
    # (-en, -ar)
    #
    # --------------------------------------------------------

    pattern = re.compile(
        r"\(\s*"
        r"(?=[^)]*-)"
        r"[A-Za-zÅÄÖåäöÉéÜüÆæØø"
        r"\-\s,\/]+"
        r"\)"
    )

    cleaned = pattern.sub(
        "",
        text,
    )

    cleaned = normalize_spaces(
        cleaned
    )

    return cleaned, cleaned != original


# ============================================================
# EXPRESSION NORMALIZATION
# ============================================================

def normalize_expression(text):
    """
    Prepare a Swedish flashcard expression for NST matching.

    V5 order:

        1. Unicode normalization
        2. whitespace cleanup
        3. remove inflection annotations
        4. remove surrounding punctuation
        5. lowercase
    """

    original = normalize_unicode(
        text
    )

    text = normalize_spaces(
        original
    )

    text, inflection_removed = (
        remove_inflection_annotations(
            text
        )
    )

    # Remove punctuation surrounding the WHOLE expression.
    #
    # Internal hyphens remain untouched:
    #
    # it-ingenjör
    # e-post
    #
    text = text.strip(
        " \t\r\n"
        ".,!?;:"
        "\"'“”‘’"
        "()[]{}"
    )

    text = normalize_spaces(
        text
    )

    normalized = text.lower()

    return {
        "original": original,
        "normalized": normalized,
        "inflection_removed":
            inflection_removed,
    }


# ============================================================
# SAMPA PARSING
# ============================================================

def parse_sampa_token(token):

    token = token.strip()

    if not token:
        return "", None

    prefix = ""

    while (
        token
        and token[0] in {'"', '%', '$'}
    ):

        marker = token[0]

        token = token[1:]

        if marker == '"':
            prefix += "ˈ"

        elif marker == "%":
            prefix += "ˌ"

        elif marker == "$":
            # Boundary marker.
            pass

    # Defensive handling in case $ occurs
    # inside the token.
    token = token.replace(
        "$",
        "",
    )

    if not token:
        return prefix, None

    ipa = SAMPA_TO_IPA.get(
        token
    )

    if ipa is None:

        return (
            prefix + f"[{token}]",
            token,
        )

    return prefix + ipa, None


def sampa_to_ipa(sampa):

    sampa = normalize_unicode(
        sampa
    ).strip()

    if not sampa:

        return {
            "ipa": "",
            "unknown_symbols": [],
        }

    ipa_parts = []
    unknown_symbols = []

    for token in sampa.split():

        ipa_part, unknown = (
            parse_sampa_token(
                token
            )
        )

        ipa_parts.append(
            ipa_part
        )

        if unknown is not None:

            unknown_symbols.append(
                unknown
            )

    return {
        "ipa": "".join(
            ipa_parts
        ),
        "unknown_symbols":
            unknown_symbols,
    }


# ============================================================
# LOAD WORDS.JSON
# ============================================================

def load_words():

    print(
        "Loading flashcards:"
    )

    print(
        f"  {WORDS_FILE}"
    )

    with open(
        WORDS_FILE,
        "r",
        encoding="utf-8",
    ) as f:

        data = json.load(f)

    if isinstance(data, list):

        words = data

    elif (
        isinstance(data, dict)
        and isinstance(
            data.get("words"),
            list,
        )
    ):

        words = data["words"]

    else:

        raise ValueError(
            "Unexpected words.json structure."
        )

    print(
        f"Flashcards loaded: {len(words)}"
    )

    print()

    return words


# ============================================================
# LOAD NST
# ============================================================

def load_nst_lexicon():

    print(
        "Loading NST lexicon:"
    )

    print(
        f"  {LEXICON_FILE}"
    )

    print()

    lexicon = {}

    line_count = 0
    pronunciation_count = 0

    with open(
        LEXICON_FILE,
        "r",
        encoding="utf-8-sig",
        errors="replace",
    ) as f:

        for line in f:

            line_count += 1

            line = line.strip()

            if not line:
                continue

            parts = line.split(
                maxsplit=1
            )

            if len(parts) != 2:
                continue

            word = parts[0]
            pronunciation = parts[1]

            word_info = (
                normalize_expression(
                    word
                )
            )

            normalized_word = (
                word_info[
                    "normalized"
                ]
            )

            if not normalized_word:
                continue

            pronunciation = (
                pronunciation.strip()
            )

            if not pronunciation:
                continue

            lexicon.setdefault(
                normalized_word,
                [],
            )

            # Avoid exact duplicate pronunciation
            # lines in the dictionary.
            if (
                pronunciation
                not in lexicon[
                    normalized_word
                ]
            ):

                lexicon[
                    normalized_word
                ].append(
                    pronunciation
                )

                pronunciation_count += 1

    print(
        "NST lexicon loaded."
    )

    print(
        f"Lines read:             "
        f"{line_count}"
    )

    print(
        f"Unique entries:         "
        f"{len(lexicon)}"
    )

    print(
        f"Pronunciations loaded:  "
        f"{pronunciation_count}"
    )

    print()

    return lexicon


# ============================================================
# CONVERT PRONUNCIATIONS
# ============================================================

def convert_pronunciations(
    pronunciations,
):

    converted = []

    unknown_counter = Counter()

    for sampa in pronunciations:

        result = sampa_to_ipa(
            sampa
        )

        converted.append(
            {
                "sampa": sampa,
                "ipa":
                    result["ipa"],
                "unknown_symbols":
                    result[
                        "unknown_symbols"
                    ],
            }
        )

        for symbol in (
            result[
                "unknown_symbols"
            ]
        ):

            unknown_counter[
                symbol
            ] += 1

    # Deduplicate IPA while preserving
    # original NST order.
    distinct_ipa = list(
        dict.fromkeys(
            pronunciation["ipa"]
            for pronunciation
            in converted
            if pronunciation["ipa"]
        )
    )

    return {
        "pronunciations":
            converted,

        "distinct_ipa":
            distinct_ipa,

        "unknown_counter":
            unknown_counter,
    }


# ============================================================
# ONE-WORD CLASSIFICATION
# ============================================================

def classify_one_word(
    original,
    normalized,
    inflection_removed,
    lexicon,
):

    pronunciations = lexicon.get(
        normalized
    )

    # --------------------------------------------------------
    # MISSING
    # --------------------------------------------------------

    if not pronunciations:

        return {
            "status": "MISSING",

            "word": original,

            "normalized":
                normalized,

            "word_count": 1,

            "inflection_removed":
                inflection_removed,
        }

    result = convert_pronunciations(
        pronunciations
    )

    distinct_ipa = (
        result["distinct_ipa"]
    )

    has_unknown = bool(
        result["unknown_counter"]
    )

    # --------------------------------------------------------
    # SAFE
    # --------------------------------------------------------

    if (
        len(distinct_ipa) == 1
        and not has_unknown
    ):

        status = "SAFE"

    # --------------------------------------------------------
    # REVIEW
    # --------------------------------------------------------

    else:

        status = "REVIEW"

    entry = {
        "status": status,

        "word": original,

        "normalized":
            normalized,

        "word_count": 1,

        "inflection_removed":
            inflection_removed,

        "pronunciations":
            result[
                "pronunciations"
            ],

        "distinct_ipa":
            distinct_ipa,
    }

    if status == "SAFE":

        entry["selected_ipa"] = (
            distinct_ipa[0]
        )

    return entry


# ============================================================
# TWO-WORD CLASSIFICATION
# ============================================================

def classify_two_word(
    original,
    normalized,
    inflection_removed,
    lexicon,
):

    parts = normalized.split()

    component_data = []

    all_components_found = True

    for part in parts:

        pronunciations = (
            lexicon.get(
                part
            )
        )

        if not pronunciations:

            all_components_found = False

            component_data.append(
                {
                    "word": part,
                    "found": False,
                    "pronunciations": [],
                    "distinct_ipa": [],
                }
            )

            continue

        result = (
            convert_pronunciations(
                pronunciations
            )
        )

        component_data.append(
            {
                "word": part,

                "found": True,

                "pronunciations":
                    result[
                        "pronunciations"
                    ],

                "distinct_ipa":
                    result[
                        "distinct_ipa"
                    ],
            }
        )

    # --------------------------------------------------------
    # Direct two-word NST lookup
    #
    # We keep this only as diagnostic information.
    # Even a direct match is NOT automatically SAFE.
    # --------------------------------------------------------

    direct_pronunciations = (
        lexicon.get(
            normalized
        )
    )

    direct_data = None

    if direct_pronunciations:

        result = (
            convert_pronunciations(
                direct_pronunciations
            )
        )

        direct_data = {
            "pronunciations":
                result[
                    "pronunciations"
                ],

            "distinct_ipa":
                result[
                    "distinct_ipa"
                ],
        }

    return {
        "status":
            "REVIEW_TWO_WORD",

        "word":
            original,

        "normalized":
            normalized,

        "word_count": 2,

        "inflection_removed":
            inflection_removed,

        "direct_nst_match":
            direct_data is not None,

        "direct_pronunciation":
            direct_data,

        "all_components_found":
            all_components_found,

        "components":
            component_data,
    }


# ============================================================
# AUDIT
# ============================================================

def audit(
    words,
    lexicon,
):

    safe = []
    review = []
    two_word_review = []
    missing = []
    skipped = []

    inflection_cleaned = []

    unknown_counter = Counter()

    one_word_total = 0
    two_word_total = 0

    for word_data in words:

        original = str(
            word_data.get(
                "swedish",
                "",
            )
        ).strip()

        normalization = (
            normalize_expression(
                original
            )
        )

        normalized = (
            normalization[
                "normalized"
            ]
        )

        inflection_removed = (
            normalization[
                "inflection_removed"
            ]
        )

        # ----------------------------------------------------
        # Record every expression changed by V5 cleaning.
        # ----------------------------------------------------

        if inflection_removed:

            inflection_cleaned.append(
                {
                    "original":
                        original,

                    "normalized":
                        normalized,
                }
            )

        # ----------------------------------------------------
        # EMPTY
        # ----------------------------------------------------

        if not normalized:

            skipped.append(
                {
                    "word":
                        original,

                    "normalized":
                        normalized,

                    "reason":
                        "empty_after_normalization",
                }
            )

            continue

        parts = (
            normalized.split()
        )

        word_count = len(parts)

        # ----------------------------------------------------
        # 3+ WORDS
        # ----------------------------------------------------

        if word_count > 2:

            skipped.append(
                {
                    "word":
                        original,

                    "normalized":
                        normalized,

                    "word_count":
                        word_count,

                    "inflection_removed":
                        inflection_removed,

                    "reason":
                        "3_plus_words",
                }
            )

            continue

        # ----------------------------------------------------
        # ONE WORD
        # ----------------------------------------------------

        if word_count == 1:

            one_word_total += 1

            entry = (
                classify_one_word(
                    original,
                    normalized,
                    inflection_removed,
                    lexicon,
                )
            )

            status = entry[
                "status"
            ]

            if status == "SAFE":

                safe.append(
                    entry
                )

            elif status == "REVIEW":

                review.append(
                    entry
                )

            else:

                missing.append(
                    entry
                )

            for pronunciation in (
                entry.get(
                    "pronunciations",
                    [],
                )
            ):

                for symbol in (
                    pronunciation.get(
                        "unknown_symbols",
                        [],
                    )
                ):

                    unknown_counter[
                        symbol
                    ] += 1

            continue

        # ----------------------------------------------------
        # TWO WORDS
        # ----------------------------------------------------

        if word_count == 2:

            two_word_total += 1

            entry = (
                classify_two_word(
                    original,
                    normalized,
                    inflection_removed,
                    lexicon,
                )
            )

            two_word_review.append(
                entry
            )

            # Component unknown symbols
            for component in (
                entry[
                    "components"
                ]
            ):

                for pronunciation in (
                    component.get(
                        "pronunciations",
                        [],
                    )
                ):

                    for symbol in (
                        pronunciation.get(
                            "unknown_symbols",
                            [],
                        )
                    ):

                        unknown_counter[
                            symbol
                        ] += 1

            # Direct expression unknown symbols
            direct = entry.get(
                "direct_pronunciation"
            )

            if direct:

                for pronunciation in (
                    direct.get(
                        "pronunciations",
                        [],
                    )
                ):

                    for symbol in (
                        pronunciation.get(
                            "unknown_symbols",
                            [],
                        )
                    ):

                        unknown_counter[
                            symbol
                        ] += 1

    # ========================================================
    # STATISTICS
    # ========================================================

    eligible = (
        one_word_total
        + two_word_total
    )

    classified = (
        len(safe)
        + len(review)
        + len(two_word_review)
        + len(missing)
    )

    safe_percent = (
        len(safe)
        / eligible
        * 100
        if eligible
        else 0
    )

    one_word_found = (
        len(safe)
        + len(review)
    )

    two_word_all_components_found = (
        sum(
            1
            for entry
            in two_word_review
            if entry[
                "all_components_found"
            ]
        )
    )

    two_word_direct_matches = (
        sum(
            1
            for entry
            in two_word_review
            if entry[
                "direct_nst_match"
            ]
        )
    )

    # --------------------------------------------------------
    # How many cleaned entries became SAFE?
    # --------------------------------------------------------

    cleaned_safe = sum(
        1
        for entry in safe
        if entry[
            "inflection_removed"
        ]
    )

    cleaned_review = sum(
        1
        for entry in review
        if entry[
            "inflection_removed"
        ]
    )

    cleaned_missing = sum(
        1
        for entry in missing
        if entry[
            "inflection_removed"
        ]
    )

    cleaned_two_word = sum(
        1
        for entry in two_word_review
        if entry[
            "inflection_removed"
        ]
    )

    statistics = {

        "total_flashcards":
            len(words),

        "eligible_1_2_words":
            eligible,

        "classified":
            classified,

        "skipped_3_plus_or_empty":
            len(skipped),

        "SAFE":
            len(safe),

        "REVIEW":
            len(review),

        "REVIEW_TWO_WORD":
            len(two_word_review),

        "MISSING":
            len(missing),

        "safe_percent_of_eligible":
            round(
                safe_percent,
                2,
            ),

        "one_word_total":
            one_word_total,

        "one_word_found_in_nst":
            one_word_found,

        "one_word_missing":
            len(missing),

        "two_word_total":
            two_word_total,

        "two_word_all_components_found":
            two_word_all_components_found,

        "two_word_direct_nst_matches":
            two_word_direct_matches,

        "inflection_annotations_removed":
            len(
                inflection_cleaned
            ),

        "cleaned_entries_now_SAFE":
            cleaned_safe,

        "cleaned_entries_now_REVIEW":
            cleaned_review,

        "cleaned_entries_still_MISSING":
            cleaned_missing,

        "cleaned_entries_still_TWO_WORD":
            cleaned_two_word,

        "unknown_symbol_occurrences":
            sum(
                unknown_counter.values()
            ),

        "unique_unknown_symbols":
            len(
                unknown_counter
            ),
    }

    return {

        "statistics":
            statistics,

        "unknown_symbols":
            dict(
                unknown_counter.most_common()
            ),

        "inflection_cleaned":
            inflection_cleaned,

        "SAFE":
            safe,

        "REVIEW":
            review,

        "REVIEW_TWO_WORD":
            two_word_review,

        "MISSING":
            missing,

        "SKIPPED":
            skipped,
    }


# ============================================================
# SAVE JSON
# ============================================================

def save_json(
    path,
    data,
):

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
# PRINT INFLECTION EXAMPLES
# ============================================================

def print_inflection_examples(
    report,
):

    entries = report[
        "inflection_cleaned"
    ]

    print()
    print("=" * 72)
    print("INFLECTION CLEANING - V5")
    print("=" * 72)

    print(
        f"Expressions cleaned: "
        f"{len(entries)}"
    )

    print()

    for entry in entries[:30]:

        print(
            f"{entry['original']}"
            f"  ->  "
            f"{entry['normalized']}"
        )


# ============================================================
# PRINT REVIEW EXAMPLES
# ============================================================

def print_review_examples(
    report,
):

    print()
    print("=" * 72)
    print("REVIEW - MULTIPLE IPA")
    print("=" * 72)

    entries = report[
        "REVIEW"
    ]

    for entry in entries[:30]:

        print()
        print(
            entry["word"]
        )

        for ipa in (
            entry[
                "distinct_ipa"
            ]
        ):

            print(
                f"  /{ipa}/"
            )


# ============================================================
# PRINT MISSING
# ============================================================

def print_missing(
    report,
):

    print()
    print("=" * 72)
    print("FIRST 50 MISSING")
    print("=" * 72)

    for entry in (
        report[
            "MISSING"
        ][:50]
    ):

        print(
            entry["word"]
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 72)
    print("NST SWEDISH IPA AUDIT V5")
    print("=" * 72)

    print()
    print(
        "V5 changes:"
    )

    print(
        "  - inflection annotations are removed before matching"
    )

    print(
        "  - direct SAMPA -> IPA only"
    )

    print(
        "  - no consonant-length inference"
    )

    print(
        "  - no automatic choice between multiple pronunciations"
    )

    print(
        "  - two-word expressions remain REVIEW"
    )

    print(
        "  - words.json is NOT modified"
    )

    print()

    # ========================================================
    # LOAD
    # ========================================================

    words = load_words()

    lexicon = (
        load_nst_lexicon()
    )

    # ========================================================
    # AUDIT
    # ========================================================

    print(
        "Running V5 audit..."
    )

    report = audit(
        words,
        lexicon,
    )

    stats = report[
        "statistics"
    ]

    # ========================================================
    # SAVE
    # ========================================================

    save_json(
        OUTPUT_FILE,
        report,
    )

    save_json(
        SAFE_FILE,
        report["SAFE"],
    )

    save_json(
        REVIEW_FILE,
        report["REVIEW"],
    )

    save_json(
        TWO_WORD_FILE,
        report[
            "REVIEW_TWO_WORD"
        ],
    )

    save_json(
        MISSING_FILE,
        report["MISSING"],
    )

    save_json(
        SKIPPED_FILE,
        report["SKIPPED"],
    )

    # ========================================================
    # RESULTS
    # ========================================================

    print()
    print("=" * 72)
    print("AUDIT RESULTS V5")
    print("=" * 72)

    for key, value in (
        stats.items()
    ):

        print(
            f"{key:38s}: "
            f"{value}"
        )

    print()
    print(
        "Unknown SAMPA symbols:"
    )

    if report[
        "unknown_symbols"
    ]:

        for symbol, count in (
            report[
                "unknown_symbols"
            ].items()
        ):

            print(
                f"  {symbol!r}: "
                f"{count}"
            )

    else:

        print(
            "  NONE"
        )

    # ========================================================
    # DETAILS
    # ========================================================

    print_inflection_examples(
        report
    )

    print_review_examples(
        report
    )

    print_missing(
        report
    )

    # ========================================================
    # OUTPUT
    # ========================================================

    print()
    print("=" * 72)
    print("OUTPUT FILES")
    print("=" * 72)

    print(
        f"Full audit:\n"
        f"  {OUTPUT_FILE}"
    )

    print(
        f"\nSAFE:\n"
        f"  {SAFE_FILE}"
    )

    print(
        f"\nREVIEW:\n"
        f"  {REVIEW_FILE}"
    )

    print(
        f"\nTWO-WORD REVIEW:\n"
        f"  {TWO_WORD_FILE}"
    )

    print(
        f"\nMISSING:\n"
        f"  {MISSING_FILE}"
    )

    print(
        f"\nSKIPPED:\n"
        f"  {SKIPPED_FILE}"
    )

    print()

    print("=" * 72)
    print(
        "IMPORTANT: words.json was NOT modified."
    )
    print("=" * 72)


if __name__ == "__main__":
    main()