"""Signing and notarization of the macOS bundle (ADR 0006, docs/macos-signing.md).

Everything here is pure: the planners only build argument lists, so these tests run on any
platform (CI is Linux) and never sign, notarize or touch a keychain. What they hold:

- the unsigned local build is unchanged unless signing is asked for (no plan, no identity,
  no entitlements reach PyInstaller);
- a configuration that cannot work fails before PyInstaller runs, saying what to set;
- the commands are the ones notarization needs (hardened runtime, secure timestamp, the
  entitlements), in an order that leaves every artifact stapled;
- Gatekeeper's and notarytool's verdicts are read strictly, not by exit code alone.
"""

from __future__ import annotations

import ast
import plistlib
import re
from pathlib import Path

import pytest

pytest.importorskip("fcntl")

import abstractassistant.build_macos_app as build  # noqa: E402
from abstractassistant.build_macos_app import (  # noqa: E402
    NotaryAuth,
    ReleaseOptions,
    SigningError,
    check_assessment,
    check_team,
    check_nested_signature,
    mach_o_files,
    parse_notary_result,
    plan_release,
    resolve_identity,
    resolve_notary_auth,
    run_plan,
)

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "packaging" / "macos" / "AbstractAssistant.spec"
ENTITLEMENTS = ROOT / "packaging" / "macos" / "entitlements.plist"
DEV_ID = "Developer ID Application: Example Person (K3R4D6HP2A)"
KEY_ENV = {"ASC_KEY_ID": "ABCDE12345", "ASC_ISSUER_ID": "12345678-1234-1234-1234-123456789abc"}


def _spec_signing_function():
    """The spec's `_signing_from_env`, extracted and run on its own (the spec itself needs
    PyInstaller's globals to execute)."""
    tree = ast.parse(SPEC.read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_signing_from_env")
    namespace: dict = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SPEC), "exec"), namespace)
    return namespace["_signing_from_env"]


def _plan(**kwargs):
    defaults = dict(
        app=Path("/d/AbstractAssistant.app"), work_dir=Path("/w"), out_dir=Path("/d"),
        version="9.9.9", entitlements=ENTITLEMENTS,
    )
    defaults.update(kwargs)
    return plan_release(**defaults)


def _labels(steps):
    return [step.label for step in steps]


def _index(steps, prefix):
    return next(i for i, step in enumerate(steps) if step.label.startswith(prefix))


# --- identity: one bundle id, in both places -------------------------------------------------


@pytest.mark.basic
def test_the_bundle_id_is_the_families_and_the_spec_agrees() -> None:
    spec_id = re.search(r'^BUNDLE_ID = "([^"]+)"', SPEC.read_text(encoding="utf-8"), re.M).group(1)
    assert spec_id == build.BUNDLE_ID == "ai.abstractframework.assistant.mac"
    assert 'BUNDLE_ID = "ai.abstractcore' not in SPEC.read_text(encoding="utf-8")


# --- the default build stays unsigned --------------------------------------------------------


@pytest.mark.basic
def test_the_spec_signs_nothing_unless_an_identity_is_set(tmp_path) -> None:
    signing = _spec_signing_function()
    assert signing({}, tmp_path) == (None, None, {})
    # Entitlements alone mean nothing without a signature to carry them.
    assert signing({"ABSTRACTASSISTANT_ENTITLEMENTS": "/x.plist"}, tmp_path) == (None, None, {})
    assert signing({"ABSTRACTASSISTANT_CODESIGN_IDENTITY": "  "}, tmp_path) == (None, None, {})


@pytest.mark.basic
def test_the_spec_uses_the_identity_and_the_packaged_entitlements(tmp_path) -> None:
    signing = _spec_signing_function()
    strict = {"PYINSTALLER_STRICT_BUNDLE_CODESIGN_ERROR": "1"}
    assert signing({"ABSTRACTASSISTANT_CODESIGN_IDENTITY": DEV_ID}, tmp_path) == (DEV_ID, str(tmp_path / "entitlements.plist"), strict)
    env = {"ABSTRACTASSISTANT_CODESIGN_IDENTITY": DEV_ID, "ABSTRACTASSISTANT_ENTITLEMENTS": "/other.plist"}
    assert signing(env, tmp_path) == (DEV_ID, "/other.plist", strict)
    text = SPEC.read_text(encoding="utf-8")
    assert "codesign_identity=CODESIGN_IDENTITY" in text and "entitlements_file=ENTITLEMENTS_FILE" in text
    # The strict flag reaches PyInstaller before BUNDLE signs (it is read there).
    assert text.index("os.environ.update(SIGNING_ENV)") < text.index("app = BUNDLE(")


