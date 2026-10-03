from pathlib import Path
import pymupdf


BASE_DIR = Path(__file__).resolve().parent
PDF_FILE = BASE_DIR / "input" / "B1 B2.pdf"


def main():
    doc = pymupdf.open(PDF_FILE)

    # Na początek tylko pierwsza strona PDF.
    page = doc[0]

    words = page.get_text("words", sort=True)

    print("=" * 100)
    print("B1-B2 PDF - WORD POSITIONS - PAGE 1")
    print("=" * 100)

    print(
        f"{'X0':>8} "
        f"{'Y0':>8} "
        f"{'X1':>8} "
        f"{'Y1':>8}  "
        f"TEXT"
    )

    print("-" * 100)

    for word in words:
        x0, y0, x1, y1, text, block_no, line_no, word_no = word

        # Pomijamy pusty tekst.
        if not text.strip():
            continue

        print(
            f"{x0:8.1f} "
            f"{y0:8.1f} "
            f"{x1:8.1f} "
            f"{y1:8.1f}  "
            f"{text}"
        )

    doc.close()


if __name__ == "__main__":
    main()