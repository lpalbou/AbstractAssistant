"""Bundle the optional installed AbstractAvatar native renderer with the desktop app."""

from PyInstaller.utils.hooks import collect_dynamic_libs

binaries = collect_dynamic_libs("abstractavatar")
