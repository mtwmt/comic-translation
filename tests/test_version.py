import re
from pathlib import Path

from src.version import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_windows_version_resource_matches_application_version():
    resource = (ROOT / "tools/packaging/version_info.txt").read_text(encoding="utf-8")
    assert re.findall(r"'(?:File|Product)Version', '([^']+)'", resource) == [__version__] * 2
    numbers = tuple(int(part) for part in __version__.split(".")) + (0,)
    assert re.findall(r"(?:filevers|prodvers)=\(([^)]+)\)", resource) == [", ".join(map(str, numbers))] * 2
