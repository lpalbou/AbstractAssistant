/**
 * Settings → Voice: the kit's AfVoiceSection (backlog 0035). "Gateway default · provider /
 * model" comes from the gateway's `GET voice/defaults`; the person's overrides, devices,
 * volume and microphone mode are kept in this browser (`useVoicePreferences`: the gateway keeps
 * no voice preference per account yet).
 *
 * Waits for gateway 0.16.0 (not wired here): the voice library (`voiceLibrary`: create, list,
 * rename, share voices over voice/design and voice/clones) and the engine language lists
 * (`fetchLanguages`, voice/languages).
 */
import { AfVoiceSection, type VoiceCatalog, type VoiceClientPreferences, type VoiceDefaults } from "@abstractframework/ui-kit";

import type { GatewayClient } from "../gateway/client";

/** What an unset preference means in this app (shown as the selected state). */
export const CAPTURE_DEFAULTS = { capture_mode: "toggle" as const, auto_send: false };

export function SettingsPanel(props: {
  client: GatewayClient;
  prefs: VoiceClientPreferences;
  onPrefsChange: (next: VoiceClientPreferences) => void;
  defaults: VoiceDefaults | null;
}) {
  const { client } = props;
  return (
    <div className="aa-settings">
      <h2 className="aa-settings__heading">Voice</h2>
      <AfVoiceSection
        nested
        value={props.prefs}
        onChange={props.onPrefsChange}
        fetchCatalog={(provider, model) => client.voiceCatalog(provider, model) as Promise<VoiceCatalog>}
        fetchDefaults={() => client.voiceDefaults() as Promise<VoiceDefaults>}
        defaults={props.defaults}
        overrideOwner="this app"
        // This app honours Mute, the microphone mode and "Send what you say automatically".
        rows={{ mute: true, capture: true }}
        captureDefaults={CAPTURE_DEFAULTS}
      />
    </div>
  );
}
