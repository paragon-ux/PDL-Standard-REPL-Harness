import re
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.bump_version import compute_next_version, VERSION_PATTERN


def test_compute_next_version_patch():
    assert compute_next_version("2.4.0", "patch") == "2.4.1"
    assert compute_next_version("1.0.9", "patch") == "1.0.10"


def test_compute_next_version_minor():
    assert compute_next_version("2.4.0", "minor") == "2.5.0"
    assert compute_next_version("2.4.9", "minor") == "2.5.0"


def test_compute_next_version_major():
    assert compute_next_version("2.4.0", "major") == "3.0.0"


def test_compute_next_version_explicit():
    assert compute_next_version("2.4.0", "2.4.1rc1") == "2.4.1rc1"
    assert compute_next_version("2.4.0", "3.0.0a1") == "3.0.0a1"


def test_compute_next_version_invalid():
    with pytest.raises(ValueError, match="Invalid target version"):
        compute_next_version("2.4.0", "not-a-version")


def test_version_pattern_matches_init(tmp_path: Path):
    init_content = '__version__ = "2.4.0"\n'
    match = VERSION_PATTERN.search(init_content)
    assert match is not None
    assert match.group(1) == "2.4.0"

    new_content, count = VERSION_PATTERN.subn('__version__ = "2.4.1"', init_content)
    assert count == 1
    assert '__version__ = "2.4.1"' in new_content
