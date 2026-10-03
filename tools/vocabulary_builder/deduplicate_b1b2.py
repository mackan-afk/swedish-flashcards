import json
import re
from pathlib import Path
from collections import defaultdict, Counter


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"

INPUT_FILE = OUTPUT_DIR / "b1b2_clean.json"

OUTPUT_FILE = OUTPUT_DIR / "b1b2_deduplicated.json"
REPORT_FILE = OUTPUT_DIR / "b1b2_dedup_report.txt"
REVIEW_FILE = OUTPUT_DIR / "b1b2_semantic_review.json"


# ============================================================
# HELPERS
# ============================================================

def load_json(path):
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
    """
    Conservative normalization used only for duplicate matching.
    Original text is never replaced with this normalized version.
    """

    if not isinstance(value, str):
        return ""

    value = value.strip()
    value = re.sub(r"\s+", " ", value)

    return value.casefold()


def normalize_forms(value):
    if not isinstance(value, str):
        return ""

    value = value.strip()
    value = re.sub(r"\s+", " ", value)

    return value.casefold()


def card_sort_key(card):
    """
    Prefer original Rivstart cards with the lowest/earliest ID.
    Manual cards naturally sort after riv_b_XXXX.
    """

    card_id = card.get("id", "")

    match = re.fullmatch(r"riv_b_(\d+)", card_id)

    if match:
        return (0, int(match.group(1)), card_id)

    match = re.fullmatch(
        r"riv_b_manual_(\d+)",
        card_id,
    )

    if match:
        return (1, int(match.group(1)), card_id)

    return (2, 999999, card_id)


def choose_best_forms(cards):
    """
    If the same Swedish+English card appears multiple times,
    keep the most informative morphology.

    We do NOT combine unrelated morphology strings.
    We simply choose the most complete-looking one.
    """

    candidates = []

    for card in cards:
        forms = card.get("forms", "")

        if not isinstance(forms, str):
            continue

        forms = forms.strip()

        if not forms:
            continue

        candidates.append(forms)

    if not candidates:
        return ""

    # Prefer:
    # 1. more comma-separated morphological elements
    # 2. longer representation
    # 3. deterministic alphabetical tie-break

    def score(forms):
        pieces = [
            x.strip()
            for x in forms.split(",")
            if x.strip()
        ]

        return (
            len(pieces),
            len(forms),
            forms.casefold(),
        )

    return max(candidates, key=score)


def occurrence_from_card(card):
    return {
        "chapter": card.get("chapter"),
        "page": card.get("page"),
        "source_pdf_page": card.get(
            "source_pdf_page"
        ),
        "original_id": card.get("id"),
    }


def occurrence_key(occ):
    return (
        occ.get("chapter"),
        occ.get("page"),
        occ.get("source_pdf_page"),
        occ.get("original_id"),
    )


def merge_occurrences(cards):
    occurrences = []

    for card in cards:

        existing = card.get("occurrences")

        if isinstance(existing, list):

            for occurrence in existing:
                if isinstance(occurrence, dict):
                    occurrences.append(
                        dict(occurrence)
                    )

        else:
            occurrences.append(
                occurrence_from_card(card)
            )

    unique = {}

    for occurrence in occurrences:
        unique[occurrence_key(occurrence)] = occurrence

    result = list(unique.values())

    result.sort(
        key=lambda x: (
            x.get("chapter")
            if isinstance(
                x.get("chapter"), int
            )
            else 999,
            x.get("page")
            if isinstance(
                x.get("page"), int
            )
            else 999999,
            x.get("source_pdf_page")
            if isinstance(
                x.get("source_pdf_page"), int
            )
            else 999999,
            x.get("original_id") or "",
        )
    )

    return result


# ============================================================
# PHASE 1
# SAFE DEDUPLICATION
# ============================================================