@pytest.mark.basic
def test_no_options_means_no_steps_after_pyinstaller() -> None:
    assert _plan() == []


@pytest.mark.basic
def test_the_default_cli_builds_unsigned(monkeypatch) -> None:
    seen = {}

    def _fake_build(*, install_to_applications, release):
        seen.update(install=install_to_applications, release=release)
        return Path("/d/AbstractAssistant.app")

    monkeypatch.setattr(build, "build_macos_app", _fake_build)
    assert build.main(["--skip-install"]) == 0
    assert seen == {"install": False, "release": ReleaseOptions()}


# --- the entitlements ------------------------------------------------------------------------


@pytest.mark.basic
def test_the_entitlements_are_exactly_the_ones_the_adr_lists() -> None:
    entitlements = plistlib.loads(ENTITLEMENTS.read_bytes())
    assert entitlements == {
        "com.apple.security.cs.allow-unsigned-executable-memory": True,
        "com.apple.security.device.audio-input": True,
    }
    # Notarization refuses get-task-allow; a sandbox key would make this a different app.
    assert "com.apple.security.get-task-allow" not in entitlements
    assert "com.apple.security.app-sandbox" not in entitlements


@pytest.mark.basic
def test_the_microphone_entitlement_has_its_usage_string() -> None:
    assert "NSMicrophoneUsageDescription" in SPEC.read_text(encoding="utf-8")


# --- configuration fails before the build ----------------------------------------------------


@pytest.mark.basic
def test_signing_without_an_identity_names_the_variable() -> None:
    with pytest.raises(SigningError, match="ABSTRACTASSISTANT_CODESIGN_IDENTITY"):
        resolve_identity({})


@pytest.mark.basic
@pytest.mark.parametrize(
    "identity",
    ["-", "Apple Development: Someone (AAAAAAAAAA)", "Apple Distribution: Org (K3R4D6HP2A)", "Mac Developer: X (B)"],
)
def test_identities_gatekeeper_rejects_are_refused(identity) -> None:
    with pytest.raises(SigningError):
        resolve_identity({}, identity)


@pytest.mark.basic
def test_a_local_test_accepts_a_development_identity_and_nothing_weaker() -> None:
    dev = "Apple Development: Someone (AAK63XPX58)"
    # The parenthetical of a development name is the person, not the team: TEAM_ID is checked
    # on the signed app instead, so it must not refuse here.
    assert resolve_identity({"TEAM_ID": "K3R4D6HP2A"}, dev, local_test=True) == dev
    assert resolve_identity({}, DEV_ID, local_test=True) == DEV_ID
    for refused in ("-", "Apple Distribution: Org (K3R4D6HP2A)", "3rd Party Mac Developer Application: X"):
        with pytest.raises(SigningError):
            resolve_identity({}, refused, local_test=True)


@pytest.mark.basic
def test_a_local_test_signs_verifies_and_never_notarizes() -> None:
    steps = _plan(identity="Apple Development: Someone (AAK63XPX58)", local_test=True, team_id="K3R4D6HP2A")
    kinds = [s.kind for s in steps]
    assert "nested" in kinds and kinds[-2:] == ["note", "note"]
    assert not any(s.argv and s.argv[0] in ("spctl", "ditto", "hdiutil") or "notarytool" in s.argv for s in steps)
    assert "Contents/MacOS/AbstractAssistant" in steps[-1].label
    for bad in (dict(notary=NotaryAuth(profile="p")), dict(dmg=True)):
        with pytest.raises(SigningError):
            _plan(identity=DEV_ID, local_test=True, **bad)


@pytest.mark.basic
def test_the_identity_must_belong_to_team_id_when_both_are_known() -> None:
    assert resolve_identity({"ABSTRACTASSISTANT_CODESIGN_IDENTITY": DEV_ID, "TEAM_ID": "K3R4D6HP2A"}) == DEV_ID
    with pytest.raises(SigningError, match="team"):
        resolve_identity({"TEAM_ID": "ZZZZZZZZZZ"}, DEV_ID)
    # A SHA-1 identity names no team; TEAM_ID is then checked on the signed app instead.
    assert resolve_identity({"TEAM_ID": "K3R4D6HP2A"}, "A" * 40) == "A" * 40


