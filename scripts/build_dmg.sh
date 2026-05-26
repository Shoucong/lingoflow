#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="LingoFlow"
APP_PATH="$ROOT_DIR/dist/$APP_NAME.app"
DMG_PATH="${LINGOFLOW_DMG_PATH:-$ROOT_DIR/dist/$APP_NAME.dmg}"
STAGING_DIR="$ROOT_DIR/build/dmg/$APP_NAME"
VOLUME_NAME="${LINGOFLOW_DMG_VOLUME_NAME:-$APP_NAME}"

cd "$ROOT_DIR"

if [[ "${LINGOFLOW_SKIP_APP_BUILD:-0}" != "1" ]]; then
  "$ROOT_DIR/scripts/build_macos_app.sh"
fi

if [[ ! -d "$APP_PATH" ]]; then
  echo "Missing app bundle: $APP_PATH"
  echo "Run scripts/build_macos_app.sh first, or unset LINGOFLOW_SKIP_APP_BUILD."
  exit 1
fi

codesign --verify --deep --strict "$APP_PATH"

case "$STAGING_DIR" in
  "$ROOT_DIR"/build/dmg/*) ;;
  *)
    echo "Refusing to clean unexpected staging path: $STAGING_DIR"
    exit 1
    ;;
esac

rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"
mkdir -p "$(dirname "$DMG_PATH")"

ditto "$APP_PATH" "$STAGING_DIR/$APP_NAME.app"
ln -s /Applications "$STAGING_DIR/Applications"

rm -f "$DMG_PATH"
hdiutil create \
  -volname "$VOLUME_NAME" \
  -srcfolder "$STAGING_DIR" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

hdiutil verify "$DMG_PATH"

echo "Built $DMG_PATH"
du -h "$DMG_PATH"
