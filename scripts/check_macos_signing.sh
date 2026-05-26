#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_PATH="${1:-$ROOT_DIR/dist/LingoFlow.app}"

if [[ ! -d "$APP_PATH" ]]; then
  echo "App bundle not found: $APP_PATH" >&2
  exit 1
fi

echo "App: $APP_PATH"
echo
echo "Bundle metadata:"
/usr/libexec/PlistBuddy \
  -c "Print :CFBundleIdentifier" \
  -c "Print :CFBundleName" \
  -c "Print :LSUIElement" \
  "$APP_PATH/Contents/Info.plist"

echo
echo "Signature:"
codesign -dvvv "$APP_PATH" 2>&1

echo
echo "Entitlements:"
codesign -d --entitlements :- "$APP_PATH" 2>/dev/null || true

echo
echo "Verification:"
codesign --verify --deep --strict --verbose=1 "$APP_PATH"

echo
echo "Available code-signing identities:"
security find-identity -v -p codesigning || true
