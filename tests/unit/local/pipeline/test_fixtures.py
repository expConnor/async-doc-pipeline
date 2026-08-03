import pymupdf
from pipeline.fixtures import SAMPLE_PDF, garbage_pdf, slow_pdf


def test_slow_pdf_generates_at_least_60_pages(tmp_path):
    path = slow_pdf(dest_dir=tmp_path, source=SAMPLE_PDF)

    assert path.parent == tmp_path
    doc = pymupdf.open(path)
    try:
        assert doc.page_count >= 60
    finally:
        doc.close()


def test_slow_pdf_is_not_regenerated_if_present(tmp_path):
    first = slow_pdf(dest_dir=tmp_path, source=SAMPLE_PDF)
    mtime_before = first.stat().st_mtime_ns

    second = slow_pdf(dest_dir=tmp_path, source=SAMPLE_PDF)

    assert second == first
    assert second.stat().st_mtime_ns == mtime_before


def test_garbage_pdf_is_not_a_valid_pdf(tmp_path):
    path = garbage_pdf(dest_dir=tmp_path)

    assert path.exists()
    assert path.suffix == ".pdf"
    try:
        pymupdf.open(path)
        raised = False
    except Exception:
        raised = True
    assert raised
