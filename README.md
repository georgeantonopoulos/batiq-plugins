# BATIQ plugins

Ready-built downloads of BATIQ's extensions, one zip per machine, so
artists never need Rust or a compiler. BATIQ fetches these itself:
*Settings → Extensions → Get more*. You don't need to download anything
from here by hand.

| Plugin | What it does | Latest |
| --- | --- | --- |
| SAM3 | Mattes from a click: Segment Anything 3 tracks the object through the shot. | [sam3-v0.3.0](https://github.com/georgeantonopoulos/batiq-plugins/releases/tag/sam3-v0.3.0) |
| Deadline | Submit renders to a Thinkbox Deadline 10 farm, and set up the farm side. | [deadline-v1.0.0](https://github.com/georgeantonopoulos/batiq-plugins/releases/tag/deadline-v1.0.0) |

Each release is tagged `<plugin>-v<version>` and holds one zip per machine:
`macos-arm64`, `macos-x64`, `linux-x64` (glibc 2.34 or newer) and
`windows-x64`, plus `SHA256SUMS`. A plugin written only in Python ships one
`any` zip for every machine. BATIQ checks each zip's SHA-256 before
installing it.

## Building a release

```sh
scripts/build.sh <plugin source> <BATIQ checkout>/sdk/rust/batiq-plugin dist/
```

It builds the macOS programs on the Mac and the Linux and Windows ones in
pinned Docker images (Rocky Linux 9 and MinGW), then packages each zip as
the plugin's folder minus its Rust source, with the program in `bin/`.

## Shipping an update

BATIQ reads [`catalogue.json`](catalogue.json) from this repository's main
branch. A plugin updates the moment a pull request moving its entry merges:
no BATIQ release and no website deploy.

1. Build the zips (above) and publish them as release `<plugin>-v<version>`
   with `SHA256SUMS`.
2. `scripts/catalogue.py set <plugin> dist/` points the entry at that
   release, with each zip's checksum and size.
3. Open a pull request. Its checks download every zip, match it to the
   list, refuse any that names a home folder, and install the changed
   plugin through the latest BATIQ on macOS, Linux and Windows, running its
   setup where that BATIQ can. The template lists what to walk by hand in
   the app first.
4. Merge. Running BATIQs offer the new version the next time they read the
   list.

Run the same checks locally with `scripts/catalogue.py check` and
`scripts/catalogue.py install <path to batiq-headless>`.

The plugins are MIT licensed. Models they download (such as Meta's SAM3
weights) stay under their own licences.
