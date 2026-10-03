import json
import re
from pathlib import Path
from collections import Counter, defaultdict


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"

INPUT_FILE = OUTPUT_DIR / "b1b2_deduplicated.json"

OUTPUT_FILE = OUTPUT_DIR / "b1b2_final.json"
REPORT_FILE = OUTPUT_DIR / "b1b2_final_report.txt"
MERGE_MAP_FILE = OUTPUT_DIR / "b1b2_final_merge_map.json"


# ============================================================
# IMPORTANT
# ============================================================
#
# This is the FINAL B1-B2 semantic cleanup.
#
# Input:
#   b1b2_deduplicated.json
#   expected: 5955 cards
#
# Rules:
#
# 1. Obvious translation variants of the SAME lexical item
#    are merged.
#
# 2. Homonyms / different parts of speech / clearly different
#    meanings remain separate.
#
# 3. Original canonical IDs are preserved.
#
# 4. All Rivstart chapter/page occurrences are preserved.
#
# 5. A few clear parser/typo artifacts are corrected.
#
# ============================================================


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


def norm(value):
    if not isinstance(value, str):
        return ""

    value = value.strip()
    value = re.sub(r"\s+", " ", value)

    return value.casefold()


def card_sort_key(card):
    card_id = card.get("id", "")

    m = re.fullmatch(r"riv_b_(\d+)", card_id)

    if m:
        return (0, int(m.group(1)), card_id)

    m = re.fullmatch(
        r"riv_b_manual_(\d+)",
        card_id,
    )

    if m:
        return (1, int(m.group(1)), card_id)

    return (2, 999999, card_id)


def choose_best_forms(cards):
    values = []

    for card in cards:
        forms = card.get("forms", "")

        if not isinstance(forms, str):
            continue

        forms = forms.strip()

        if forms:
            values.append(forms)

    if not values:
        return ""

    def score(value):
        parts = [
            x.strip()
            for x in value.split(",")
            if x.strip()
        ]

        return (
            len(parts),
            len(value),
        )

    return max(values, key=score)


def occurrence_from_card(card):
    return {
        "chapter": card.get("chapter"),
        "page": card.get("page"),
        "source_pdf_page":
            card.get("source_pdf_page"),
        "original_id": card.get("id"),
    }


def collect_occurrences(cards):
    result = []
    seen = set()

    for card in cards:

        existing = card.get("occurrences")

        if isinstance(existing, list):
            source = existing
        else:
            source = [
                occurrence_from_card(card)
            ]

        for occurrence in source:

            if not isinstance(
                occurrence, dict
            ):
                continue

            key = (
                occurrence.get("chapter"),
                occurrence.get("page"),
                occurrence.get(
                    "source_pdf_page"
                ),
                occurrence.get(
                    "original_id"
                ),
            )

            if key in seen:
                continue

            seen.add(key)
            result.append(
                dict(occurrence)
            )

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
                x.get("source_pdf_page"),
                int,
            )
            else 999999,
            x.get("original_id") or "",
        )
    )

    return result


# ============================================================
# CLEAR CORRECTIONS
# ============================================================
#
# These are corrections of obvious extraction/typing artifacts,
# not broad rewriting of the Rivstart source.
#
# Format:
#
# ID: {
#     "swedish": "...",   # optional
#     "english": "...",   # optional
#     "forms": "...",     # optional
# }
#
# ============================================================

CORRECTIONS = {

    # obvious English typo
    "riv_b_2952": {
        "english": "enormous",
    },

    # obvious morphology typo
    "riv_b_3313": {
        "forms": "känt, kända",
    },

    # obvious English typo
    "riv_b_0797": {
        "english": "spontaneous",
    },

    # Parser split:
    # känna till = be familiar with
    "riv_b_2637": {
        "swedish": "känna till",
        "english": "be familiar with",
        "forms": "känner, kände, känt",
    },

    # Parser split:
    # räkna ut = work out / calculate
    "riv_b_0199": {
        "swedish": "räkna ut",
        "english": "work out, calculate",
        "forms": "-r, -de, -t",
    },

    # Parser split:
    # tro på = believe in
    "riv_b_3459": {
        "swedish": "tro på",
        "english": "believe in",
        "forms": "tror, trodde, trott",
    },

    # morphology accidentally ended up in English
    "riv_b_3041": {
        "forms": "-en, -er, -erna",
        "english": "time period",
    },

    # obvious spelling correction in English
    "riv_b_1137": {
        "english": "doctor, general practitioner",
    },
}


