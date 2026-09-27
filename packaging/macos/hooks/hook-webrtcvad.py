# The `webrtcvad` module is installed by the `webrtcvad-wheels` distribution
# (abstractvoice[audio-io] requires it), not by `webrtcvad`. PyInstaller's
# contrib hook copies the metadata of `webrtcvad`, which does not exist in such
# an environment, so the build stops. This hook (on the spec's hookspath, which
# takes precedence over the contrib hooks) copies the distribution that is
# actually installed; a missing `webrtcvad-wheels` fails the build loudly.
from PyInstaller.utils.hooks import copy_metadata

datas = copy_metadata("webrtcvad-wheels")
