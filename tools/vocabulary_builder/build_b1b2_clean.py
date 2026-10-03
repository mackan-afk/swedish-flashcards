import json
from pathlib import Path
from copy import deepcopy


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"

RAW_FILE = OUTPUT_DIR / "b1b2_raw_v53.json"
REVIEW_FILE = OUTPUT_DIR / "b1b2_manual_review_v53.json"
FIXES_FILE = OUTPUT_DIR / "manual_fixes_v53.json"

CLEAN_FILE = OUTPUT_DIR / "b1b2_clean.json"
REPORT_FILE = OUTPUT_DIR / "b1b2_clean_report.txt"


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


def clean_text(value):
    """
    Remove common PDF extraction artifacts without otherwise
    modifying the vocabulary.
    """
    if value is None:
        return None

    if not isinstance(value, str):
        return value

    value = value.replace("\u00ad", "")
    value = value.replace("\u200b", "")
    value = value.strip()

    return value


def normalize_card(card):
    card = deepcopy(card)

    for key in (
        "swedish",
        "forms",
        "english",
        "level",
        "source",
        "parse_method",
    ):
        if key in card:
            card[key] = clean_text(card[key])

    return card


def review_key(review):
    """
    Stable key describing the physical review row.
    """
    return (
        review.get("source_pdf_page"),
        review.get("column"),
        review.get("chapter"),
        review.get("page"),
        review.get("raw"),
    )


def find_previous_card_index(cards, review):
    """
    Locate the card referred to by PREVIOUS CARD.

    We use several fields instead of just Swedish because the same
    Swedish headword may legitimately occur more than once.
    """

    previous = review.get("previous_card") or {}

    swedish = clean_text(previous.get("swedish"))
    forms = clean_text(previous.get("forms"))
    english = clean_text(previous.get("english"))

    chapter = review.get("chapter")
    page = review.get("page")
    pdf_page = review.get("source_pdf_page")

    candidates = []

    for index, card in enumerate(cards):
        if clean_text(card.get("swedish")) != swedish:
            continue

        score = 0

        if card.get("chapter") == chapter:
            score += 10

        if card.get("page") == page:
            score += 10

        if card.get("source_pdf_page") == pdf_page:
            score += 20

        if forms and clean_text(card.get("forms")) == forms:
            score += 5

        if english and clean_text(card.get("english")) == english:
            score += 5

        candidates.append((score, index))

    if not candidates:
        raise RuntimeError(
            "\nCould not locate PREVIOUS CARD:\n"
            f"  Swedish: {swedish}\n"
            f"  Chapter: {chapter}\n"
            f"  Page: {page}\n"
            f"  PDF page: {pdf_page}"
        )

    candidates.sort(reverse=True)

    best_score = candidates[0][0]
    best = [index for score, index in candidates if score == best_score]

    if len(best) != 1:
        details = [
            {
                "index": index,
                "id": cards[index].get("id"),
                "swedish": cards[index].get("swedish"),
                "chapter": cards[index].get("chapter"),
                "page": cards[index].get("page"),
                "source_pdf_page": cards[index].get("source_pdf_page"),
            }
            for index in best
        ]

        raise RuntimeError(
            "\nAmbiguous PREVIOUS CARD match:\n"
            f"{json.dumps(details, ensure_ascii=False, indent=2)}"
        )

    return best[0]


def next_manual_id(cards):
    """
    Existing parser IDs look like riv_b_0001.

    Added manual cards get their own namespace so we never have
    to renumber parser-generated cards.
    """

    used = {card.get("id") for card in cards}

    number = 1

    while True:
        candidate = f"riv_b_manual_{number:04d}"

        if candidate not in used:
            return candidate

        number += 1


def create_manual_card(fix, review, card_id):
    return {
        "id": card_id,
        "swedish": clean_text(fix["swedish"]),
        "forms": clean_text(fix.get("forms", "")),
        "english": clean_text(fix["english"]),
        "level": "B1-B2",
        "chapter": fix.get("chapter", review.get("chapter")),
        "page": fix.get("page", review.get("page")),
        "source": "rivstart_b1b2",
        "source_pdf_page": review.get("source_pdf_page"),
        "parse_method": "MANUAL_REVIEW",
    }