# ============================================================
# KEEP SEPARATE
# ============================================================
#
# Same written Swedish headword, but genuinely different
# meanings / lexical entries.
#
# These MUST NOT be merged.
#
# ============================================================

KEEP_SEPARATE = {

    # store / business deal
    "affär",

    # other / second
    "andra",

    # addicted / dependent
    "beroende",

    # wrong / fault
    "fel",

    # wife / Mrs.
    "fru",

    # ask / question
    "fråga",

    # verb fill / noun drunkenness
    "fylla",

    # noun food / verb give birth
    "föda",

    # married / poison
    "gift",

    # time / walking path
    "gång",

    # greet / health
    "hälsa",

    # different meanings:
    # "Do you follow?" / "Will you join us?"
    "hänger du med?",

    # at most / highest/tallest
    "högst",

    # club / nightclub
    "klubb",

    # feel / känna till was corrected above,
    # therefore they no longer share same Swedish key

    # drive / cover distance
    "köra",

    # free from work / relaxed
    "ledig",

    # lie / have sex
    "ligga",

    # light / easy
    "lätt",

    # pronoun "one" / noun "man"
    "man",

    # mathematics / female pet owner
    "matte",

    # least/smallest / youngest
    "minst",

    # exercise / parliamentary motion
    "motion",

    # workout/pass / passport
    "pass",

    # introduce / present
    "presentera",

    # noun trip / verb raise
    "resa",

    # right / dish
    "rätt",

    # verb move / noun mess
    "röra",

    # vote / voice
    "röst",

    # syrup / juice/sap
    "saft",

    # noun salt / adjective salty
    "salt",

    # page / side
    "sida",

    # tax / treasure
    "skatt",

    # verb sweep / noun garbage
    "sopa",

    # pole / staff
    "stav",

    # delete / iron
    "stryka",

    # sin / pity
    "synd",

    # to / also-another
    "till",

    # metric ton / tone
    "ton",

    # turn / luck
    "tur",

    # choice / election
    "val",

    # vara = be / goods / last
    "vara",

    # show / song
    "visa",

    # well / surely
    "väl",

    # adjective deserted / noun fate
    "öde",
    
     # time / time period
    "tid",

    # flirt with / encounter
    "stöta på",

    # stop / put-place
    "stoppa",
}


# ============================================================
# SPECIAL SEMANTIC MERGES
# ============================================================
#
# For these groups we explicitly choose the English text that
# should appear on the final card.
#
# Everything here represents the SAME lexical item.
#
# ============================================================

MERGE_TRANSLATIONS = {

    "anse":
        "consider, deem, believe",

    "arbetsfri":
        "free from work, off work",

    "ask":
        "ash tree",

    "barnbidrag":
        "child benefit",

    "bit":
        "bit, piece, slice",

    "björk":
        "birch, birch tree",

    "bra":
        "good, well",

    "debutera":
        "debut",

    "ena":
        "one (of several)",

    "enorm":
        "enormous",

    "falla":
        "fall",

    "falsk":
        "false, out of tune",

    "fast":
        "firm, determined",

    "fräck":
        "cheeky, brash, brazen",

    "förändras":
        "change",

    "gemenskap":
        "community, fellowship, connection",

    "gifta sig":
        "get married",

    "gjord av":
        "made of, made out of",

    "gå över till":
        "change to, switch to",

    "hemsk":
        "horrible, scary",

    "himla":
        "really, very",

    "hindra":
        "hinder, stop",

    "hjälpas åt":
        "help each other out",

    "hoppa över":
        "skip, skip over",

    "hälsa på":
        "visit, pay a visit",

    "hård":
        "hard, tough",

    "höra hemma":
        "belong",

    "i första hand":
        "primarily, in the first place",

    "i samband med":
        "in connection with",

    "i slutet av":
        "at the end of",

    "inför":
        "before, in front of",

    "inte alls":
        "not at all",

    "kamma sig":
        "comb one's hair",

    "klappa":
        "pet, caress",

    "komma på":
        "think of, realize",

    "kvar":
        "remaining, left",

    "känd":
        "famous, well known",

    "lita på":
        "trust",

    "locka":
        "attract, lure",

    "lukt":
        "smell, scent",

    "lägga sig":
        "lie down, go to bed",

    "läkare":
        "doctor",

    "låta":
        "sound, make noise",

    "nordbo":
        "person from the Nordic countries",

    "område":
        "area, region, field",

    "pryl":
        "object, thing",

    "på så sätt":
        "in that way",

    "pålitlig":
        "reliable, dependable",

    "rest":
        "remainder, leftover",

    "rubrik":
        "heading, headline",

    "saga":
        "story, fairy tale, saga",

    "sammansatt":
        "compound, put together",

    "skadad":
        "injured, damaged",

    "skicklig":
        "skilled, skillful",

    "slå":
        "hit, beat",

    "snack":
        "talk, chat",

    "spela roll":
        "play a role, matter",

    "spontan":
        "spontaneous",

    "sprida sig":
        "spread",

    "starta":
        "start",

    "statskupp":
        "coup, coup d'état",

    "steka":
        "fry",

    "sten":
        "stone, rock",

    "stor":
        "big, large",

    "stressad":
        "stressed, stressed out",

    "städa":
        "clean, clean up",

    "störst":
        "biggest, largest",

    "svettas":
        "sweat",

    "ta kontakt med":
        "contact, get in touch with",

    "träningskläder":
        "workout clothes, exercise clothes",

    "undra":
        "wonder",

    "uppmaning":
        "appeal, urging",

    "vandra":
        "hike",

    "vara på väg":
        "be on the way",

    "varje":
        "each, every",

    "vid":
        "by, next to",

    "väcka intresse":
        "generate interest",

    "väga":
        "weigh",

    "väldig":
        "enormous, very large",

    "våttorka":
        "wet-mop",

    "återgå":
        "return, go back",

    "över":
        "over, more than",
}


