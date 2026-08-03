"""Generate large/malformed PDF fixtures for chaos scenarios, from the
committed local/sample.pdf. Fixtures are regenerated on demand into
local/fixtures/ and are gitignored, keeping ~1MB of binary out of git
history and preventing drift from the source sample.
"""

from pathlib import Path

import pymupdf

SAMPLE_PDF = Path(__file__).parent.parent / "sample.pdf"
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

# Parse time is linear at ~1.0s/page on a 1-CPU worker (measured). 30 pages
# gives a ~30s window, wide enough to land a fault injection reliably mid-job.
SLOW_PDF_MIN_PAGES = 30


# "Fixture" here means a test input file generated on demand rather than
# committed to git — the function is named for what it produces (a
# slow-to-parse PDF), not for any testing framework concept.
def slow_pdf(dest_dir: Path = FIXTURES_DIR, source: Path = SAMPLE_PDF) -> Path:
    path = dest_dir / "slow.pdf"
    if path.exists():
        return path

    dest_dir.mkdir(parents=True, exist_ok=True)
    # pymupdf.open() with no argument creates a new, empty PDF in memory.
    # insert_pdf() appends all of `src`'s pages onto the end of `out` — called
    # repeatedly in the loop below, it duplicates the small sample PDF into
    # `out` until there are enough pages to take ~60 seconds to parse.
    src = pymupdf.open(source)
    out = pymupdf.open()
    # `try`/`finally` guarantees the `.close()` calls run even if something
    # above raises partway through — otherwise a failure mid-loop would leak
    # the open file handles pymupdf holds for `src` and `out`.
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