# ============================================================
# VALIDATION
# ============================================================

def validate_inputs(cards, reviews, fixes):
    errors = []

    if not isinstance(cards, list):
        errors.append("b1b2_raw_v53.json is not a JSON list.")

    if not isinstance(reviews, list):
        errors.append("b1b2_manual_review_v53.json is not a JSON list.")

    if not isinstance(fixes, list):
        errors.append("manual_fixes_v53.json is not a JSON list.")

    if errors:
        raise RuntimeError("\n".join(errors))

    if len(reviews) != 163:
        errors.append(
            f"Expected 163 review records, found {len(reviews)}."
        )

    if len(fixes) != 163:
        errors.append(
            f"Expected 163 manual fixes, found {len(fixes)}."
        )

    review_numbers = [fix.get("review") for fix in fixes]

    expected = list(range(1, 164))

    if sorted(review_numbers) != expected:
        missing = sorted(set(expected) - set(review_numbers))
        duplicates = sorted(
            number
            for number in set(review_numbers)
            if review_numbers.count(number) > 1
        )

        if missing:
            errors.append(
                f"Missing manual review numbers: {missing}"
            )

        if duplicates:
            errors.append(
                f"Duplicate manual review numbers: {duplicates}"
            )

    valid_actions = {
        "UPDATE_PREVIOUS",
        "ADD_CARD",
        "SKIP",
    }

    for fix in fixes:
        number = fix.get("review")
        action = fix.get("action")

        if action not in valid_actions:
            errors.append(
                f"Review #{number}: invalid action '{action}'."
            )

        if action == "ADD_CARD":
            if not clean_text(fix.get("swedish")):
                errors.append(
                    f"Review #{number}: ADD_CARD has no Swedish."
                )

            if not clean_text(fix.get("english")):
                errors.append(
                    f"Review #{number}: ADD_CARD has no English."
                )

    ids = [card.get("id") for card in cards]

    duplicate_ids = sorted(
        card_id
        for card_id in set(ids)
        if ids.count(card_id) > 1
    )

    if duplicate_ids:
        errors.append(
            f"Raw database already contains duplicate IDs: "
            f"{duplicate_ids[:20]}"
        )

    if errors:
        raise RuntimeError(
            "\nINPUT VALIDATION FAILED\n\n"
            + "\n".join(f"- {error}" for error in errors)
        )


# ============================================================
# APPLY MANUAL FIXES
# ============================================================

def apply_fixes(cards, reviews, fixes):
    cards = [normalize_card(card) for card in cards]

    fixes_by_number = {
        fix["review"]: fix
        for fix in fixes
    }

    stats = {
        "updated": 0,
        "added": 0,
        "skipped": 0,
    }

    change_log = []

    manual_counter = 1

    used_ids = {card.get("id") for card in cards}

    for review_number, review in enumerate(reviews, start=1):

        fix = fixes_by_number[review_number]
        action = fix["action"]

        # ----------------------------------------------------
        # UPDATE EXISTING CARD
        # ----------------------------------------------------

        if action == "UPDATE_PREVIOUS":

            index = find_previous_card_index(cards, review)

            before = deepcopy(cards[index])

            if "swedish" in fix:
                cards[index]["swedish"] = clean_text(
                    fix["swedish"]
                )

            if "forms" in fix:
                cards[index]["forms"] = clean_text(
                    fix["forms"]
                )

            if "english" in fix:
                cards[index]["english"] = clean_text(
                    fix["english"]
                )

            cards[index]["parse_method"] = "MANUAL_REVIEW_FIXED"

            after = deepcopy(cards[index])

            stats["updated"] += 1

            change_log.append({
                "review": review_number,
                "action": action,
                "id": cards[index].get("id"),
                "before": before,
                "after": after,
            })

        # ----------------------------------------------------
        # ADD MISSING CARD
        # ----------------------------------------------------

        elif action == "ADD_CARD":

            while True:
                card_id = f"riv_b_manual_{manual_counter:04d}"
                manual_counter += 1

                if card_id not in used_ids:
                    break

            new_card = create_manual_card(
                fix,
                review,
                card_id,
            )

            cards.append(new_card)
            used_ids.add(card_id)

            stats["added"] += 1

            change_log.append({
                "review": review_number,
                "action": action,
                "id": card_id,
                "card": deepcopy(new_card),
            })

        # ----------------------------------------------------
        # NOTHING TO ADD
        # ----------------------------------------------------

        elif action == "SKIP":

            stats["skipped"] += 1

            change_log.append({
                "review": review_number,
                "action": action,
            })

    return cards, stats, change_log