# ============================================================
# SPECIAL CASE: STÖTA PÅ
# ============================================================
#
# Rivstart contains genuinely different senses:
#
#   stöta på = encounter / run into
#   stöta på = flirt with / hit on
#
# We want TWO cards, not three.
#
# The manual card and encounter card are merged.
#
# ============================================================

SPECIAL_MERGES = [

    {
        "ids": [
            "riv_b_3522",
            "riv_b_manual_0008",
        ],
        "english":
            "encounter, run into, come across",
    },

]


# ============================================================
# APPLY CORRECTIONS
# ============================================================

def apply_corrections(cards):

    by_id = {
        card["id"]: card
        for card in cards
    }

    applied = []

    for card_id, changes in CORRECTIONS.items():

        card = by_id.get(card_id)

        if card is None:
            raise RuntimeError(
                f"Correction target missing: "
                f"{card_id}"
            )

        before = {
            key: card.get(key)
            for key in changes
        }

        for key, value in changes.items():
            card[key] = value

        applied.append({
            "id": card_id,
            "before": before,
            "after": changes,
        })

    return applied


# ============================================================
# MERGE CARDS
# ============================================================

def merge_card_group(
    cards,
    final_english=None,
):

    ordered = sorted(
        cards,
        key=card_sort_key,
    )

    keeper = dict(ordered[0])

    if final_english:
        keeper["english"] = final_english

    keeper["forms"] = choose_best_forms(
        ordered
    )

    occurrences = collect_occurrences(
        ordered
    )

    keeper["occurrences"] = occurrences

    keeper["chapters"] = sorted({
        x["chapter"]
        for x in occurrences
        if isinstance(
            x.get("chapter"), int
        )
    })

    previous_removed = []

    for card in ordered:

        old = card.get(
            "deduplicated_from"
        )

        if isinstance(old, list):
            previous_removed.extend(old)

    removed_now = [
        card["id"]
        for card in ordered[1:]
    ]

    all_removed = []

    for card_id in (
        previous_removed
        + removed_now
    ):
        if (
            card_id != keeper["id"]
            and card_id
            not in all_removed
        ):
            all_removed.append(card_id)

    if all_removed:
        keeper[
            "deduplicated_from"
        ] = all_removed

    return keeper, removed_now


# ============================================================
# APPLY EXPLICIT SPECIAL MERGES
# ============================================================

def apply_special_merges(cards):

    by_id = {
        card["id"]: card
        for card in cards
    }

    remove_ids = set()
    replacements = {}
    report = []

    for rule in SPECIAL_MERGES:

        selected = []

        for card_id in rule["ids"]:

            card = by_id.get(card_id)

            if card is None:
                raise RuntimeError(
                    "Special merge target "
                    f"missing: {card_id}"
                )

            selected.append(card)

        merged, removed = (
            merge_card_group(
                selected,
                rule["english"],
            )
        )

        keeper_id = merged["id"]

        replacements[
            keeper_id
        ] = merged

        remove_ids.update(removed)

        report.append({
            "kept_id": keeper_id,
            "removed_ids": removed,
            "swedish":
                merged["swedish"],
            "english":
                merged["english"],
        })

    output = []

    for card in cards:

        card_id = card["id"]

        if card_id in remove_ids:
            continue

        if card_id in replacements:
            output.append(
                replacements[card_id]
            )
        else:
            output.append(card)

    return output, report