@pytest.mark.basic
def test_notarizing_without_credentials_names_both_ways() -> None:
    with pytest.raises(SigningError) as excinfo:
        resolve_notary_auth({})
    message = str(excinfo.value)
    assert "store-credentials" in message and "ASC_KEY_ID" in message and "ASC_KEY_P8" in message


@pytest.mark.basic
def test_an_incomplete_or_ambiguous_api_key_is_refused(tmp_path) -> None:
    with pytest.raises(SigningError, match="incomplete"):
        resolve_notary_auth({"ASC_KEY_ID": "ABCDE12345"})
    with pytest.raises(SigningError, match="set one"):
        resolve_notary_auth({**KEY_ENV, "ASC_KEY_P8": "k"}, "profile")
    with pytest.raises(SigningError, match="not both"):
        key = tmp_path / "k.p8"
        key.write_text("k")
        resolve_notary_auth({**KEY_ENV, "ASC_KEY_P8": "k", "ASC_KEY_PATH": str(key)})
    with pytest.raises(SigningError, match="key id"):
        resolve_notary_auth({**KEY_ENV, "ASC_KEY_ID": "short", "ASC_KEY_P8": "k"})
    with pytest.raises(SigningError, match="issuer"):
        resolve_notary_auth({**KEY_ENV, "ASC_ISSUER_ID": "nope", "ASC_KEY_P8": "k"})
    with pytest.raises(SigningError, match="does not name a file"):
        resolve_notary_auth({**KEY_ENV, "ASC_KEY_PATH": str(tmp_path / "missing.p8")})


@pytest.mark.basic
def test_notary_credentials_resolve_to_notarytool_arguments(tmp_path) -> None:
    assert resolve_notary_auth({"ABSTRACTASSISTANT_NOTARY_PROFILE": "aa"}).args() == ["--keychain-profile", "aa"]
    key = tmp_path / "AuthKey.p8"
    key.write_text("k")
    auth = resolve_notary_auth({**KEY_ENV, "ASC_KEY_PATH": str(key)})
    assert auth.args() == ["--key", str(key), "--key-id", "ABCDE12345", "--issuer", KEY_ENV["ASC_ISSUER_ID"]]
    # The key text never appears in a printed command.
    secret = resolve_notary_auth({**KEY_ENV, "ASC_KEY_P8": "-----BEGIN PRIVATE KEY-----SECRET"})
    assert "SECRET" not in " ".join(secret.args()) and "SECRET" not in repr(secret)


