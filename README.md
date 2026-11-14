# BATIQ plugins

Ready-built downloads of BATIQ's extensions, one zip per machine, so
artists never need Rust or a compiler. BATIQ fetches these itself:
*Settings → Extensions → Get more*. You don't need to download anything
from here by hand.

| Plugin | What it does | Latest |
| --- | --- | --- |
| SAM3 | Mattes from a click: Segment Anything 3 tracks the object through the shot. | [sam3-v0.1.0](https://github.com/georgeantonopoulos/batiq-plugins/releases/tag/sam3-v0.1.0) |

Each release is tagged `<plugin>-v<version>` and holds one zip per machine:
`macos-arm64`, `macos-x64`, `linux-x64` (glibc 2.34 or newer) and
`windows-x64`, plus `SHA256SUMS`. BATIQ checks each zip's SHA-256 before
installing it.

## Building a release

```sh
scripts/build.sh <plugin source> <BATIQ checkout>/sdk/rust/batiq-plugin dist/
```

It builds the macOS programs on the Mac and the Linux and Windows ones in
pinned Docker images (Rocky Linux 9 and MinGW), then packages each zip as
the plugin's folder minus its Rust source, with the program in `bin/`.
Put the printed checksums and sizes into BATIQ's extension catalogue.

The plugins are MIT licensed. Models they download (such as Meta's SAM3
weights) stay under their own licences.
