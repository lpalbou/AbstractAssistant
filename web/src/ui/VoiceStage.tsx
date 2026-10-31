import { AfVoiceMicButton, Icon, type VoiceCaptureMode } from "@abstractframework/ui-kit";
import { useVoiceLevel } from "../vendor/abstractvoice/af_voice_level_meter.js";
import type { GatewayVoice } from "../vendor/abstractvoice/use_gateway_voice.js";
import type { AvatarPalette, AvatarPose } from "../vendor/abstractavatar/avatar_renderer.js";
import { useState } from "react";
import { AppAvatar } from "./AppAvatar";
import type { AssistantPreferences } from "./useAssistantPreferences";

/** The Watch's mint/lavender light, rendered by the shared TUI/web geometry. */
export const ORB_PALETTE: AvatarPalette = {
  background: [9, 11, 22, 0], warm: [107, 227, 204, 255], eye: [173, 166, 255, 255],
  shadow: [33, 27, 63, 255], highlight: [237, 242, 255, 255], muted: [90, 109, 146, 255],
};
const MACHINE_PALETTE: AvatarPalette = { ...ORB_PALETTE, warm: [237, 197, 106, 255], eye: [240, 137, 171, 255], shadow: [68, 45, 48, 255] };
const ERROR_PALETTE: AvatarPalette = { ...ORB_PALETTE, eye: [255, 77, 91, 255] };
const MACHINE_ERROR_PALETTE: AvatarPalette = { ...MACHINE_PALETTE, eye: [255, 77, 91, 255] };
export function avatarPalette(design: string, pose: AvatarPose): AvatarPalette {
  const machine = design === "hover" || design === "rover";
  return pose === "error" ? machine ? MACHINE_ERROR_PALETTE : ERROR_PALETTE : machine ? MACHINE_PALETTE : ORB_PALETTE;
}

function Orb(props: { voice: GatewayVoice; pose: AvatarPose; prefs: AssistantPreferences; onError: () => void }) {
  const microphone = useVoiceLevel(props.pose === "listening" ? props.voice : null);
  const playback = useVoiceLevel(props.pose === "speaking" ? props.voice : null, "playback");
  const level = props.pose === "listening" ? microphone : props.pose === "speaking" ? playback : 0;
  return <AppAvatar design={props.prefs.design} pose={props.pose} size={288} level={level}
    palette={avatarPalette(props.prefs.design, props.pose)} animated={props.prefs.animated} followCursor className="aa-orb" label={`Assistant · ${props.pose}`} onError={props.onError} />;
}

export function VoiceStage(props: {
  voice: GatewayVoice;
  presence: { pose: AvatarPose; label: string; hint: string };
  prefs: AssistantPreferences;
  readReplies: boolean;
  onReadRepliesChange: (value: boolean) => void;
  mode: VoiceCaptureMode;
  microphoneReason: string | null;
  busy: boolean;
  onTranscript: (text: string) => void;
  onPlayback: () => void;
  onStop: () => void;
  onType: () => void;
  onSettings: () => void;
  autoSend: boolean;
}) {
  const [unavailable, setUnavailable] = useState(false);
  const playing = ["playing", "paused", "loading"].includes(props.voice.tts_playback.status);
  const capture = !playing && !props.busy && !props.voice.voice_ptt_busy && !props.microphoneReason && props.voice.voice_ptt_supported;
  const action = playing ? props.voice.tts_playback.status === "paused" ? "Resume reply" : "Pause reply"
    : props.busy || props.voice.voice_ptt_busy ? "Stop" : "Write a message";
  return (
    <section className="aa-presence" data-pose={props.presence.pose} aria-label="Assistant voice">
      <div className="aa-presence__eyebrow"><span className="aa-presence__light" /> Your assistant</div>
      <div className={`aa-orb-control${capture ? " aa-orb-control--mic" : ""}`}>
        <Orb voice={props.voice} pose={props.presence.pose} prefs={props.prefs} onError={() => setUnavailable(true)} />
        <AfVoiceMicButton voice={props.voice} mode={props.mode} showStatus={false} className={`aa-orb-mic${capture ? "" : " is-hidden"}`}
          unavailableReason={capture ? null : "Use the current action on the orb."}
          label={props.mode === "hold" ? "Hold the orb to talk" : "Tap the orb to talk"} onTranscript={props.onTranscript} />
        {!capture && <button type="button" className="aa-orb-hit" aria-label={action}
            onClick={playing ? props.onPlayback : props.busy || props.voice.voice_ptt_busy ? props.onStop : props.onType} />}
      </div>
      <div className="aa-presence__words" aria-live="polite">
        <h2>{props.presence.label}</h2>
        <p>{props.voice.voice_ptt_recording
          ? props.mode === "hold" ? "Release to finish recording." : "Tap the orb again to finish."
          : capture ? props.mode === "hold" ? "Hold the orb to talk." : "Tap the orb to talk." : props.presence.hint}</p>
        {!props.busy && !playing && !props.voice.voice_ptt_busy && <span className="aa-presence__caption">{props.autoSend ? "What you say is sent automatically." : "Review your words before sending."}</span>}
      </div>
      <div className="aa-presence__actions" role="group" aria-label="Voice controls">
        <button type="button" className="aa-icon-button" onClick={props.onType} aria-label="Write a message" title="Write a message"><Icon name="edit" size={18} /></button>
        {props.voice.tts_supported && <button type="button" className={`aa-icon-button${props.readReplies ? " is-on" : ""}`}
          aria-pressed={props.readReplies} aria-label="Read new replies aloud" title="Read new replies aloud"
          onClick={() => { if (props.readReplies) props.voice.stop_tts(); props.onReadRepliesChange(!props.readReplies); }}><Icon name="speaker" size={18} /></button>}
        {playing && <button type="button" className="aa-icon-button" aria-label={props.voice.tts_playback.status === "paused" ? "Resume reply" : "Pause reply"}
          onClick={props.onPlayback}><Icon name={props.voice.tts_playback.status === "paused" ? "play" : "pause"} size={18} /></button>}
        {(props.busy || playing || props.voice.voice_ptt_recording || props.voice.voice_ptt_busy) && <button type="button" className="aa-icon-button" onClick={props.onStop} aria-label="Stop"><Icon name="stop" size={18} /></button>}
        <button type="button" className="aa-icon-button" onClick={props.onSettings} aria-label="Assistant settings" title="Assistant settings"><Icon name="settings" size={18} /></button>
      </div>
      {unavailable && <p className="aa-note" role="status">The avatar could not load. Voice and messages still work.</p>}
      {props.microphoneReason && <p className="aa-presence__caption">{props.microphoneReason}</p>}
    </section>
  );
}