# ============================================================
# SEMANTIC FINALIZATION
# ============================================================

def semantic_finalize(cards):

    groups = defaultdict(list)

    for card in cards:
        groups[
            norm(card.get("swedish"))
        ].append(card)

    output = []

    merged_report = []
    kept_separate_report = []

    unresolved = []

    for key, group in groups.items():

        if len(group) == 1:
            output.append(group[0])
            continue

        # --------------------------------------------
        # Explicitly keep different meanings
        # --------------------------------------------

        if key in KEEP_SEPARATE:

            output.extend(
                sorted(
                    group,
                    key=card_sort_key,
                )
            )

            kept_separate_report.append({
                "swedish":
                    group[0]["swedish"],
                "ids": [
                    x["id"]
                    for x in group
                ],
                "english": [
                    x["english"]
                    for x in group
                ],
            })

            continue

        # --------------------------------------------
        # Explicit same-meaning merge
        # --------------------------------------------

        if key in MERGE_TRANSLATIONS:

            merged, removed = (
                merge_card_group(
                    group,
                    MERGE_TRANSLATIONS[key],
                )
            )

            output.append(merged)

            merged_report.append({
                "swedish":
                    merged["swedish"],
                "kept_id":
                    merged["id"],
                "removed_ids":
                    removed,
                "english":
                    merged["english"],
            })

            continue

        # --------------------------------------------
        # Anything left is NOT silently modified.
        # --------------------------------------------

        output.extend(
            sorted(
                group,
                key=card_sort_key,
            )
        )

        unresolved.append({
            "swedish":
                group[0]["swedish"],
            "ids": [
                x["id"]
                for x in group
            ],
            "english": [
                x["english"]
                for x in group
            ],
        })

    output.sort(
        key=card_sort_key
    )

    return (
        output,
        merged_report,
        kept_separate_report,
        unresolved,
    )


# ============================================================
# FINAL NORMALIZATION
# ============================================================

def normalize_final_cards(cards):

    for card in cards:

        # Ensure chapters exists.
        if not isinstance(
            card.get("chapters"), list
        ):

            chapter = card.get(
                "chapter"
            )

            if isinstance(chapter, int):
                card["chapters"] = [
                    chapter
                ]
            else:
                card["chapters"] = []

        # Ensure occurrences exists.
        if not isinstance(
            card.get("occurrences"),
            list,
        ):
            card["occurrences"] = [
                occurrence_from_card(
                    card
                )
            ]

        # Keep chapter for compatibility.
        #
        # For merged cards this remains the
        # canonical/earliest Rivstart occurrence.
        #
        # Future Flutter code should use
        # "chapters" for By Kapitel.

        card["swedish"] = (
            card.get(
                "swedish", ""
            ).strip()
        )

        card["english"] = (
            card.get(
                "english", ""
            ).strip()
        )

        forms = card.get(
            "forms", ""
        )

        if isinstance(forms, str):
            card["forms"] = (
                forms.strip()
            )


# ============================================================
# VALIDATION
# ============================================================

