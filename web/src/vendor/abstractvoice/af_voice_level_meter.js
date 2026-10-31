// dist/af_voice_level_meter.js
import { jsx as _jsx } from "react/jsx-runtime";
import { useEffect, useState } from "react";
function useVoiceLevel(source, channel = "microphone") {
  const [level, setLevel] = useState(0);
  const subscribe = channel === "playback" ? source?.subscribe_playback_level : source?.subscribe_level;
  useEffect(() => {
    if (!subscribe) {
      setLevel(0);
      return;
    }
    return subscribe((v) => setLevel(Math.min(1, Math.max(0, Number(v) || 0))));
  }, [subscribe]);
  return level;
}
function AfVoiceLevelMeter(p) {
  const live = useVoiceLevel(p.level === void 0 ? p.source : null, p.channel);
  const value = Math.min(1, Math.max(0, p.level === void 0 ? live : Number(p.level) || 0));
  const Tag = p.inline ? "span" : "div";
  return _jsx(Tag, { className: `af-voice-meter${p.className ? ` ${p.className}` : ""}`, "data-voice-meter": true, "data-voice-meter-source": p.origin || "live", role: "meter", "aria-label": p.label || (p.channel === "playback" ? "Playback level" : "Microphone level"), "aria-valuemin": 0, "aria-valuemax": 100, "aria-valuenow": Math.round(value * 100), children: _jsx("span", { className: "af-voice-meter__fill", style: { width: `${Math.round(value * 100)}%` } }) });
}
export {
  AfVoiceLevelMeter,
  useVoiceLevel
};
