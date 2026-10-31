import { avatarDesigns, type AvatarDesign, type AvatarPose } from "../vendor/abstractavatar/avatar_renderer.js";
import { useEffect, useState } from "react";
import { AppAvatar } from "./AppAvatar";
import { avatarPalette } from "./VoiceStage";
import type { AssistantPreferences } from "./useAssistantPreferences";

const POSES: AvatarPose[] = ["ready", "listening", "thinking", "working", "speaking", "waiting", "error"];

export function AvatarSettings(props: { value: AssistantPreferences; onChange: (next: AssistantPreferences) => void; active: boolean; error: string }) {
  const [designs, setDesigns] = useState<readonly AvatarDesign[]>([]);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [pose, setPose] = useState<AvatarPose>("ready");
  useEffect(() => {
    if (!props.active) return;
    let cancelled = false;
    avatarDesigns().then((items) => { if (!cancelled) { setDesigns(items); setError(""); } }, () => { if (!cancelled) setError("The avatar library could not load."); });
    return () => { cancelled = true; };
  }, [props.active, attempt]);
  return <section className="aa-avatar-settings" aria-label="Avatar appearance">
    <h2 className="aa-settings__heading">Make it yours</h2>
    <p className="aa-note">Choose a Watch particle orb, the iPhone woven orb, or a shaded character.</p>
    <div className="aa-avatar-preview"><AppAvatar design={props.value.design} pose={pose} size={260} level={.55} active={props.active}
      palette={avatarPalette(props.value.design, pose)} animated={props.value.animated} followCursor label={`Preview · ${pose}`} /></div>
    <div className="aa-setting"><label htmlFor="assistant-avatar-design">Avatar</label>
      <select id="assistant-avatar-design" value={props.value.design} disabled={!designs.length} onChange={(e) => props.onChange({ ...props.value, design: e.target.value })}>
        {!designs.some((d) => d.id === props.value.design) && <option value={props.value.design}>Current avatar</option>}
        {Array.from(new Set(designs.map((d) => d.family))).map((family) => <optgroup key={family} label={family[0].toUpperCase() + family.slice(1)}>
          {designs.filter((d) => d.family === family).map((design) => <option value={design.id} key={design.id}>{design.name}</option>)}
        </optgroup>)}
      </select>
    </div>
    <p className="aa-note">{designs.find((d) => d.id === props.value.design)?.description}</p>
    <div className="aa-phase-picker" role="group" aria-label="Preview activity states">{POSES.map((p) =>
      <button key={p} type="button" aria-pressed={p === pose} onClick={() => setPose(p)}>{p[0].toUpperCase() + p.slice(1)}</button>)}</div>
    <p className="aa-note">Silent preview · Listening and Speaking use a sample level.</p>
    <label className="aa-setting aa-setting--switch"><span>Animate activity<small>Your system’s reduced-motion preference always applies.</small></span>
      <input type="checkbox" checked={props.value.animated} onChange={(e) => props.onChange({ ...props.value, animated: e.target.checked })} /></label>
    {(error || props.error) && <p className="aa-note" role="status">{error || props.error} {error && <button className="aa-link" type="button" onClick={() => setAttempt((n) => n + 1)}>Try again</button>}</p>}
  </section>;
}
