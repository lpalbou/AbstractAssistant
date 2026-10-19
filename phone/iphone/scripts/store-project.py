#!/usr/bin/env python3
"""Compose one Store product from the canonical iPhone and Watch projects.

Only generated files are changed. Developer projects retain their local bundle IDs.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import subprocess

STORE_ID = "ai.abstractframework.assistant"
WATCH_ID = STORE_ID + ".watch"


def validate_watch_package(package: dict) -> None:
    targets = [t for t in package["targets"] if t["type"] != "test"]
    if len(targets) != 1 or targets[0]["name"] != "AbstractGatewayClient":
        raise ValueError("Store composition requires one Watch client module")
    target = targets[0]
    if package.get("dependencies") or any(target.get(k) for k in
            ("dependencies", "resources", "settings", "exclude", "pluginUsages", "path", "sources")):
        raise ValueError("Watch package has custom build behavior: update Store composition before delivery")


def relocate(target: dict, base: Path, output: Path, label: str) -> dict:
    target = copy.deepcopy(target)
    if target.get("entitlements") or "CODE_SIGN_ENTITLEMENTS" in json.dumps(target.get("settings", {})):
        raise ValueError("Explicit entitlements require a signed Store archive configuration")
    original_info = target.get("info", {}).get("path")
    sources = []
    for value in target.get("sources", []):
        source = {"path": value} if isinstance(value, str) else copy.deepcopy(value)
        path = (base / source["path"]).resolve()
        source["path"] = str(path)
        if original_info:
            info = (base / original_info).resolve()
            if info.is_relative_to(path):
                source.setdefault("excludes", []).append(str(info.relative_to(path)))
        sources.append(source)
    target["sources"] = sources
    for kind in ("info", "entitlements"):
        if kind in target:
            target[kind]["path"] = str(output / (label + "." + kind + ".plist"))
    # These inputs need explicit relocation if either client adds them later.
    if any(target.get(k) for k in ("configFiles", "preBuildScripts", "postBuildScripts", "postCompileScripts", "buildRules")):
        raise ValueError("Custom target build inputs require explicit Store composition support")
    return target


def compose(phone: dict, watch: dict, root: Path, output: Path) -> tuple[dict, dict]:
    phone_base, watch_base = root / "phone/iphone", root / "watch/apple"
    p = copy.deepcopy(phone)
    p["name"] = "StorePhone"
    p["targets"] = {name: relocate(t, phone_base, output, name) for name, t in p["targets"].items()}
    for package in p.get("packages", {}).values():
        if "path" in package:
            package["path"] = str((phone_base / package["path"]).resolve())
    app = p["targets"]["AbstractAssistantPhone"]
    app["settings"]["base"]["PRODUCT_BUNDLE_IDENTIFIER"] = STORE_ID
    app.setdefault("dependencies", []).append({"target": "StoreWatch/AbstractAssistantWatch", "embed": True})
    p["projectReferences"] = {"StoreWatch": {"path": str(output / "StoreWatch.xcodeproj")}}

    w = {"name": "StoreWatch", "options": copy.deepcopy(watch["options"]),
         "settings": copy.deepcopy(watch["settings"]), "targets": {}}
    for key in ("MARKETING_VERSION", "CURRENT_PROJECT_VERSION"):
        w["settings"]["base"][key] = phone["settings"]["base"][key]
    target = relocate(watch["targets"]["AbstractAssistantWatch"], watch_base, output, "Watch")
    props = target["info"]["properties"]
    props.pop("WKWatchOnly", None)
    props.update(WKCompanionAppBundleIdentifier=STORE_ID, WKRunsIndependentlyOfCompanionApp=True)
    if target["settings"]["base"]["PRODUCT_BUNDLE_IDENTIFIER"] != WATCH_ID:
        raise ValueError("Watch identity must remain attached to the existing Store listing")
    if target["dependencies"] != [{"package": "AbstractGatewayClient"}]:
        raise ValueError("Watch target dependencies changed: update Store composition")
    target["dependencies"] = [{"target": "WatchGatewayClient", "embed": False}]
    w["targets"]["AbstractAssistantWatch"] = target
    # Avoid SwiftPM's duplicate-product collision while compiling the same Watch sources.
    w["targets"]["WatchGatewayClient"] = {
        "type": "framework", "platform": "watchOS", "productName": "AbstractGatewayClient",
        "sources": [str(watch_base / "Packages/AbstractGatewayClient/Sources/AbstractGatewayClient")],
        "settings": {"base": {"PRODUCT_BUNDLE_IDENTIFIER": WATCH_ID + ".client",
            "PRODUCT_MODULE_NAME": "AbstractGatewayClient", "MACH_O_TYPE": "staticlib",
            "SKIP_INSTALL": True, "GENERATE_INFOPLIST_FILE": True,
            "SWIFT_STRICT_CONCURRENCY": "complete"}}}
    return p, w


def generate(root: Path, output: Path) -> None:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    specs = [json.loads(subprocess.check_output(["xcodegen", "dump", "--spec", str(root / path), "--type", "json"]))
             for path in ("phone/iphone/project.yml", "watch/apple/project.yml")]
    package = json.loads(subprocess.check_output(["swift", "package", "--package-path",
        str(root / "watch/apple/Packages/AbstractGatewayClient"), "dump-package"]))
    validate_watch_package(package)
    phone, watch = compose(*specs, root, output)
    for spec in (watch, phone):
        path = output / (spec["name"] + ".json")
        path.write_text(json.dumps(spec, indent=2) + "\n")
        subprocess.run(["xcodegen", "generate", "--spec", str(path), "--project", str(output)], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generate(Path(__file__).resolve().parents[3], args.output)