def validate(cards):

    errors = []
    warnings = []

    ids = [
        card.get("id")
        for card in cards
    ]

    counts = Counter(ids)

    duplicate_ids = [
        card_id
        for card_id, count
        in counts.items()
        if count > 1
    ]

    if duplicate_ids:
        errors.append(
            "Duplicate IDs: "
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
                f"{card_id}: empty Swedish"
            )

        if (
            not isinstance(
                english, str
            )
            or not english.strip()
        ):
            errors.append(
                f"{card_id}: empty English"
            )

        if card.get(
            "level"
        ) not in (
            "B1-B2",
            "B1–B2",
            None,
        ):
            warnings.append(
                f"{card_id}: unexpected "
                f"level={card.get('level')!r}"
            )

        chapters = card.get(
            "chapters"
        )

        if not isinstance(
            chapters, list
        ):
            errors.append(
                f"{card_id}: chapters "
                "is not a list"
            )

        occurrences = card.get(
            "occurrences"
        )

        if not isinstance(
            occurrences, list
        ):
            errors.append(
                f"{card_id}: occurrences "
                "is not a list"
            )

    # --------------------------------------------
    # Check exact SW + EN duplicates again
    # --------------------------------------------

    pair_groups = defaultdict(list)

    for card in cards:

        pair = (
            norm(
                card.get("swedish")
            ),
            norm(
                card.get("english")
            ),
        )

        pair_groups[pair].append(
            card["id"]
        )

    surviving_exact = [
        (
            pair,
            card_ids,
        )
        for pair, card_ids
        in pair_groups.items()
        if len(card_ids) > 1
    ]

    if surviving_exact:

        for pair, card_ids in (
            surviving_exact[:20]
        ):
            errors.append(
                "Exact semantic duplicate "
                f"survived: {pair} -> "
                f"{card_ids}"
            )

    # --------------------------------------------
    # Known typo regression checks
    # --------------------------------------------

    bad_fragments = [
        "enrmous",
        "käntt",
        "spontanteous",
    ]

    for card in cards:

        blob = (
            f"{card.get('swedish', '')} "
            f"{card.get('english', '')} "
            f"{card.get('forms', '')}"
        ).casefold()

        for fragment in bad_fragments:

            if fragment in blob:
                errors.append(
                    f"{card['id']}: "
                    f"bad fragment survived: "
                    f"{fragment}"
                )

    return errors, warnings


# ============================================================
# REPORT
# ============================================================

