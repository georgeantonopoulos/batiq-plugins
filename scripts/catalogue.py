#!/usr/bin/env python3
"""The list of extensions BATIQ offers (catalogue.json), and its checks.

BATIQ reads catalogue.json from this repository's main branch, so a plugin
updates the moment a pull request moving its entry merges, with no BATIQ or
website release. These checks run on that pull request (and by hand):

  scripts/catalogue.py set <id> <dist folder> [--name --tagline --needs]
      point <id> at its release, from the zips scripts/build.sh made
  scripts/catalogue.py check [--only id,id]
      every zip downloads and matches its SHA-256, size, id and version,
      and names no user or home folder
  scripts/catalogue.py install <batiq-headless> [--only id,id] [--no-setup]
      install each through BATIQ on this machine and run its setup, which
      must end ready or fail with a reason an artist can act on
  scripts/catalogue.py changed <older catalogue.json>
      the ids whose entry differs (what a pull request needs checked)

Standard library only, Python 3.9 or newer, on macOS, Linux and Windows.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOGUE = ROOT / "catalogue.json"
REPO = "georgeantonopoulos/batiq-plugins"
PLATFORMS = ("macos-arm64", "macos-x64", "linux-x64", "windows-x64", "any")
ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
# A public download must not say who built it or where: a home folder in a
# panic path, a log line or a default setting.
PERSONAL = [
    re.compile(rb"/Users/(?!Shared/)[A-Za-z0-9._-]+/"),
    re.compile(rb"/home/[a-z_][a-z0-9_.-]*/"),
    re.compile(rb"[A-Za-z]:\\{1,2}Users\\{1,2}(?!Public\\)[A-Za-z0-9._ -]+\\"),
]
# Setup's failure must say what to do; a bare traceback does not.
BARE_FAILURES = ("Traceback (most recent call last)", "exit status", "exit code")


def fail(message):
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def load(path=CATALOGUE):
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def save(catalogue):
    text = json.dumps(catalogue, indent=2, ensure_ascii=False) + "\n"
    CATALOGUE.write_text(text, encoding="utf-8")


def this_platform():
    machine = os.uname().machine if hasattr(os, "uname") else os.environ.get("PROCESSOR_ARCHITECTURE", "")
    arm = machine.lower() in ("arm64", "aarch64")
    if sys.platform == "darwin":
        return "macos-arm64" if arm else "macos-x64"
    if sys.platform.startswith("linux"):
        return "linux-arm64" if arm else "linux-x64"
    if sys.platform == "win32":
        return "windows-arm64" if arm else "windows-x64"
    return sys.platform


def selected(catalogue, only):
    offers = catalogue["extensions"]
    if not only:
        return offers
    wanted = [id for id in only.split(",") if id]
    unknown = sorted(set(wanted) - {offer["id"] for offer in offers})
    if unknown:
        fail(f"not in catalogue.json: {', '.join(unknown)}")
    return [offer for offer in offers if offer["id"] in wanted]


# ---------------------------------------------------------------- the shape


def check_shape(catalogue):
    """The rules BATIQ's own reader applies, plus this repository's."""
    problems = []
    if catalogue.get("schema_version") != 1:
        problems.append("schema_version must be 1")
    seen = set()
    for offer in catalogue.get("extensions", []):
        id = offer.get("id", "")
        if not ID.match(id):
            problems.append(f"bad id {id!r}")
        if id in seen:
            problems.append(f"'{id}' is listed twice")
        seen.add(id)
        for field in ("name", "tagline", "needs"):
            if not str(offer.get(field, "")).strip():
                problems.append(f"'{id}' needs a {field}: artists see it before installing")
        version = offer.get("version", "")
        if not SEMVER.match(version):
            problems.append(f"'{id}' version {version!r} is not x.y.z")
        downloads = offer.get("downloads", {})
        if not downloads:
            problems.append(f"'{id}' offers no download")
        for platform_name, download in downloads.items():
            where = f"'{id}' {platform_name}"
            if platform_name not in PLATFORMS:
                problems.append(f"{where}: unknown machine (use {', '.join(PLATFORMS)})")
            url = download.get("url", "")
            if not url.startswith("https://"):
                problems.append(f"{where}: the url must be https")
            if f"/{id}-v{version}/" not in url:
                problems.append(f"{where}: the url is not the {id}-v{version} release")
            if not SHA256.match(download.get("sha256", "")):
                problems.append(f"{where}: needs the zip's SHA-256 (64 lowercase hex)")
            if not download.get("size"):
                problems.append(f"{where}: needs the zip's size")
    return problems


# --------------------------------------------------------------- the zips


def manifest_fields(text):
    """id and version from batiq-extension.toml's top table."""
    fields = {}
    for line in text.splitlines():
        if line.strip().startswith("["):
            break
        match = re.match(r'^\s*(id|version)\s*=\s*"([^"]*)"', line)
        if match:
            fields[match.group(1)] = match.group(2)
    return fields