# ============================================================
# FINAL QA
# ============================================================

def validate_output(cards):
    errors = []
    warnings = []

    # --------------------------------------------------------
    # IDs
    # --------------------------------------------------------

    ids = [card.get("id") for card in cards]

    missing_ids = [
        index
        for index, card_id in enumerate(ids)
        if not card_id
    ]

    if missing_ids:
        errors.append(
            f"{len(missing_ids)} cards have no ID."
        )

    duplicate_ids = sorted(
        card_id
        for card_id in set(ids)
        if card_id and ids.count(card_id) > 1
    )

    if duplicate_ids:
        errors.append(
            f"Duplicate IDs found: {duplicate_ids}"
        )

    # --------------------------------------------------------
    # Required fields
    # --------------------------------------------------------

    for index, card in enumerate(cards):

        card_id = card.get("id", f"index_{index}")

        if not clean_text(card.get("swedish")):
            errors.append(
                f"{card_id}: empty Swedish."
            )

        if not clean_text(card.get("english")):
            errors.append(
                f"{card_id}: empty English."
            )

        if card.get("level") != "B1-B2":
            warnings.append(
                f"{card_id}: unexpected level "
                f"{card.get('level')!r}."
            )

        chapter = card.get("chapter")

        if not isinstance(chapter, int) or not 1 <= chapter <= 18:
            errors.append(
                f"{card_id}: invalid chapter {chapter!r}."
            )

    # --------------------------------------------------------
    # Suspicious PDF artifacts
    # --------------------------------------------------------

    suspicious_fragments = [
        "\u00ad",
        "\u200b",
    ]

    for card in cards:

        for field in ("swedish", "forms", "english"):

            value = card.get(field)

            if not isinstance(value, str):
                continue

            for fragment in suspicious_fragments:
                if fragment in value:
                    warnings.append(
                        f"{card.get('id')}: suspicious character "
                        f"in {field}."
                    )

    return errors, warnings


# ============================================================
# REPORT
# ============================================================

