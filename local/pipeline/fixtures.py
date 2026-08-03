"""Generate large/malformed PDF fixtures for chaos scenarios, from the
committed local/sample.pdf. Fixtures are regenerated on demand into
local/fixtures/ and are gitignored, keeping ~1MB of binary out of git
history and preventing drift from the source sample.
"""

from pathlib import Path

import pymupdf

SAMPLE_PDF = Path(__file__).parent.parent / "sample.pdf"
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

# Parse time is linear at ~1.0s/page on a 1-CPU worker (measured). 60 pages
# gives a ~60s window, wide enough to land a fault injection reliably mid-job.
SLOW_PDF_MIN_PAGES = 60


def slow_pdf(dest_dir: Path = FIXTURES_DIR, source: Path = SAMPLE_PDF) -> Path:
    path = dest_dir / "slow.pdf"
    if path.exists():
        return path

    dest_dir.mkdir(parents=True, exist_ok=True)
    src = pymupdf.open(source)
    out = pymupdf.open()
    try:
        while out.page_count < SLOW_PDF_MIN_PAGES:
            out.insert_pdf(src)
        out.save(path)
    finally:
        out.close()
        src.close()
    return path


def garbage_pdf(dest_dir: Path = FIXTURES_DIR) -> Path:
    path = dest_dir / "garbage.pdf"
    if path.exists():
        return path

    dest_dir.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"this is not a pdf file, just garbage bytes\n" * 100)
    return path