def safe_deduplicate(cards):

    groups = defaultdict(list)

    for card in cards:

        key = (
            normalize_text(
                card.get("swedish")
            ),
            normalize_text(
                card.get("english")
            ),
        )

        groups[key].append(card)

    output = []

    merged_groups = []
    removed_cards = 0

    for key, group in groups.items():

        # Not duplicated
        if len(group) == 1:
            output.append(
                dict(group[0])
            )
            continue

        ordered = sorted(
            group,
            key=card_sort_key,
        )

        keeper = dict(ordered[0])

        best_forms = choose_best_forms(
            ordered
        )

        keeper["forms"] = best_forms

        occurrences = merge_occurrences(
            ordered
        )

        keeper["occurrences"] = occurrences

        keeper["chapters"] = sorted({
            occurrence["chapter"]
            for occurrence in occurrences
            if isinstance(
                occurrence.get("chapter"),
                int,
            )
        })

        keeper["deduplicated_from"] = [
            card["id"]
            for card in ordered
            if card["id"] != keeper["id"]
        ]

        output.append(keeper)

        removed_cards += len(group) - 1

        merged_groups.append({
            "swedish": keeper.get(
                "swedish"
            ),
            "english": keeper.get(
                "english"
            ),
            "forms": keeper.get(
                "forms"
            ),
            "kept_id": keeper.get(
                "id"
            ),
            "removed_ids": [
                card.get("id")
                for card in ordered[1:]
            ],
            "chapters": keeper[
                "chapters"
            ],
            "occurrences": occurrences,
        })

    output.sort(
        key=card_sort_key
    )

    return (
        output,
        merged_groups,
        removed_cards,
    )


# ============================================================
# PHASE 2
# FIND SAME SWEDISH WITH DIFFERENT ENGLISH
# ============================================================

def build_semantic_review(cards):

    groups = defaultdict(list)

    for card in cards:

        swedish = normalize_text(
            card.get("swedish")
        )

        groups[swedish].append(card)

    review = []

    for swedish, group in groups.items():

        if len(group) < 2:
            continue

        english_values = {
            normalize_text(
                card.get("english")
            )
            for card in group
        }

        # Same English meaning would already have
        # been handled by safe deduplication.
        if len(english_values) <= 1:
            continue

        review.append({
            "swedish": group[0].get(
                "swedish"
            ),
            "count": len(group),
            "decision": "REVIEW",
            "reason": (
                "Same Swedish headword but "
                "different English translation."
            ),
            "cards": [
                {
                    "id": card.get("id"),
                    "swedish": card.get(
                        "swedish"
                    ),
                    "forms": card.get(
                        "forms"
                    ),
                    "english": card.get(
                        "english"
                    ),
                    "chapter": card.get(
                        "chapter"
                    ),
                    "page": card.get(
                        "page"
                    ),
                    "source_pdf_page":
                        card.get(
                            "source_pdf_page"
                        ),
                }
                for card in sorted(
                    group,
                    key=card_sort_key,
                )
            ],
        })

    review.sort(
        key=lambda x:
        normalize_text(x["swedish"])
    )

    return review


# ============================================================
# VALIDATION
# ============================================================

def validate(cards):

    errors = []

    ids = [
        card.get("id")
        for card in cards
    ]

    id_counts = Counter(ids)

    duplicate_ids = [
        card_id
        for card_id, count
        in id_counts.items()
        if count > 1
    ]

    if duplicate_ids:
        errors.append(
            "Duplicate IDs found: "
            + ", ".join(
                duplicate_ids[:20]
            )
        )

    for card in cards:

        card_id = card.get("id")

        swedish = card.get(
            "swedish"
        )

        english = card.get(
            "english"
        )

        if (
            not isinstance(
                swedish, str
            )
            or not swedish.strip()
        ):
            errors.append(
                f"{card_id}: "
                "empty Swedish"
            )

        if (
            not isinstance(
                english, str
            )
            or not english.strip()
        ):
            errors.append(
                f"{card_id}: "
                "empty English"
            )

    # Make sure safe duplicates are gone
    seen = {}

    for card in cards:

        key = (
            normalize_text(
                card.get("swedish")
            ),
            normalize_text(
                card.get("english")
            ),
        )

        if key in seen:
            errors.append(
                "Safe duplicate survived: "
                f"{card.get('swedish')} / "
                f"{card.get('english')} "
                f"({seen[key]} and "
                f"{card.get('id')})"
            )

        else:
            seen[key] = card.get(
                "id"
            )

    return errors


# ============================================================
# REPORT
# ============================================================