@pytest.mark.basic
def test_the_cli_refuses_a_bad_configuration_before_building(monkeypatch, capsys) -> None:
    for name in ("ABSTRACTASSISTANT_CODESIGN_IDENTITY", "ABSTRACTASSISTANT_NOTARY_PROFILE", "ASC_KEY_ID", "ASC_ISSUER_ID", "ASC_KEY_P8", "ASC_KEY_PATH"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(build, "_build_locked", lambda *a, **k: pytest.fail("PyInstaller must not run"))
    monkeypatch.setattr(build, "_require_voice_io", lambda: None)
    assert build.main(["--sign", "--skip-install"]) == 2
    assert "ABSTRACTASSISTANT_CODESIGN_IDENTITY" in capsys.readouterr().err
    assert build.main(["--notarize", "--identity", DEV_ID, "--skip-install"]) == 2
    assert "store-credentials" in capsys.readouterr().err


@pytest.mark.basic
def test_a_dry_run_prints_every_command_and_runs_none(monkeypatch, capsys) -> None:
    monkeypatch.setenv("ABSTRACTASSISTANT_NOTARY_PROFILE", "aa-notary")
    monkeypatch.setattr(build, "_build_locked", lambda *a, **k: pytest.fail("PyInstaller must not run"))
    monkeypatch.setattr(build.subprocess, "run", lambda *a, **k: pytest.fail("nothing may run"))
    assert build.main(["--notarize", "--dmg", "--identity", DEV_ID, "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert out.rstrip().splitlines()[-1].startswith("dry run: would build "), "a dry run never claims a built app"
    for fragment in ("pyinstaller", "codesign --verify --deep --strict", "<each Mach-O file in the app>", "notarytool submit",
                     "stapler staple", "spctl --assess", "hdiutil create", "/Applications"):
        assert fragment in out, fragment


# --- the commands and their order ------------------------------------------------------------


@pytest.mark.basic
def test_signing_is_inside_out_with_no_deep_reseal() -> None:
    """PyInstaller signs every binary, then the bundle. A second `codesign --force --deep`
    would replace every nested signature (deprecated for signing since macOS 13)."""
    for steps in (_plan(identity=DEV_ID), _plan(identity=DEV_ID, notary=NotaryAuth(profile="p"), dmg=True)):
        for step in steps:
            if step.argv[:1] == ("codesign",) and "--sign" in step.argv:
                assert "--deep" not in step.argv, step.label
                assert step.argv[-1].endswith(".dmg"), "only the disk image is signed here"


@pytest.mark.basic
def test_sign_only_verifies_checks_every_binary_and_assesses() -> None:
    steps = _plan(identity=DEV_ID)
    assert [s.kind for s in steps] == ["run", "run", "run", "nested", "assess-app"]
    assert ("--verify", "--deep", "--strict") == steps[0].argv[1:4]
    assert steps[3].target == "/d/AbstractAssistant.app"
    assert not any("notarytool" in s.argv for s in steps)


@pytest.mark.basic
def test_notarize_staples_before_assessing_and_ships_a_stapled_zip() -> None:
    steps = _plan(identity=DEV_ID, notary=NotaryAuth(profile="p"))
    submit = _index(steps, "notarize the app")
    staple = _index(steps, "staple the ticket to the app")
    assess = _index(steps, "Gatekeeper assessment of the app")
    final_zip = _index(steps, "zip the stapled app")
    assert _index(steps, "check every nested binary") < _index(steps, "zip the app for the notary") < submit < staple < assess < final_zip
    assert steps[submit].kind == "notarize" and "--wait" in steps[submit].argv
    assert steps[final_zip].argv[-1] == "/d/AbstractAssistant-9.9.9.zip"


@pytest.mark.basic
def test_a_notarized_disk_image_holds_the_stapled_app_and_is_stapled_itself() -> None:
    steps = _plan(identity=DEV_ID, notary=NotaryAuth(profile="p"), dmg=True)
    labels = _labels(steps)
    assert _index(steps, "staple the ticket to the app") < _index(steps, "stage the app") < _index(steps, "build the disk image")
    assert _index(steps, "build the disk image") < _index(steps, "sign the disk image") < _index(steps, "notarize the disk image")
    assert _index(steps, "notarize the disk image") < _index(steps, "staple the ticket to the disk image")
    assert labels[-1] == "Gatekeeper assessment of the disk image"
    assert not any(label.startswith("zip the stapled app") for label in labels), "the image is the download"
    clear = steps[_index(steps, "clear the disk image")]
    assert clear.argv == ("rm", "-rf", "/w/dmg-root"), "only the build folder's staging area is removed"


@pytest.mark.basic
def test_an_unsigned_disk_image_is_just_an_image() -> None:
    steps = _plan(dmg=True)
    assert [s.argv[0] for s in steps] == ["rm", "ditto", "ln", "hdiutil"]


@pytest.mark.basic
def test_notarizing_an_unsigned_app_is_refused() -> None:
    with pytest.raises(SigningError):
        _plan(notary=NotaryAuth(profile="p"))


@pytest.mark.basic
def test_team_id_adds_a_check_of_the_signed_app() -> None:
    steps = _plan(identity=DEV_ID, team_id="K3R4D6HP2A")
    assert steps[_index(steps, "show the signature")].kind == "team"
    check_team("Identifier=x\nTeamIdentifier=K3R4D6HP2A\n", "K3R4D6HP2A")
    with pytest.raises(SigningError, match="ZZZ"):
        check_team("TeamIdentifier=ZZZ\n", "K3R4D6HP2A")


# --- verdicts are read, not assumed ----------------------------------------------------------


@pytest.mark.basic
def test_gatekeeper_verdicts() -> None:
    check_assessment(0, "x.app: accepted\nsource=Notarized Developer ID", notarized=True)
    check_assessment(3, "x.app: rejected\nsource=Unnotarized Developer ID", notarized=False)
    with pytest.raises(SigningError):
        check_assessment(3, "x.app: rejected\nsource=Unnotarized Developer ID", notarized=True)
    with pytest.raises(SigningError):
        check_assessment(3, "x.app: rejected\nsource=no usable signature", notarized=False)
    with pytest.raises(SigningError):
        check_assessment(0, "", notarized=True)


@pytest.mark.basic
def test_notary_verdicts() -> None:
    assert parse_notary_result('{"id": "abc", "status": "Accepted", "message": "ok"}')["id"] == "abc"
    with pytest.raises(SigningError, match="Invalid.*abc"):
        parse_notary_result('{"id": "abc", "status": "Invalid", "message": "Processing complete"}')
    with pytest.raises(SigningError, match="no readable result"):
        parse_notary_result("Error: HTTP status code: 401")


class _Result:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


GOOD_NESTED = "CodeDirectory v=20500 flags=0x10000(runtime) hashes=1\nTimestamp=Oct 26, 2026\nTeamIdentifier=K3R4D6HP2A\n"


def _bundle(tmp_path) -> Path:
    """A bundle holding one Mach-O header and one plain file."""
    app = tmp_path / "AbstractAssistant.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "MacOS" / "AbstractAssistant").write_bytes(bytes.fromhex("cffaedfe") + b"\0" * 28)
    (app / "Contents" / "Info.plist").write_text("<plist/>")
    return app


def _answer(argv, default=None, **_):
    """codesign -dv of a nested file answers like a good signature; the rest succeed."""
    if argv[:3] == ["codesign", "--display", "--verbose=2"]:
        return _Result(0, "", GOOD_NESTED)
    return default or _Result()


@pytest.mark.basic
def test_mach_o_files_are_found_by_magic_number(tmp_path) -> None:
    app = _bundle(tmp_path)
    (app / "Contents" / "MacOS" / "link").symlink_to(app / "Contents" / "MacOS" / "AbstractAssistant")
    assert mach_o_files(app) == [app / "Contents" / "MacOS" / "AbstractAssistant"]


@pytest.mark.basic
def test_nested_signature_verdicts() -> None:
    assert check_nested_signature(GOOD_NESTED, team_id="K3R4D6HP2A") is None
    assert check_nested_signature("flags=0x0(none)\nTimestamp=x") == "no hardened runtime"
    assert check_nested_signature("flags=0x10002(adhoc,runtime)\n") == "ad-hoc signature"
    assert check_nested_signature("flags=0x10000(runtime)\nSigned Time=x") == "no secure timestamp"
    assert "ZZZ" in check_nested_signature("flags=0x10000(runtime)\nTimestamp=x\nTeamIdentifier=ZZZ", team_id="K3R4D6HP2A")


@pytest.mark.basic
def test_one_wrong_nested_binary_fails_the_build(tmp_path) -> None:
    app = _bundle(tmp_path)
    (app / "Contents" / "MacOS" / "helper.so").write_bytes(bytes.fromhex("cffaedfe") + b"\0" * 28)

    def _runner(argv, **_):
        if argv[:3] == ["codesign", "--display", "--verbose=2"] and argv[-1].endswith("helper.so"):
            return _Result(0, "", "flags=0x2(adhoc)\n")
        return _answer(argv)

    with pytest.raises(SigningError, match="helper.so: no hardened runtime"):
        run_plan(_plan(app=app, identity=DEV_ID), runner=_runner)


@pytest.mark.basic
def test_a_bundle_with_no_binaries_is_not_a_pass(tmp_path) -> None:
    app = tmp_path / "Empty.app"
    (app / "Contents").mkdir(parents=True)
    with pytest.raises(SigningError, match="no Mach-O file"):
        run_plan(_plan(app=app, identity=DEV_ID), runner=_answer)


@pytest.mark.basic
def test_the_runner_stops_at_the_first_failure_with_the_tools_output(capsys) -> None:
    calls = []

    def _runner(argv, **_):
        calls.append(argv)
        return _Result(1, "", "a sealed resource is missing or invalid") if len(calls) == 1 else _Result()

    with pytest.raises(SigningError, match="sealed resource"):
        run_plan(_plan(identity=DEV_ID), runner=_runner)
    assert len(calls) == 1
    assert "$ codesign --verify --deep --strict" in capsys.readouterr().out


@pytest.mark.basic
def test_an_invalid_notarization_fails_even_when_notarytool_exits_zero(tmp_path) -> None:
    auth = NotaryAuth(profile="p")

    def _runner(argv, **_):
        if "notarytool" in argv:
            return _Result(0, '{"id": "sub-1", "status": "Invalid", "message": "Processing complete"}')
        return _answer(argv)

    with pytest.raises(SigningError) as excinfo:
        run_plan(_plan(app=_bundle(tmp_path), identity=DEV_ID, notary=auth), notary=auth, runner=_runner)
    assert "sub-1" in str(excinfo.value) and "notarytool log" in str(excinfo.value)


@pytest.mark.basic
def test_the_p8_key_exists_only_while_the_plan_runs(tmp_path) -> None:
    auth = NotaryAuth(key_id="ABCDE12345", issuer_id=KEY_ENV["ASC_ISSUER_ID"], key_text="-----KEY-----")
    seen = {}

    def _runner(argv, **_):
        if "notarytool" in argv:
            path = Path(argv[argv.index("--key") + 1])
            seen["path"], seen["text"], seen["mode"] = path, path.read_text(), path.stat().st_mode & 0o777
            return _Result(0, '{"id": "s", "status": "Accepted"}')
        if argv[0] == "spctl":
            return _Result(0, "accepted\nsource=Notarized Developer ID")
        return _answer(argv)

    run_plan(_plan(app=_bundle(tmp_path), identity=DEV_ID, notary=auth), notary=auth, runner=_runner)
    assert seen["text"].strip() == "-----KEY-----" and seen["mode"] == 0o600
    assert not seen["path"].exists() and not seen["path"].parent.exists()


@pytest.mark.basic
def test_a_missing_hook_distribution_is_refused_before_pyinstaller(monkeypatch) -> None:
    """Measured 2026-10-26: an environment with the old `webrtcvad` instead of
    `webrtcvad-wheels` died 7 min into PyInstaller's analysis."""
    import importlib.metadata as metadata

    def _missing(name):
        raise metadata.PackageNotFoundError(name)

    monkeypatch.setattr(metadata, "distribution", _missing)
    with pytest.raises(RuntimeError, match="webrtcvad-wheels"):
        build._require_hook_metadata()


@pytest.mark.basic
def test_notary_json_is_read_whole_or_from_its_last_line() -> None:
    assert parse_notary_result('{\n  "id": "a",\n  "status": "Accepted"\n}')["id"] == "a"
    assert parse_notary_result('Conducting pre-submission checks...\n{"id": "b", "status": "Accepted"}')["id"] == "b"


@pytest.mark.basic
def test_a_notarytool_error_keeps_what_it_said(tmp_path) -> None:
    auth = NotaryAuth(profile="p")

    def _runner(argv, **_):
        if "notarytool" in argv:
            return _Result(69, "", "Error: HTTP status code: 401. Unable to authenticate.")
        return _answer(argv)

    with pytest.raises(SigningError, match="401"):
        run_plan(_plan(app=_bundle(tmp_path), identity=DEV_ID, notary=auth), notary=auth, runner=_runner)


@pytest.mark.basic
def test_a_signed_build_forces_strict_bundle_signing(tmp_path, monkeypatch) -> None:
    """PyInstaller only warns when sealing the bundle fails unless this is set."""
    monkeypatch.delenv("PYINSTALLER_STRICT_BUNDLE_CODESIGN_ERROR", raising=False)
    seen = {}
    monkeypatch.setattr(build, "_ensure_icon_assets", lambda root: None)
    monkeypatch.setattr(build, "_sync_shared_themes", lambda root: None)

    def _fake_pyinstaller(spec, dist, work):
        seen["strict"] = build.os.environ.get("PYINSTALLER_STRICT_BUNDLE_CODESIGN_ERROR")
        seen["identity"] = build.os.environ.get("ABSTRACTASSISTANT_CODESIGN_IDENTITY")
        raise RuntimeError("stop after PyInstaller")

    monkeypatch.setattr(build, "_pyinstaller_run", _fake_pyinstaller)
    monkeypatch.setattr(build, "_dist_dir", lambda root: tmp_path / "dist")
    monkeypatch.setattr(build, "_build_dir", lambda root: tmp_path / "build")
    monkeypatch.setenv("ABSTRACTASSISTANT_CODESIGN_IDENTITY", "")
    with pytest.raises(RuntimeError, match="stop after PyInstaller"):
        build._build_locked(ROOT, install_to_applications=False, identity=DEV_ID)
    assert seen == {"strict": "1", "identity": DEV_ID}
