"""Tests need the fallback font, which is downloaded rather than stored in git."""
import pytest

from src.offline import fonts


@pytest.fixture(scope="session", autouse=True)
def bundled_font():
    try:
        return fonts.ensure_bundled_font()
    except fonts.ModelError as error:
        pytest.exit(f"需要字型才能執行測試：{error}", returncode=2)
