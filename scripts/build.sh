#!/usr/bin/env bash
# Builds one Rust plugin ready to run on every machine BATIQ ships for, and
# packages one zip per machine for a GitHub release of this repo.
#
#   scripts/build.sh <plugin source> <batiq-plugin SDK folder> <output folder>
#
# Each zip holds the plugin's folder without its Rust source: the manifest,
# README, licence, any Python, and bin/<program> built for that machine.
# BATIQ runs bin/ as is when the folder has no Cargo.toml, so artists never
# need Rust. Linux is built on Rocky 9 (glibc 2.34, the oldest BATIQ runs
# on) and Windows with MinGW, in the same pinned images as BATIQ's release.
set -euo pipefail
SOURCE=$(cd "$1" && pwd)
SDK=$(cd "$2" && pwd)
OUT=$(mkdir -p "$3" && cd "$3" && pwd)
ROCKY_IMAGE='rockylinux/rockylinux:9.5@sha256:149fd31d916038eb1084d0e051537e279d7afcd5de0b365254e8fa3c3ef12bad'
WINDOWS_IMAGE='rust:1.97-bookworm@sha256:77fac8b98f9f46062bb680b6d25d5bcaabfc400143952ebc572e924bcbedc3fa'
TOOLCHAIN=${RUSTUP_TOOLCHAIN:-stable-aarch64-apple-darwin}

name=$(sed -n 's/^name = "\(.*\)"/\1/p' "$SOURCE/Cargo.toml" | head -1)
version=$(sed -n 's/^version = "\(.*\)"/\1/p' "$SOURCE/batiq-extension.toml" | head -1)
crate_version=$(sed -n 's/^version = "\(.*\)"/\1/p' "$SOURCE/Cargo.toml" | head -1)
[ "$version" = "$crate_version" ] || { echo "manifest $version != Cargo.toml $crate_version" >&2; exit 1; }
patch="patch.crates-io.batiq-plugin.path=\"/sdk\""
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# macOS, both architectures, on this Mac.
for pair in aarch64-apple-darwin:macos-arm64 x86_64-apple-darwin:macos-x64; do
    target=${pair%%:*}; platform=${pair##*:}
    RUSTUP_TOOLCHAIN=$TOOLCHAIN CARGO_TARGET_DIR="$work/target" cargo build --locked --release \
        --manifest-path "$SOURCE/Cargo.toml" --target "$target" \
        --config "patch.crates-io.batiq-plugin.path=\"$SDK\""
    mkdir -p "$work/bin-$platform"
    cp "$work/target/$target/release/$name" "$work/bin-$platform/"
done

# Linux x64 on Rocky 9.
mkdir -p "$work/bin-linux-x64"
docker run --rm --platform linux/amd64 \
    -v "$SOURCE:/src:ro" -v "$SDK:/sdk:ro" -v "$work/bin-linux-x64:/out" \
    -v batiq-plugins-linux:/cache "$ROCKY_IMAGE" /bin/bash -lc "
    set -euo pipefail
    dnf install --assumeyes gcc >/dev/null
    export CARGO_HOME=/cache/cargo RUSTUP_HOME=/cache/rustup PATH=/cache/cargo/bin:\$PATH
    if [ ! -x /cache/cargo/bin/rustup ]; then
      curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs -o /tmp/rustup.sh
      sh /tmp/rustup.sh -y --no-modify-path --profile minimal --default-toolchain 1.97.0
    fi
    CARGO_TARGET_DIR=/cache/target cargo build --locked --release \
      --manifest-path /src/Cargo.toml --config '$patch'
    cp /cache/target/release/$name /out/"

# Windows x64 with MinGW.
mkdir -p "$work/bin-windows-x64"
docker run --rm --platform linux/arm64 \
    -v "$SOURCE:/src:ro" -v "$SDK:/sdk:ro" -v "$work/bin-windows-x64:/out" \
    -v batiq-plugins-windows:/cache "$WINDOWS_IMAGE" /bin/bash -c "
    set -euo pipefail
    apt-get update >/dev/null
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends gcc-mingw-w64-x86-64 >/dev/null
    rustup target add x86_64-pc-windows-gnu
    CARGO_HOME=/cache/cargo CARGO_TARGET_DIR=/cache/target cargo build --locked --release \
      --manifest-path /src/Cargo.toml --target x86_64-pc-windows-gnu --config '$patch'
    cp /cache/target/x86_64-pc-windows-gnu/release/$name.exe /out/"

# One zip per machine: the plugin's folder minus its Rust source.
for platform in macos-arm64 macos-x64 linux-x64 windows-x64; do
    folder="$work/zip-$platform/$name-$version"
    mkdir -p "$folder"
    (cd "$SOURCE" && git ls-files) | grep -v -E '^(Cargo\.(toml|lock)|src/|\.gitignore$)' |
        while read -r file; do mkdir -p "$folder/$(dirname "$file")"; cp "$SOURCE/$file" "$folder/$file"; done
    mkdir -p "$folder/bin"
    cp "$work/bin-$platform/"* "$folder/bin/"
    chmod 755 "$folder/bin/"*
    archive="$name-$version-$platform.zip"
    rm -f "$OUT/$archive"
    (cd "$work/zip-$platform" && zip -qrX "$OUT/$archive" "$name-$version")
    echo "$platform $(shasum -a 256 "$OUT/$archive" | cut -d' ' -f1) $(stat -f %z "$OUT/$archive") $archive"
done