def make_report(
    input_count,
    final_cards,
    corrections,
    special_merges,
    semantic_merges,
    kept_separate,
    unresolved,
    errors,
    warnings,
):

    lines = []

    lines.append("=" * 78)
    lines.append(
        "B1-B2 FINAL DATABASE REPORT"
    )
    lines.append("=" * 78)
    lines.append("")

    lines.append(
        f"Input cards:                 "
        f"{input_count}"
    )

    lines.append(
        f"Corrections applied:         "
        f"{len(corrections)}"
    )

    lines.append(
        f"Special merge groups:        "
        f"{len(special_merges)}"
    )

    lines.append(
        f"Semantic merge groups:       "
        f"{len(semantic_merges)}"
    )

    lines.append(
        f"Different-meaning groups:    "
        f"{len(kept_separate)}"
    )

    lines.append(
        f"Unresolved groups:           "
        f"{len(unresolved)}"
    )

    lines.append(
        f"Final cards:                 "
        f"{len(final_cards)}"
    )

    lines.append(
        f"Validation errors:           "
        f"{len(errors)}"
    )

    lines.append(
        f"Validation warnings:         "
        f"{len(warnings)}"
    )

    lines.append("")

    lines.append(
        "SEMANTIC MERGES"
    )
    lines.append("-" * 78)

    for item in semantic_merges:

        lines.append(
            f"{item['swedish']} -> "
            f"{item['english']}"
        )

        lines.append(
            f"  kept: {item['kept_id']}"
        )

        lines.append(
            "  removed: "
            + ", ".join(
                item["removed_ids"]
            )
        )

    lines.append("")
    lines.append(
        "KEPT AS DIFFERENT MEANINGS"
    )
    lines.append("-" * 78)

    for item in kept_separate:

        lines.append(
            item["swedish"]
        )

        for card_id, english in zip(
            item["ids"],
            item["english"],
        ):
            lines.append(
                f"  {card_id}: {english}"
            )

    lines.append("")
    lines.append(
        "UNRESOLVED"
    )
    lines.append("-" * 78)

    if unresolved:

        for item in unresolved:

            lines.append(
                item["swedish"]
            )

            for card_id, english in zip(
                item["ids"],
                item["english"],
            ):
                lines.append(
                    f"  {card_id}: {english}"
                )

    else:
        lines.append(
            "None."
        )

    lines.append("")
    lines.append(
        "VALIDATION"
    )
    lines.append("-" * 78)

    if errors:
        for error in errors:
            lines.append(
                "ERROR: " + error
            )
    else:
        lines.append(
            "No validation errors."
        )

    if warnings:
        lines.append("")

        for warning in warnings:
            lines.append(
                "WARNING: " + warning
            )

    lines.append("")
    lines.append("=" * 78)

    if errors or unresolved:
        lines.append(
            "RESULT: REVIEW REQUIRED"
        )
    else:
        lines.append(
            "RESULT: B1-B2 FINAL DATABASE OK"
        )

    lines.append("=" * 78)

    return "\n".join(lines)


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 78)
    print("B1-B2 FINALIZER")
    print("=" * 78)
    print()

    cards = load_json(
        INPUT_FILE
    )

    input_count = len(cards)

    print(
        f"Input cards: {input_count}"
    )

    if input_count != 5955:

        print()
        print(
            "WARNING:"
        )

        print(
            "Expected 5955 cards from "
            "b1b2_deduplicated.json, "
            f"but found {input_count}."
        )

        print()

    # Make independent mutable copies
    cards = [
        dict(card)
        for card in cards
    ]

    # --------------------------------------------
    # 1. Corrections
    # --------------------------------------------

    print(
        "1/6 Applying corrections..."
    )

    corrections = (
        apply_corrections(cards)
    )

    print(
        f"    Applied: "
        f"{len(corrections)}"
    )

    # --------------------------------------------
    # 2. Special merges
    # --------------------------------------------

    print(
        "2/6 Applying special merges..."
    )

    cards, special_merges = (
        apply_special_merges(cards)
    )

    print(
        f"    Groups: "
        f"{len(special_merges)}"
    )

    # --------------------------------------------
    # 3. Semantic finalization
    # --------------------------------------------

    print(
        "3/6 Resolving semantic "
        "duplicates..."
    )

    (
        cards,
        semantic_merges,
        kept_separate,
        unresolved,
    ) = semantic_finalize(cards)

    print(
        f"    Merged groups: "
        f"{len(semantic_merges)}"
    )

    print(
        f"    Different meanings kept: "
        f"{len(kept_separate)}"
    )

    print(
        f"    Unresolved: "
        f"{len(unresolved)}"
    )

    # --------------------------------------------
    # 4. Normalize schema
    # --------------------------------------------

    print(
        "4/6 Normalizing final schema..."
    )

    normalize_final_cards(cards)

    # --------------------------------------------
    # 5. Validation
    # --------------------------------------------

    print(
        "5/6 Running final validation..."
    )

    errors, warnings = validate(
        cards
    )

    print(
        f"    Errors: "
        f"{len(errors)}"
    )

    print(
        f"    Warnings: "
        f"{len(warnings)}"
    )

    # --------------------------------------------
    # 6. Save
    # --------------------------------------------

    print(
        "6/6 Writing output..."
    )

    save_json(
        OUTPUT_FILE,
        cards,
    )

    merge_map = {
        "special_merges":
            special_merges,
        "semantic_merges":
            semantic_merges,
        "kept_separate":
            kept_separate,
        "unresolved":
            unresolved,
        "corrections":
            corrections,
    }

    save_json(
        MERGE_MAP_FILE,
        merge_map,
    )

    report = make_report(
        input_count=input_count,
        final_cards=cards,
        corrections=corrections,
        special_merges=special_merges,
        semantic_merges=semantic_merges,
        kept_separate=kept_separate,
        unresolved=unresolved,
        errors=errors,
        warnings=warnings,
    )

    REPORT_FILE.write_text(
        report,
        encoding="utf-8",
    )

    # --------------------------------------------
    # RESULT
    # --------------------------------------------

    print()
    print("=" * 78)

    if errors:
        print(
            "RESULT: VALIDATION FAILED"
        )

    elif unresolved:
        print(
            "RESULT: REVIEW REQUIRED"
        )

    else:
        print(
            "RESULT: B1-B2 FINAL DATABASE OK"
        )

    print("=" * 78)

    print()

    print(
        f"Final cards: "
        f"{len(cards)}"
    )

    print(
        f"Unresolved semantic groups: "
        f"{len(unresolved)}"
    )

    print(
        f"Validation errors: "
        f"{len(errors)}"
    )

    print()

    print("Created:")
    print(OUTPUT_FILE)
    print(REPORT_FILE)
    print(MERGE_MAP_FILE)
    print()

    if unresolved:

        print(
            "IMPORTANT:"
        )

        print(
            "Some semantic groups were not "
            "covered by the explicit rules."
        )

        print(
            "Do NOT use b1b2_final.json in "
            "production yet."
        )

        print(
            "Send the UNRESOLVED section "
            "from b1b2_final_report.txt."
        )

    elif errors:

        print(
            "IMPORTANT:"
        )

        print(
            "Validation failed. Do NOT use "
            "b1b2_final.json in production."
        )

    else:

        print(
            "B1-B2 database is ready for "
            "application integration."
        )

        print()

        print(
            "Original source files were "
            "not modified."
        )

    print()


if __name__ == "__main__":
    main()