def build_report(
    original_cards,
    final_cards,
    merged_groups,
    removed_cards,
    semantic_review,
    errors,
):

    lines = []

    lines.append(
        "=" * 78
    )

    lines.append(
        "B1-B2 SAFE DEDUPLICATION REPORT"
    )

    lines.append(
        "=" * 78
    )

    lines.append("")

    lines.append(
        f"Original cards:             "
        f"{len(original_cards)}"
    )

    lines.append(
        f"Safe merged groups:         "
        f"{len(merged_groups)}"
    )

    lines.append(
        f"Duplicate cards removed:    "
        f"{removed_cards}"
    )

    lines.append(
        f"Cards after safe dedup:     "
        f"{len(final_cards)}"
    )

    lines.append(
        f"Semantic review groups:     "
        f"{len(semantic_review)}"
    )

    lines.append(
        f"Validation errors:          "
        f"{len(errors)}"
    )

    lines.append("")

    lines.append(
        "SAFE MERGE RULE"
    )

    lines.append(
        "-" * 78
    )

    lines.append(
        "Cards were merged ONLY when "
        "normalized Swedish AND normalized "
        "English were identical."
    )

    lines.append("")

    lines.append(
        "Same Swedish spelling with different "
        "English translations was NOT merged."
    )

    lines.append("")

    lines.append(
        "Each merged card preserves all original "
        "Rivstart occurrences."
    )

    lines.append("")

    lines.append(
        "MERGED GROUPS"
    )

    lines.append(
        "-" * 78
    )

    for group in merged_groups:

        lines.append("")

        lines.append(
            f"{group['swedish']} -> "
            f"{group['english']}"
        )

        lines.append(
            f"  kept: {group['kept_id']}"
        )

        lines.append(
            "  removed: "
            + ", ".join(
                group["removed_ids"]
            )
        )

        lines.append(
            "  chapters: "
            + ", ".join(
                str(x)
                for x in group[
                    "chapters"
                ]
            )
        )

    lines.append("")

    lines.append(
        "VALIDATION"
    )

    lines.append(
        "-" * 78
    )

    if errors:
        lines.extend(errors)
    else:
        lines.append(
            "OK - no validation errors."
        )

    lines.append("")

    lines.append(
        "=" * 78
    )

    if errors:
        lines.append(
            "RESULT: FAIL"
        )
    else:
        lines.append(
            "RESULT: SAFE DEDUPLICATION OK"
        )

    lines.append(
        "=" * 78
    )

    return "\n".join(lines)


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 78)
    print("B1-B2 SAFE DEDUPLICATION")
    print("=" * 78)
    print()

    cards = load_json(
        INPUT_FILE
    )

    print(
        f"Input cards: {len(cards)}"
    )

    if len(cards) != 6164:
        print()
        print(
            "WARNING: expected 6164 cards "
            f"but found {len(cards)}."
        )
        print()

    print()
    print(
        "Phase 1: safe duplicate merging..."
    )

    (
        deduplicated,
        merged_groups,
        removed_cards,
    ) = safe_deduplicate(cards)

    print(
        f"Merged groups: "
        f"{len(merged_groups)}"
    )

    print(
        f"Removed duplicate cards: "
        f"{removed_cards}"
    )

    print(
        f"Cards remaining: "
        f"{len(deduplicated)}"
    )

    print()
    print(
        "Phase 2: finding semantic "
        "review candidates..."
    )

    semantic_review = (
        build_semantic_review(
            deduplicated
        )
    )

    print(
        f"Semantic review groups: "
        f"{len(semantic_review)}"
    )

    print()
    print(
        "Phase 3: validation..."
    )

    errors = validate(
        deduplicated
    )

    print(
        f"Validation errors: "
        f"{len(errors)}"
    )

    # --------------------------------------------
    # SAVE
    # --------------------------------------------

    save_json(
        OUTPUT_FILE,
        deduplicated,
    )

    save_json(
        REVIEW_FILE,
        semantic_review,
    )

    report = build_report(
        cards,
        deduplicated,
        merged_groups,
        removed_cards,
        semantic_review,
        errors,
    )

    REPORT_FILE.write_text(
        report,
        encoding="utf-8",
    )

    print()
    print("=" * 78)

    if errors:
        print(
            "RESULT: FAIL"
        )
    else:
        print(
            "RESULT: SAFE DEDUPLICATION OK"
        )

    print("=" * 78)

    print()
    print("Created:")
    print(OUTPUT_FILE)
    print(REVIEW_FILE)
    print(REPORT_FILE)
    print()

    if not errors:

        print(
            "Original b1b2_clean.json "
            "was NOT modified."
        )

        print()

        print(
            "Next step: review only the "
            "remaining same-Swedish / "
            "different-English groups."
        )

    print()


if __name__ == "__main__":
    main()