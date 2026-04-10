#!/usr/bin/env bash
#
# Build, sign, notarize, and package "Videohub Controller" for distribution.
#
# Output: dist/Videohub Controller.dmg
#
# Usage:  ./build_and_sign.sh
#

set -euo pipefail

# ----- Config ---------------------------------------------------------------

APP_NAME="Videohub Controller"
APP_PATH="dist/${APP_NAME}.app"
DMG_NAME="Videohub Controller"
DMG_PATH="dist/${DMG_NAME}.dmg"
ENTITLEMENTS="entitlements.plist"
NOTARY_PROFILE="${NOTARY_PROFILE:-chads-davinci-notary}"

# Auto-detect signing identity
if [[ -z "${SIGN_IDENTITY:-}" ]]; then
    SIGN_IDENTITY="$(security find-identity -v -p codesigning \
        | awk -F'"' '/Developer ID Application/ {print $2; exit}')"
fi
if [[ -z "${SIGN_IDENTITY:-}" ]]; then
    echo "ERROR: No 'Developer ID Application' code-signing identity found."
    exit 1
fi

echo "==> Using signing identity: ${SIGN_IDENTITY}"
echo "==> Using notarytool profile: ${NOTARY_PROFILE}"

# ----- 1. Clean + build .app via py2app ------------------------------------

echo "==> Cleaning previous build..."
rm -rf build dist

PYPROJECT_HIDDEN=0
if [[ -f pyproject.toml ]]; then
    mv pyproject.toml pyproject.toml.bak
    PYPROJECT_HIDDEN=1
fi
trap '[[ "${PYPROJECT_HIDDEN}" == "1" ]] && [[ -f pyproject.toml.bak ]] && mv pyproject.toml.bak pyproject.toml || true' EXIT

echo "==> Building .app via py2app..."
PYTHONPATH=src python3 setup.py py2app

if [[ ! -d "${APP_PATH}" ]]; then
    echo "ERROR: py2app did not produce ${APP_PATH}"
    exit 1
fi

if [[ "${PYPROJECT_HIDDEN}" == "1" ]] && [[ -f pyproject.toml.bak ]]; then
    mv pyproject.toml.bak pyproject.toml
    PYPROJECT_HIDDEN=0
fi

# ----- 2. Sign nested binaries ---------------------------------------------

echo "==> Signing nested Mach-O binaries..."
find "${APP_PATH}" \
    \( -name "*.dylib" -o -name "*.so" \
       -o -path "*/Contents/MacOS/*" -o -path "*/Frameworks/*/Versions/*/Python*" \) \
    -type f -print0 \
  | while IFS= read -r -d '' f; do
        codesign --force --options runtime --timestamp \
                 --entitlements "${ENTITLEMENTS}" \
                 --sign "${SIGN_IDENTITY}" "$f" || true
    done

# ----- 3. Sign the .app bundle ---------------------------------------------

echo "==> Signing the app bundle..."
codesign --force --deep --options runtime --timestamp \
         --entitlements "${ENTITLEMENTS}" \
         --sign "${SIGN_IDENTITY}" "${APP_PATH}"

echo "==> Verifying signature..."
codesign --verify --deep --strict --verbose=2 "${APP_PATH}"

# ----- 4. Notarize ---------------------------------------------------------

ZIP_PATH="dist/${APP_NAME}.zip"
echo "==> Zipping for notarization..."
ditto -c -k --sequesterRsrc --keepParent "${APP_PATH}" "${ZIP_PATH}"

echo "==> Submitting to Apple notarization service..."
xcrun notarytool submit "${ZIP_PATH}" \
    --keychain-profile "${NOTARY_PROFILE}" \
    --wait

echo "==> Stapling notarization ticket..."
xcrun stapler staple "${APP_PATH}"
xcrun stapler validate "${APP_PATH}"

rm -f "${ZIP_PATH}"

# ----- 5. Build the DMG ----------------------------------------------------

echo "==> Building DMG via dmgbuild..."
rm -f "${DMG_PATH}"

if python3 -c "import dmgbuild" 2>/dev/null; then
    python3 -m dmgbuild -s dmg_settings.py "Videohub Controller" "${DMG_PATH}"
elif command -v create-dmg &>/dev/null; then
    create-dmg \
        --volname "${DMG_NAME}" \
        --window-pos 200 120 \
        --window-size 600 400 \
        --icon-size 100 \
        --icon "${APP_NAME}.app" 150 190 \
        --app-drop-link 450 190 \
        "${DMG_PATH}" \
        "${APP_PATH}"
else
    hdiutil create -volname "${DMG_NAME}" -srcfolder "${APP_PATH}" \
        -ov -format UDZO "${DMG_PATH}"
fi

# ----- 6. Sign + notarize the DMG ------------------------------------------

echo "==> Signing the DMG..."
codesign --force --sign "${SIGN_IDENTITY}" --timestamp "${DMG_PATH}"

echo "==> Notarizing the DMG..."
xcrun notarytool submit "${DMG_PATH}" \
    --keychain-profile "${NOTARY_PROFILE}" \
    --wait

echo "==> Stapling DMG..."
xcrun stapler staple "${DMG_PATH}"
xcrun stapler validate "${DMG_PATH}"

echo
echo "================================================================="
echo " SUCCESS"
echo " Signed + notarized DMG: ${DMG_PATH}"
echo "================================================================="
