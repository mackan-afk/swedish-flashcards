import json
import re
import unicodedata
from pathlib import Path


WORDS_FILE = Path("words.json")
LEXICON_FILE = Path("lexicon-sv") / "lexicon.txt"


# ============================================================
# NORMALIZATION
# ============================================================

def normalize(text):
    text = unicodedata.normalize("NFC", text)
    text = text.strip()

    # Remove punctuation only from beginning/end.
    text = re.sub(
        r'^[\s.,!?;:"“”„\'()\[\]{}]+|[\s.,!?;:"“”„\'()\[\]{}]+$',
        '',
        text,
    )

    return text.lower().strip()


def word_count(text):
    return len(text.split())


# ============================================================
# LOAD WORDS.JSON
# ============================================================

print("=" * 80)
print("NST / OPENSLR PRONUNCIATION TEST")
print("=" * 80)

print("\nLoading words.json...")

with WORDS_FILE.open("r", encoding="utf-8") as f:
    words = json.load(f)

print(f"Flashcards loaded: {len(words)}")


# ============================================================
# BUILD LIST OF ELIGIBLE WORDS
# ============================================================

eligible = []
skipped = []

for item in words:

    swedish = item.get("swedish", "").strip()
    normalized = normalize(swedish)

    count = word_count(normalized)

    if count <= 2 and normalized:
        eligible.append(
            {
                "original": swedish,
                "normalized": normalized,
                "word_count": count,
            }
        )
    else:
        skipped.append(swedish)


print(f"Eligible (1-2 words): {len(eligible)}")
print(f"Skipped (3+ words):  {len(skipped)}")


# ============================================================
# LOAD NST LEXICON
# ============================================================

print("\nLoading NST/OpenSLR lexicon...")

lexicon = {}


# Try UTF-8 first.
# If the file contains occasional problematic bytes,
# replacement prevents the test from crashing.
with LEXICON_FILE.open(
    "r",
    encoding="utf-8",
    errors="replace",
) as f:

    for line in f:

        line = line.strip()

        if not line:
            continue

        parts = line.split(maxsplit=1)

        if len(parts) != 2:
            continue

        word, pronunciation = parts

        key = normalize(word)

        if not key:
            continue

        lexicon.setdefault(key, [])

        if pronunciation not in lexicon[key]:
            lexicon[key].append(pronunciation)


print(f"Unique NST entries loaded: {len(lexicon)}")


# ============================================================
# MATCH WORDS
# ============================================================

direct_matches = []
composed_matches = []
missing = []


for item in eligible:

    original = item["original"]
    normalized = item["normalized"]
    count = item["word_count"]

    # --------------------------------------------------------
    # DIRECT MATCH
    # --------------------------------------------------------

    if normalized in lexicon:

        direct_matches.append(
            {
                "word": original,
                "normalized": normalized,
                "pronunciations": lexicon[normalized],
            }
        )

        continue

    # --------------------------------------------------------
    # TWO-WORD COMPONENT MATCH
    # --------------------------------------------------------

    if count == 2:

        components = normalized.split()

        if all(component in lexicon for component in components):

            composed_matches.append(
                {
                    "word": original,
                    "normalized": normalized,
                    "components": [
                        {
                            "word": component,
                            "pronunciations": lexicon[component],
                        }
                        for component in components
                    ],
                }
            )

            continue

    # --------------------------------------------------------
    # MISSING
    # --------------------------------------------------------

    missing.append(
        {
            "word": original,
            "normalized": normalized,
            "word_count": count,
        }
    )


# ============================================================
# STATISTICS
# ============================================================

matched_total = len(direct_matches) + len(composed_matches)

coverage = (
    matched_total / len(eligible) * 100
    if eligible
    else 0
)


one_word_total = sum(
    1 for item in eligible
    if item["word_count"] == 1
)

two_word_total = sum(
    1 for item in eligible
    if item["word_count"] == 2
)


one_word_matched = sum(
    1 for item in direct_matches
    if word_count(item["normalized"]) == 1
)


two_word_direct = sum(
    1 for item in direct_matches
    if word_count(item["normalized"]) == 2
)


two_word_matched = (
    two_word_direct
    + len(composed_matches)
)


# ============================================================
# PRINT RESULTS
# ============================================================

print()
print("=" * 80)
print("RESULTS")
print("=" * 80)

print(f"Total flashcards:        {len(words)}")
print(f"Eligible 1-2 words:      {len(eligible)}")
print(f"Skipped 3+ words:        {len(skipped)}")
print()

print(f"Direct matches:          {len(direct_matches)}")
print(f"Composed 2-word matches: {len(composed_matches)}")
print(f"Missing:                 {len(missing)}")
print()

print(f"One-word total:          {one_word_total}")
print(f"One-word matched:        {one_word_matched}")
print(f"One-word missing:        {one_word_total - one_word_matched}")
print()

print(f"Two-word total:          {two_word_total}")
print(f"Two-word matched:        {two_word_matched}")
print(f"Two-word missing:        {two_word_total - two_word_matched}")
print()

print(f"TOTAL COVERAGE:          {coverage:.2f}%")


# ============================================================
# TEST IMPORTANT WORDS
# ============================================================

TEST_WORDS = [
    "elev",
    "lärare",
    "kapitel",
    "lampa",
    "öva",
    "väder",
    "glömma",
    "foto",
    "verb",
    "möbel",
    "skriv",
    "dator",
    "kaffe",
    "svenska",
    "kunna",
]


print()
print("=" * 80)
print("IMPORTANT WORD TEST")
print("=" * 80)


for word in TEST_WORDS:

    key = normalize(word)

    print()
    print(f"{word}:")

    if key in lexicon:

        for pronunciation in lexicon[key]:
            print(f"  {pronunciation}")

    else:
        print("  NOT FOUND")


# ============================================================
# SHOW FIRST 50 MISSING
# ============================================================

print()
print("=" * 80)
print("FIRST 50 MISSING")
print("=" * 80)

for item in missing[:50]:
    print(item["word"])


# ============================================================
# SAVE FULL REPORT
# ============================================================

report = {
    "statistics": {
        "total_flashcards": len(words),
        "eligible": len(eligible),
        "skipped": len(skipped),
        "direct_matches": len(direct_matches),
        "composed_two_word_matches": len(composed_matches),
        "missing": len(missing),
        "one_word_total": one_word_total,
        "one_word_matched": one_word_matched,
        "one_word_missing": one_word_total - one_word_matched,
        "two_word_total": two_word_total,
        "two_word_matched": two_word_matched,
        "two_word_missing": two_word_total - two_word_matched,
        "coverage_percent": round(coverage, 2),
    },

    "direct_matches": direct_matches,
    "composed_matches": composed_matches,
    "missing": missing,
}


OUTPUT_FILE = Path("nst_test_results.json")

with OUTPUT_FILE.open(
    "w",
    encoding="utf-8",
) as f:

    json.dump(
        report,
        f,
        ensure_ascii=False,
        indent=2,
    )


print()
print("=" * 80)
print(f"Full report saved to: {OUTPUT_FILE}")
print("=" * 80)