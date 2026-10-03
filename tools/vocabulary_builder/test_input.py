from pathlib import Path
import json
import fitz  # PyMuPDF


BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "input"

WORDS_FILE = INPUT_DIR / "words.json"
B_FILE = INPUT_DIR / "B1 B2.pdf"
C_FILE = INPUT_DIR / "C1 C2.pdf"


def check_json():
    print("\n=== A1-A2: words.json ===")

    with open(WORDS_FILE, "r", encoding="utf-8") as f:
        words = json.load(f)

    print(f"Number of cards: {len(words)}")

    if words:
        print("\nFirst card:")
        print(json.dumps(words[0], ensure_ascii=False, indent=2))


def check_pdf(path, name):
    print(f"\n=== {name} ===")

    document = fitz.open(path)

    print(f"Number of pages: {len(document)}")

    first_page_text = document[0].get_text()

    print("\nFirst 500 characters:")
    print("-" * 60)
    print(first_page_text[:500])
    print("-" * 60)

    document.close()


def main():
    print("=" * 60)
    print("SVENSKAKORT VOCABULARY BUILDER - INPUT TEST")
    print("=" * 60)

    files = [
        WORDS_FILE,
        B_FILE,
        C_FILE,
    ]

    print("\nChecking files:")

    for file in files:
        status = "OK" if file.exists() else "MISSING"
        print(f"{status:8} {file.name}")

    if not all(file.exists() for file in files):
        print("\nERROR: One or more input files are missing.")
        return

    check_json()
    check_pdf(B_FILE, "Rivstart B1-B2")
    check_pdf(C_FILE, "Rivstart C")

    print("\n" + "=" * 60)
    print("ALL INPUT FILES READ SUCCESSFULLY")
    print("=" * 60)


if __name__ == "__main__":
    main()