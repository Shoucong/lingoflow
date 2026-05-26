#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPEC_FILE="$ROOT_DIR/packaging/macos/LingoFlow.spec"
APP_PATH="$ROOT_DIR/dist/LingoFlow.app"
ENTITLEMENTS="$ROOT_DIR/packaging/macos/entitlements.plist"
LOCAL_SIGN_IDENTITY="${LINGOFLOW_LOCAL_CODESIGN_IDENTITY:-LingoFlow Local Development}"

cd "$ROOT_DIR"
export PYINSTALLER_CONFIG_DIR="${PYINSTALLER_CONFIG_DIR:-$ROOT_DIR/build/pyinstaller-cache}"

if ! python -c "import PyInstaller" >/dev/null 2>&1; then
  echo "PyInstaller is not installed."
  echo "Install packaging dependencies with: python -m pip install -e '.[package]'"
  exit 1
fi

python -m PyInstaller --clean --noconfirm "$SPEC_FILE"

if [[ ! -d "$APP_PATH" ]]; then
  echo "Build failed: $APP_PATH was not created."
  exit 1
fi

if [[ "${LINGOFLOW_SKIP_CODESIGN:-0}" != "1" ]]; then
  SIGN_IDENTITY="${LINGOFLOW_CODESIGN_IDENTITY:-}"
  if [[ -z "$SIGN_IDENTITY" ]]; then
    if security find-identity -v -p codesigning 2>/dev/null | grep -F "\"$LOCAL_SIGN_IDENTITY\"" >/dev/null; then
      SIGN_IDENTITY="$LOCAL_SIGN_IDENTITY"
    else
      SIGN_IDENTITY="-"
    fi
  fi

  echo "Signing with identity: $SIGN_IDENTITY"
  codesign \
    --force \
    --deep \
    --options runtime \
    --entitlements "$ENTITLEMENTS" \
    --sign "$SIGN_IDENTITY" \
    "$APP_PATH"
  codesign --verify --deep --strict "$APP_PATH"
else
  echo "Code signing skipped."
fi

echo "Built $APP_PATH"
echo "LSUIElement:"
/usr/libexec/PlistBuddy -c "Print :LSUIElement" "$APP_PATH/Contents/Info.plist"
echo "Signature:"
codesign -dvvv "$APP_PATH" 2>&1 | sed -n "1,14p"
