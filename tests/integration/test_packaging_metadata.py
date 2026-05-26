from __future__ import annotations

from lingoflow.config.constants import APP_ICON_FILE, APP_NAME, BUNDLE_IDENTIFIER


def test_packaging_metadata_points_at_app_identity_and_icon() -> None:
    assert APP_NAME == "LingoFlow"
    assert BUNDLE_IDENTIFIER == "com.shoucong.lingoflow"
    assert APP_ICON_FILE.exists()
    assert APP_ICON_FILE.suffix == ".icns"