def check_zip(path, offer, platform_name):
    """Problems with one downloaded zip, as the artist would install it."""
    problems = []
    where = f"'{offer['id']}' {platform_name}"
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        manifests = [
            name for name in names
            if name.endswith("batiq-extension.toml") and name.count("/") <= 1
        ]
        if len(manifests) != 1:
            problems.append(f"{where}: the zip must hold one batiq-extension.toml at its top or one folder down")
        else:
            fields = manifest_fields(archive.read(manifests[0]).decode("utf-8"))
            if fields.get("id") != offer["id"]:
                problems.append(f"{where}: the zip is extension {fields.get('id')!r}, not {offer['id']!r}")
            if fields.get("version") != offer["version"]:
                problems.append(f"{where}: the zip is version {fields.get('version')!r}, not {offer['version']!r}")
        for name in names:
            if name.endswith("/"):
                continue
            data = archive.read(name)
            for pattern in PERSONAL:
                found = pattern.search(data)
                if found:
                    shown = found.group(0).decode("utf-8", "replace")
                    problems.append(f"{where}: {name} names a home folder ({shown}); rebuild with scripts/build.sh")
                    break
    return problems


def download(url, into):
    request = urllib.request.Request(url, headers={"User-Agent": "batiq-plugins-check"})
    with urllib.request.urlopen(request, timeout=120) as response, open(into, "wb") as file:
        shutil.copyfileobj(response, file)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for block in iter(lambda: file.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def command_check(args):
    catalogue = load()
    problems = check_shape(catalogue)
    with tempfile.TemporaryDirectory() as scratch:
        for offer in selected(catalogue, args.only):
            for platform_name, entry in offer["downloads"].items():
                print(f"checking {offer['id']} {offer['version']} {platform_name}", flush=True)
                zip_path = Path(scratch) / f"{offer['id']}-{platform_name}.zip"
                try:
                    download(entry["url"], zip_path)
                except Exception as error:  # noqa: BLE001 - reported as a finding
                    problems.append(f"'{offer['id']}' {platform_name}: cannot download {entry['url']}: {error}")
                    continue
                if sha256(zip_path) != entry["sha256"]:
                    problems.append(f"'{offer['id']}' {platform_name}: the zip's SHA-256 is not the one listed")
                if zip_path.stat().st_size != entry["size"]:
                    problems.append(f"'{offer['id']}' {platform_name}: the zip is {zip_path.stat().st_size} bytes, not {entry['size']}")
                problems += check_zip(zip_path, offer, platform_name)
                zip_path.unlink()
    report(problems, "catalogue.json")


def report(problems, what):
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    if problems:
        fail(f"{len(problems)} problem(s) in {what}")
    print(f"{what}: all checks passed")


# ------------------------------------------------------------- set an entry


def command_set(args):
    dist = Path(args.dist)
    sums = {}
    sums_file = dist / "SHA256SUMS"
    if not sums_file.exists():
        fail(f"{sums_file} is missing; scripts/build.sh's zips and their SHA256SUMS go there")
    for line in sums_file.read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        sums[name.strip().lstrip("*")] = digest
    downloads, version = {}, None
    for name, digest in sorted(sums.items()):
        match = re.match(r"^(.+)-(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)-([a-z0-9]+-[a-z0-9]+|any)\.zip$", name)
        if not match:
            fail(f"{name} is not <name>-<version>-<machine>.zip")
        if version and match.group(2) != version:
            fail(f"{dist} holds more than one version")
        version = match.group(2)
        path = dist / name
        if sha256(path) != digest:
            fail(f"{name} does not match SHA256SUMS")
        offer_stub = {"id": args.id, "version": version}
        problems = check_zip(path, offer_stub, match.group(3))
        if problems:
            report(problems, name)
        downloads[match.group(3)] = {
            "url": f"https://github.com/{REPO}/releases/download/{args.id}-v{version}/{name}",
            "sha256": digest,
            "size": path.stat().st_size,
        }
    catalogue = load()
    offer = next((offer for offer in catalogue["extensions"] if offer["id"] == args.id), None)
    if offer is None:
        if not (args.name and args.tagline and args.needs):
            fail(f"'{args.id}' is new: give --name, --tagline and --needs")
        offer = {"id": args.id}
        catalogue["extensions"].append(offer)
    for field in ("name", "tagline", "needs"):
        if getattr(args, field):
            offer[field] = getattr(args, field)
    offer["version"] = version
    offer["downloads"] = downloads
    offer.setdefault("repository", f"https://github.com/{REPO}")
    ordered = {key: offer[key] for key in ("id", "name", "tagline", "version", "downloads", "needs", "repository") if key in offer}
    offer.clear()
    offer.update(ordered)
    report(check_shape(catalogue), "catalogue.json")
    save(catalogue)
    print(f"{args.id} now offers {version} on {', '.join(downloads)}")


# --------------------------------------------------- install through BATIQ


def headless_session(binary, home, requests, timeout):
    """Runs batiq-headless over the requests; answers by request id."""
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["XDG_DATA_HOME"] = str(home / "data")
    env["XDG_CONFIG_HOME"] = str(home / "config")
    env["XDG_CACHE_HOME"] = str(home / "cache")
    env["LOCALAPPDATA"] = str(home / "local")
    env["APPDATA"] = str(home / "roaming")
    env["USERPROFILE"] = str(home)
    env["BATIQ_EXTENSION_CATALOGUE"] = str(CATALOGUE)
    env.pop("BATIQ_EXTENSION_PATH", None)
    lines = [{"jsonrpc": "2.0", "id": 0, "method": "initialize",
              "params": {"protocol_version": {"major": 1, "minor": 2}}}]
    lines += [{"jsonrpc": "2.0", "id": n + 1, "method": method, "params": params}
              for n, (method, params) in enumerate(requests)]
    stdin = "".join(json.dumps(line) + "\n" for line in lines)
    run = subprocess.run([str(binary)], input=stdin, capture_output=True, text=True,
                         env=env, timeout=timeout, encoding="utf-8", errors="replace")
    answers = {}
    for line in run.stdout.splitlines():
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(message, dict) and "id" in message:
            answers[message["id"]] = message
    return answers, run.stderr


def command_install(args):
    binary = Path(args.headless).resolve()
    if not binary.exists():
        fail(f"{binary} does not exist")
    machine = this_platform()
    catalogue = load()
    offers = [offer for offer in selected(catalogue, args.only)
              if machine in offer["downloads"] or "any" in offer["downloads"]]
    if not offers:
        print(f"nothing to install on {machine}")
        return
    summary = [f"### Installed through BATIQ on {machine}", "",
               "| Extension | Install | Setup |", "| --- | --- | --- |"]
    problems = []
    home = Path(tempfile.mkdtemp(prefix="batiq-check-"))
    try:
        answers, _ = headless_session(binary, home, [], 120)
        capabilities = answers.get(0, {}).get("result", {}).get("capabilities", {})
        can_setup = bool(capabilities.get("extensions.setup")) and not args.no_setup
        if not args.no_setup and not capabilities.get("extensions.setup"):
            print("note: this BATIQ has no extensions.setup; setup is not checked")
        for offer in offers:
            id = offer["id"]
            requests = [("extensions.install", {"id": id}), ("extensions.list", {})]
            if can_setup:
                requests.append(("extensions.setup", {"id": id}))
            print(f"installing {id} {offer['version']} through BATIQ", flush=True)
            answers, stderr = headless_session(binary, home, requests, args.timeout)
            installed = answers.get(1, {})
            if "result" not in installed or installed["result"].get("version") != offer["version"]:
                reason = installed.get("error", {}).get("message", stderr.strip()[-500:] or "no answer")
                problems.append(f"'{id}': install failed: {reason}")
                summary.append(f"| {id} {offer['version']} | failed: {reason} | |")
                continue
            listed = answers.get(2, {}).get("result", {}).get("extensions", [])
            if not any(entry.get("id") == id for entry in listed):
                problems.append(f"'{id}': installed but BATIQ does not list it")
            setup = "not checked"
            if can_setup:
                answer = answers.get(3, {})
                if "result" in answer:
                    setup = answer["result"].get("setup", {}).get("state", "?")
                    if setup not in ("ready", "none"):
                        problems.append(f"'{id}': setup ended '{setup}', not ready")
                else:
                    reason = answer.get("error", {}).get("message", "").strip()
                    setup = f"failed: {reason or 'no reason given'}"
                    if len(reason) < 20 or any(reason.startswith(bare) for bare in BARE_FAILURES):
                        problems.append(f"'{id}': setup failed without saying what to do: {reason!r}")
                    else:
                        print(f"note: '{id}' setup failed on this runner, with a reason: {reason}")
            summary.append(f"| {id} {offer['version']} | ok | {setup} |")
    finally:
        shutil.rmtree(home, ignore_errors=True)
    text = "\n".join(summary) + "\n"
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as file:
            file.write(text)
    report(problems, f"install on {machine}")


# ---------------------------------------------------------------- changed


def command_changed(args):
    older = {offer["id"]: offer for offer in load(args.older)["extensions"]} if Path(args.older).exists() else {}
    changed = [offer["id"] for offer in load()["extensions"] if older.get(offer["id"]) != offer]
    print(",".join(changed))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    set_parser = commands.add_parser("set", help="point an extension at its release")
    set_parser.add_argument("id")
    set_parser.add_argument("dist")
    set_parser.add_argument("--name")
    set_parser.add_argument("--tagline")
    set_parser.add_argument("--needs")
    set_parser.set_defaults(run=command_set)
    check_parser = commands.add_parser("check", help="download and check every zip")
    check_parser.add_argument("--only", default="")
    check_parser.set_defaults(run=command_check)
    install_parser = commands.add_parser("install", help="install through BATIQ and run setup")
    install_parser.add_argument("headless")
    install_parser.add_argument("--only", default="")
    install_parser.add_argument("--no-setup", action="store_true")
    install_parser.add_argument("--timeout", type=int, default=3600)
    install_parser.set_defaults(run=command_install)
    changed_parser = commands.add_parser("changed", help="ids whose entry changed")
    changed_parser.add_argument("older")
    changed_parser.set_defaults(run=command_changed)
    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
