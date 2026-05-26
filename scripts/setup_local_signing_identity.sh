#!/usr/bin/env bash
set -euo pipefail

IDENTITY="${LINGOFLOW_LOCAL_CODESIGN_IDENTITY:-LingoFlow Local Development}"
KEYCHAIN="${LINGOFLOW_CODESIGN_KEYCHAIN:-$HOME/Library/Keychains/login.keychain-db}"
DAYS="${LINGOFLOW_LOCAL_CODESIGN_DAYS:-3650}"

if security find-identity -v -p codesigning 2>/dev/null | grep -F "\"$IDENTITY\"" >/dev/null; then
  echo "Local code-signing identity already exists: $IDENTITY"
  exit 0
fi

if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl is required to create the local signing certificate." >&2
  exit 1
fi

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

delete_stale_certificates() {
  local hashes
  hashes="$(security find-certificate -a -c "$IDENTITY" -Z "$KEYCHAIN" 2>/dev/null \
    | awk '/SHA-1 hash:/ {print $3}')"

  if [[ -z "$hashes" ]]; then
    return
  fi

  while IFS= read -r hash; do
    [[ -z "$hash" ]] && continue
    echo "Removing stale certificate without usable signing identity: $hash"
    security delete-certificate -Z "$hash" "$KEYCHAIN" >/dev/null 2>&1 || true
  done <<< "$hashes"
}

delete_stale_certificates

OPENSSL_CONFIG="$TMP_DIR/openssl.cnf"
KEY_FILE="$TMP_DIR/lingoflow-local-signing.key"
CERT_FILE="$TMP_DIR/lingoflow-local-signing.crt"
P12_FILE="$TMP_DIR/lingoflow-local-signing.p12"
P12_PASSWORD="$(openssl rand -hex 24)"

cat > "$OPENSSL_CONFIG" <<EOF
[ req ]
default_bits = 2048
distinguished_name = dn
x509_extensions = code_signing_cert
prompt = no

[ dn ]
CN = $IDENTITY
O = LingoFlow

[ code_signing_cert ]
basicConstraints = critical, CA:true
keyUsage = critical, digitalSignature, keyCertSign
extendedKeyUsage = codeSigning
subjectKeyIdentifier = hash
EOF

openssl req \
  -new \
  -newkey rsa:2048 \
  -nodes \
  -x509 \
  -days "$DAYS" \
  -sha256 \
  -config "$OPENSSL_CONFIG" \
  -keyout "$KEY_FILE" \
  -out "$CERT_FILE" >/dev/null 2>&1

openssl pkcs12 \
  -export \
  -legacy \
  -inkey "$KEY_FILE" \
  -in "$CERT_FILE" \
  -name "$IDENTITY" \
  -out "$P12_FILE" \
  -passout "pass:$P12_PASSWORD" >/dev/null 2>&1

security import "$P12_FILE" \
  -k "$KEYCHAIN" \
  -f pkcs12 \
  -P "$P12_PASSWORD" \
  -T /usr/bin/codesign \
  -T /usr/bin/security

security add-trusted-cert \
  -r trustRoot \
  -p codeSign \
  -k "$KEYCHAIN" \
  "$CERT_FILE"

if [[ -n "${LINGOFLOW_KEYCHAIN_PASSWORD:-}" ]]; then
  security set-key-partition-list \
    -S apple-tool:,apple:,codesign: \
    -s \
    -k "$LINGOFLOW_KEYCHAIN_PASSWORD" \
    "$KEYCHAIN" >/dev/null
fi

if ! security find-identity -v -p codesigning 2>/dev/null | grep -F "\"$IDENTITY\"" >/dev/null; then
  echo "Created certificate, but macOS does not list it as a valid code-signing identity." >&2
  echo "Open Keychain Access and verify that '$IDENTITY' has a private key." >&2
  exit 1
fi

echo "Created local code-signing identity: $IDENTITY"
echo "Future builds will use it automatically, or explicitly with:"
echo "  LINGOFLOW_CODESIGN_IDENTITY=\"$IDENTITY\" scripts/build_macos_app.sh"
