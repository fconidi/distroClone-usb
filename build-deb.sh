#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="$(/usr/bin/python3 -c "import sys; sys.path.insert(0, sys.argv[1]); from distroclone_usb import __version__; print(__version__)" "$ROOT_DIR")"
STAGE_DIR="$(mktemp -d)"
trap 'rm -rf "$STAGE_DIR"' EXIT
install -d "$STAGE_DIR/DEBIAN" "$STAGE_DIR/usr/bin" "$STAGE_DIR/usr/lib/distroclone-usb/distroclone_usb" \
    "$STAGE_DIR/usr/share/applications" "$STAGE_DIR/usr/share/icons/hicolor/scalable/apps" \
    "$STAGE_DIR/usr/share/polkit-1/actions" "$STAGE_DIR/usr/share/doc/distroclone-usb" \
    "$STAGE_DIR/usr/share/man/man1" "$ROOT_DIR/dist"
install -m 644 "$ROOT_DIR"/distroclone_usb/*.py "$STAGE_DIR/usr/lib/distroclone-usb/distroclone_usb/"
install -m 644 "$ROOT_DIR/distroclone_usb/translations.json" "$STAGE_DIR/usr/lib/distroclone-usb/distroclone_usb/"
install -m 755 "$ROOT_DIR/helper.py" "$STAGE_DIR/usr/lib/distroclone-usb/helper.py"
install -m 755 "$ROOT_DIR/packaging/distroclone-usb" "$STAGE_DIR/usr/bin/distroclone-usb"
install -m 644 "$ROOT_DIR/packaging/distroclone-usb.desktop" "$STAGE_DIR/usr/share/applications/"
install -m 644 "$ROOT_DIR/packaging/distroclone-usb.svg" "$STAGE_DIR/usr/share/icons/hicolor/scalable/apps/"
install -m 644 "$ROOT_DIR/packaging/com.syslinuxos.distroclone-usb.policy" "$STAGE_DIR/usr/share/polkit-1/actions/"
install -m 644 "$ROOT_DIR/README.md" "$ROOT_DIR/LICENSE" "$STAGE_DIR/usr/share/doc/distroclone-usb/"
install -m 644 "$ROOT_DIR/packaging/copyright" "$STAGE_DIR/usr/share/doc/distroclone-usb/copyright"
gzip -n -9 -c "$ROOT_DIR/CHANGELOG.md" > "$STAGE_DIR/usr/share/doc/distroclone-usb/changelog.gz"
gzip -n -9 -c "$ROOT_DIR/packaging/changelog" > "$STAGE_DIR/usr/share/doc/distroclone-usb/changelog.Debian.gz"
gzip -n -9 -c "$ROOT_DIR/packaging/distroclone-usb.1" > "$STAGE_DIR/usr/share/man/man1/distroclone-usb.1.gz"
chmod 644 "$STAGE_DIR/usr/share/doc/distroclone-usb/"*.gz "$STAGE_DIR/usr/share/man/man1/"*.gz
install -m 644 "$ROOT_DIR/docs/COMPATIBILITY.md" "$STAGE_DIR/usr/share/doc/distroclone-usb/"
install -m 644 "$ROOT_DIR/docs/VALIDATION.md" "$STAGE_DIR/usr/share/doc/distroclone-usb/"
sed "s/@VERSION@/$VERSION/" "$ROOT_DIR/packaging/control" > "$STAGE_DIR/DEBIAN/control"
find "$STAGE_DIR" -type d -exec chmod 755 {} +
dpkg-deb --root-owner-group --build "$STAGE_DIR" "$ROOT_DIR/dist/distroclone-usb_${VERSION}_all.deb"
