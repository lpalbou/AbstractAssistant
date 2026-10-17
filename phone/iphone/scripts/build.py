#!/usr/bin/env python3
"""One low-priority iPhone build; yield to other Xcode builds (Watch has priority)."""
import argparse
from pathlib import Path
import os
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def other_builds(own=None, idle_watch_test=None):
    rows = subprocess.check_output(["ps", "-axo", "pid=,%cpu=,comm=,args="], text=True).splitlines()
    busy = []
    for row in rows:
        parts = row.split(maxsplit=3)
        if len(parts) < 4:
            continue
        pid, cpu, arguments = int(parts[0]), float(parts[1]), parts[3]
        # Darwin truncates the comm column when args is also requested. argv[0] keeps
        # the full executable path (the Xcode command paths here contain no spaces).
        executable = Path(arguments.split(maxsplit=1)[0]).name
        allowed_idle_test = (pid == idle_watch_test and executable == "xcodebuild" and cpu < 1.0
                             and "AbstractAssistantWatchUITests" in arguments and "platform=watchOS Simulator" in arguments and " test " in (" " + arguments + " "))
        if allowed_idle_test:
            continue
        if idle_watch_test and "AbstractAssistantWatch" in executable and cpu > 3:
            busy.append(pid)
        if (executable == "xcodebuild" and pid != own) or (executable in {"swift-frontend", "clang"} and "/watch/apple/" in arguments):
            busy.append(pid)
    if idle_watch_test:
        pressure = subprocess.run(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"], capture_output=True, text=True)
        if pressure.returncode == 0 and pressure.stdout.strip() in {"2", "4"}:
            busy.append(-1)
    return busy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--ui-test", metavar="SIMULATOR_ID", help="Run tests on this iPhone simulator")
    mode.add_argument("--device", metavar="DEVICE_ID", help="Build for this physical iPhone")
    parser.add_argument("--only-testing", action="append", default=[], metavar="TARGET/CLASS/TEST", help="Run only the named native test (with --ui-test)")
    parser.add_argument("--allow-idle-watch-test", type=int, metavar="PID", help="Allow only this idle Watch UI-test process; yield to Watch activity or memory pressure")
    parser.add_argument("--team", help="Apple development team ID (required with --device)")
    options = parser.parse_args()
    if bool(options.device) != bool(options.team):
        parser.error("--device and --team must be supplied together")
    if other_builds(idle_watch_test=options.allow_idle_watch_test):
        print("Another Xcode build is active. Leaving it priority; iPhone build skipped.", flush=True)
        return 75
    subprocess.run(["xcodegen", "generate", "--spec", "project.yml"], cwd=ROOT, check=True)
    log = ROOT / "build" / ("device-build.log" if options.device else "build.log")
    log.parent.mkdir(exist_ok=True)
    testing = bool(options.ui_test)
    scheme = "AbstractAssistantPhoneUITests" if testing else "AbstractAssistantPhone"
    destination = ("platform=iOS,id=" + options.device if options.device else
                   "platform=iOS Simulator,id=" + options.ui_test if testing else "generic/platform=iOS Simulator")
    derived = ROOT / "build" / ("DeviceDerivedData" if options.device else "DerivedData")
    args = ["nice", "-n", "10", "xcodebuild", "-project", "AbstractAssistantPhone.xcodeproj", "-scheme", scheme,
            "-destination", destination, "-derivedDataPath", str(derived),
            "-jobs", "1", "test" if testing else "build", "CODE_SIGNING_ALLOWED=YES", "ARCHS=arm64", "ONLY_ACTIVE_ARCH=YES", "-quiet"]
    if options.device:
        args += ["-allowProvisioningUpdates", "-allowProvisioningDeviceRegistration", "CODE_SIGN_STYLE=Automatic", "DEVELOPMENT_TEAM=" + options.team]
    else:
        args += ["CODE_SIGN_IDENTITY=-"]
    if testing:
        args += ["-collect-test-diagnostics", "never", "-parallel-testing-enabled", "NO", "-maximum-concurrent-test-simulator-destinations", "1",
                 "-resultBundlePath", str(ROOT / "build" / ("UITests-" + str(time.time_ns()) + ".xcresult"))]
    if options.only_testing and not testing:
        parser.error("--only-testing requires --ui-test")
    args += ["-only-testing:" + value for value in options.only_testing]
    print("iPhone only, one job, isolated DerivedData. " + ("Testing only on the named iPhone simulator." if testing else "No simulator will be booted."), flush=True)
    with log.open("w") as out:
        process = subprocess.Popen(args, cwd=ROOT, stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            while process.poll() is None:
                if other_builds(process.pid, idle_watch_test=options.allow_idle_watch_test):
                    print("Another Xcode build started. Stopping only our iPhone build to give it priority.", flush=True)
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=20)
                    return 75
                time.sleep(2)
        except BaseException:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
            raise
    print(log.read_text()[-14000:], flush=True)
    if process.returncode == 0:
        platform = "iphoneos" if options.device else "iphonesimulator"
        print("Built: " + str(derived / "Build" / "Products" / ("Debug-" + platform) / "AbstractAssistantPhone.app"), flush=True)
    return process.returncode


if __name__ == "__main__":
    sys.exit(main())
