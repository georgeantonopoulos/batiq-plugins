Merging this ships the change: BATIQ reads `catalogue.json` from main.

## Extension

- Id and version:
- Release: https://github.com/georgeantonopoulos/batiq-plugins/releases/tag/<id>-v<version>

## Checked by hand (the robots can't)

Walked in the BATIQ app, on a real machine, for this version:

- [ ] **Install:** Get Extensions offers it, installs it, and says what it does.
- [ ] **Setup:** shows its progress; ends ready, or fails saying what to do.
- [ ] **Model / data:** downloading it, or linking one already on disk, works and says where it went.
- [ ] **Failure:** a missing GPU, token, network or file gives an error with its one fix, never silence.
- [ ] Machines walked: (Windows and Linux untested unless listed)

The pull request's checks cover the rest: every zip downloads, matches its
SHA-256 and size, names the right id and version, holds no home folder, and
installs through the latest BATIQ on macOS, Linux and Windows.
