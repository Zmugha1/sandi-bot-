"""
Quick local run: extract from a small in-memory PDF and print debug counts.
Run from sandi-bot: py run_extraction_debug.py
"""
import io
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))


def main():
    from kg import extract_pdf as ext

    # Build minimal PDF with Do/Don't lines (requires fitz)
    try:
        import fitz
        doc = fitz.open()
        page = doc.new_page()
        text = (
            "Checklist for Communicating\n"
            "Do: People-oriented.\n"
            "Do: Big thinker.\n"
            "Don't: Leave decisions hanging in the air.\n"
            "Do: Provide 'yes' or 'no' answers—not maybe.\n"
        )
        filler = "Behavioral report. " * 80
        page.insert_text((50, 50), text + "\n\n" + filler)
        buf = io.BytesIO()
        doc.save(buf)
        doc.close()
        pdf_bytes = buf.getvalue()
    except Exception as e:
        print("Could not create PDF (fitz):", e)
        return

    out = ext.extract_facts("Zubia Mughal", "ttsi_doc", pdf_bytes)
    print("extraction_status:", out.get("extraction_status"))
    print("do_lines_found_count:", out.get("do_lines_found_count"))
    print("dont_lines_found_count:", out.get("dont_lines_found_count"))
    print("facts_count_by_type:", out.get("facts_count_by_type"))
    print("facts count:", len(out.get("facts", [])))
    for i, f in enumerate(out.get("facts", [])[:12]):
        lbl = (f.get("label") or "")[:60]
        print(f"  [{i}] {f.get('type')}: {repr(lbl)}")
    if len(out.get("facts", [])) > 12:
        print("  ...")


if __name__ == "__main__":
    main()
