#!/usr/bin/env bash
set -e

if ! command -v flutter >/dev/null 2>&1; then
  echo "Flutter is not installed or is not in PATH. Install Flutter stable first."
  exit 1
fi

TMP_DIR="$(mktemp -d)"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

flutter create "$TMP_DIR/psc_mentor_shell" \
  --project-name psc_mentor \
  --org in.pscmentor \
  --platforms=android,ios,macos,windows

for platform in android ios macos windows; do
  rm -rf "./$platform"
  cp -R "$TMP_DIR/psc_mentor_shell/$platform" "./$platform"
done

flutter pub get
flutter doctor

echo "Platform shells generated without replacing your lib/ or docs/. Run: flutter run"
