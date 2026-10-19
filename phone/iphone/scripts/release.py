#!/usr/bin/env python3
"""Create and verify iPhone release candidates without Apple credentials."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import tarfile

BUNDLE_ID = "ai.abstractframework.assistant"
WATCH_BUNDLE_ID = BUNDLE_ID + ".watch"
ARCHIVE_NAME = "AbstractAssistantPhone.xcarchive"


def validate_version(version: str, build: str) -> None:
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Marketing version must contain three numeric components")
    if not re.fullmatch(r"[1-9]\d{0,3}(?:\.\d{1,2}){0,2}", build):
        raise ValueError("Build number exceeds Apple's numeric component limits")


def metadata(project: Path, run_number: int, attempt: int) -> dict:
    versions = re.findall(r'^\s*MARKETING_VERSION:\s*"?([\d.]+)"?\s*$', project.read_text(), re.M)
    if len(versions) != 1 or run_number < 1 or not 1 <= attempt <= 99:
        raise ValueError("One marketing version and positive CI run/attempt are required")
    result = {"version": versions[0], "build": f"{100 + run_number}.{attempt}"}
    validate_version(**result)
    return result


def inspect_archive(archive: Path, version: str, build: str) -> dict:
    validate_version(version, build)
    app = archive / "Products/Applications/AbstractAssistantPhone.app"
    expected = {"CFBundleIdentifier": BUNDLE_ID, "CFBundleShortVersionString": version,
                "CFBundleVersion": build, "DTPlatformName": "iphoneos"}
    watch = app / "Watch/AbstractAssistantWatch.app"
    for bundle, identity, platform, supported in ((app, BUNDLE_ID, "iphoneos", "iPhoneOS"),
            (watch, WATCH_BUNDLE_ID, "watchos", "WatchOS")):
        if not (bundle / "Info.plist").is_file():
            raise ValueError("Combined candidate must include the iPhone and Watch apps")
        details = plistlib.loads((bundle / "Info.plist").read_bytes())
        for key, value in {**expected, "CFBundleIdentifier": identity, "DTPlatformName": platform}.items():
            if details.get(key) != value:
                raise ValueError(f"Archive {bundle.name} {key} differs from candidate: {details.get(key)!r}")
        if supported not in details.get("CFBundleSupportedPlatforms", []):
            raise ValueError("Candidate must contain device applications")
        executable = details.get("CFBundleExecutable")
        if not isinstance(executable, str) or Path(executable).name != executable or executable in {".", ".."}:
            raise ValueError("Candidate executable name is invalid")
        if not (bundle / executable).is_file():
            raise ValueError("Candidate executable is missing")
        if bundle == watch and (details.get("WKWatchOnly") is True or
                details.get("WKCompanionAppBundleIdentifier") != BUNDLE_ID or
                details.get("WKRunsIndependentlyOfCompanionApp") is not True or
                details.get("WKApplication") is not True):
            raise ValueError("Watch must be an independent companion of the Store iPhone app")
    applications = list((archive / "Products/Applications").glob("*.app"))
    if applications != [app]:
        raise ValueError("Store archive must contain exactly one top-level iPhone app")
    if list(app.rglob("*.xctest")):
        raise ValueError("Test plugins cannot be distributed")
    return expected


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def candidate(archive: Path, output: Path, sha: str, version: str, build: str, test_suite: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("A full Git commit SHA is required")
    inspect_archive(archive, version, build)
    output.mkdir(parents=True, exist_ok=True)
    compressed = output / "candidate.tar.gz"
    with tarfile.open(compressed, "w:gz") as target:
        target.add(archive, arcname=ARCHIVE_NAME)
    manifest = {"schema": 2, "source_sha": sha, "bundle_id": BUNDLE_ID, "watch_bundle_id": WATCH_BUNDLE_ID,
                "version": version, "build": build, "native_test_suite": test_suite, "archive_sha256": digest(compressed)}
    (output / "candidate.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def verify(folder: Path, destination: Path, sha: str) -> dict:
    manifest = json.loads((folder / "candidate.json").read_text())
    if (manifest.get("schema") != 2 or manifest.get("source_sha") != sha or
            manifest.get("bundle_id") != BUNDLE_ID or manifest.get("watch_bundle_id") != WATCH_BUNDLE_ID):
        raise ValueError("Candidate identity/source does not match this workflow")
    validate_version(manifest["version"], manifest["build"])
    if manifest.get("native_test_suite") != "full":
        raise ValueError("Upload requires a candidate validated by the full native suite")
    compressed = folder / "candidate.tar.gz"
    if digest(compressed) != manifest.get("archive_sha256"):
        raise ValueError("Candidate archive digest mismatch")
    if destination.exists():
        raise ValueError("Extraction destination must be new")
    with tarfile.open(compressed, "r:gz") as source:
        members = source.getmembers()
        if not members or any(m.name.split("/")[0] != ARCHIVE_NAME or ".." in Path(m.name).parts for m in members):
            raise ValueError("Unexpected candidate archive root")
        # Python3.12's data filter rejects traversal, external links and special files.
        source.extractall(destination, filter="data")
    inspect_archive(destination / ARCHIVE_NAME, manifest["version"], manifest["build"])
    return manifest


def validate_settings(path: Path) -> None:
    for target in json.loads(path.read_text()):
        if target.get("buildSettings", {}).get("CODE_SIGN_ENTITLEMENTS", "").strip():
            raise ValueError("Explicit entitlements require signing the archive; unsigned candidate creation is disabled")


def export_options(path: Path, team: str) -> None:
    if not re.fullmatch(r"[A-Z0-9]{10}", team):
        raise ValueError("A valid Apple team identifier is required")
    path.write_bytes(plistlib.dumps({"method": "app-store-connect", "destination": "upload",
        "teamID": team, "signingStyle": "automatic", "manageAppVersionAndBuildNumber": False,
        "uploadSymbols": True, "testFlightInternalTestingOnly": False}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    meta = sub.add_parser("metadata"); meta.add_argument("--project", type=Path, required=True)
    meta.add_argument("--run-number", type=int, required=True); meta.add_argument("--attempt", type=int, required=True)
    create = sub.add_parser("candidate"); create.add_argument("--archive", type=Path, required=True)
    create.add_argument("--output", type=Path, required=True); create.add_argument("--sha", required=True)
    create.add_argument("--version", required=True); create.add_argument("--build", required=True)
    create.add_argument("--test-suite", choices=["critical", "full"], required=True)
    inspect = sub.add_parser("inspect"); inspect.add_argument("--archive", type=Path, required=True)
    inspect.add_argument("--version", required=True); inspect.add_argument("--build", required=True)
    check = sub.add_parser("verify"); check.add_argument("--folder", type=Path, required=True)
    check.add_argument("--destination", type=Path, required=True); check.add_argument("--sha", required=True)
    settings = sub.add_parser("settings"); settings.add_argument("path", type=Path)
    export = sub.add_parser("export-options"); export.add_argument("path", type=Path); export.add_argument("--team", required=True)
    args = vars(parser.parse_args()); command = args.pop("command")
    if command == "metadata":
        result = metadata(**args)
        if output := os.environ.get("GITHUB_OUTPUT"):
            with open(output, "a") as stream:
                for key, value in result.items(): stream.write(f"{key}={value}\n")
    elif command == "candidate": result = candidate(**args)
    elif command == "inspect": result = inspect_archive(**args)
    elif command == "verify": result = verify(**args)
    elif command == "settings": validate_settings(**args); result = {"unsigned_archive_allowed": True}
    else: export_options(**args); result = {"options": str(args["path"])}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