def build_report(
    raw_count,
    review_count,
    cards,
    stats,
    change_log,
    errors,
    warnings,
):
    chapter_counts = {}

    for card in cards:
        chapter = card.get("chapter")
        chapter_counts[chapter] = (
            chapter_counts.get(chapter, 0) + 1
        )

    lines = []

    lines.append("=" * 70)
    lines.append("B1-B2 CLEAN DATABASE REPORT")
    lines.append("=" * 70)
    lines.append("")

    lines.append(f"Raw cards:            {raw_count}")
    lines.append(f"Review records:       {review_count}")
    lines.append("")
    lines.append(f"Updated cards:        {stats['updated']}")
    lines.append(f"Added cards:          {stats['added']}")
    lines.append(f"Skipped rows:         {stats['skipped']}")
    lines.append("")
    lines.append(f"Final cards:          {len(cards)}")
    lines.append("")

    lines.append("CARDS PER CHAPTER")
    lines.append("-" * 70)

    for chapter in sorted(chapter_counts):
        lines.append(
            f"Chapter {chapter:>2}: {chapter_counts[chapter]}"
        )

    lines.append("")
    lines.append("QA")
    lines.append("-" * 70)
    lines.append(f"Errors:               {len(errors)}")
    lines.append(f"Warnings:             {len(warnings)}")

    if errors:
        lines.append("")
        lines.append("ERRORS")
        lines.append("-" * 70)

        for error in errors:
            lines.append(error)

    if warnings:
        lines.append("")
        lines.append("WARNINGS")
        lines.append("-" * 70)

        for warning in warnings:
            lines.append(warning)

    lines.append("")
    lines.append("MANUAL CHANGES")
    lines.append("-" * 70)

    for change in change_log:

        review = change["review"]
        action = change["action"]

        lines.append(
            f"Review #{review:03d}: {action}"
        )

        if action == "UPDATE_PREVIOUS":

            before = change["before"]
            after = change["after"]

            lines.append(
                f"  ID: {change['id']}"
            )

            if before.get("swedish") != after.get("swedish"):
                lines.append(
                    f"  Swedish: "
                    f"{before.get('swedish')} -> "
                    f"{after.get('swedish')}"
                )

            if before.get("forms") != after.get("forms"):
                lines.append(
                    f"  Forms: "
                    f"{before.get('forms')} -> "
                    f"{after.get('forms')}"
                )

            if before.get("english") != after.get("english"):
                lines.append(
                    f"  English: "
                    f"{before.get('english')} -> "
                    f"{after.get('english')}"
                )

        elif action == "ADD_CARD":

            card = change["card"]

            lines.append(
                f"  ID: {card['id']}"
            )
            lines.append(
                f"  Swedish: {card['swedish']}"
            )
            lines.append(
                f"  English: {card['english']}"
            )

        lines.append("")

    return "\n".join(lines)


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("B1-B2 CLEAN DATABASE BUILDER")
    print("=" * 70)
    print()

    print("Loading files...")

    raw_cards = load_json(RAW_FILE)
    reviews = load_json(REVIEW_FILE)
    fixes = load_json(FIXES_FILE)

    print(f"Raw cards:      {len(raw_cards)}")
    print(f"Review records: {len(reviews)}")
    print(f"Manual fixes:   {len(fixes)}")
    print()

    print("Validating inputs...")

    validate_inputs(
        raw_cards,
        reviews,
        fixes,
    )

    print("Input validation: OK")
    print()

    print("Applying manual fixes...")

    clean_cards, stats, change_log = apply_fixes(
        raw_cards,
        reviews,
        fixes,
    )

    print(
        f"Updated: {stats['updated']} | "
        f"Added: {stats['added']} | "
        f"Skipped: {stats['skipped']}"
    )

    print()
    print("Running final QA...")

    errors, warnings = validate_output(clean_cards)

    print(f"Errors:   {len(errors)}")
    print(f"Warnings: {len(warnings)}")
    print()

    report = build_report(
        raw_count=len(raw_cards),
        review_count=len(reviews),
        cards=clean_cards,
        stats=stats,
        change_log=change_log,
        errors=errors,
        warnings=warnings,
    )

    with REPORT_FILE.open(
        "w",
        encoding="utf-8",
    ) as f:
        f.write(report)

    if errors:

        print("=" * 70)
        print("BUILD FAILED")
        print("=" * 70)
        print()

        for error in errors:
            print("ERROR:", error)

        print()
        print(
            "Report saved to:"
        )
        print(REPORT_FILE)

        print()
        print(
            "b1b2_clean.json was NOT written "
            "because QA found errors."
        )

        return

    # Sort primarily by chapter/page, but keep the existing IDs
    # unchanged. Sorting does NOT affect SRS IDs.
    clean_cards.sort(
        key=lambda card: (
            card.get("chapter") or 999,
            card.get("page")
            if card.get("page") is not None
            else -1,
            card.get("source_pdf_page")
            if card.get("source_pdf_page") is not None
            else -1,
            card.get("id") or "",
        )
    )

    save_json(
        CLEAN_FILE,
        clean_cards,
    )

    print("=" * 70)
    print("BUILD SUCCESSFUL")
    print("=" * 70)
    print()

    print(f"Final cards: {len(clean_cards)}")
    print()

    print("Created:")
    print(CLEAN_FILE)
    print()

    print("QA report:")
    print(REPORT_FILE)
    print()

    if warnings:
        print(
            f"NOTE: build contains {len(warnings)} "
            "QA warning(s)."
        )
        print(
            "They are listed in b1b2_clean_report.txt."
        )
    else:
        print("QA completed with no warnings.")

    print()


if __name__ == "__main__":
    main()