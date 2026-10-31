/**
 * The app shell, composed from the kit (ADR 0001; backlog 0036): `AfAppShell` = the header
 * (brand · the top-right cluster: docs assistant · appearance · about · identity · connection
 * pill), the drawer system (the docs assistant), and the conversations as its navigation.
 */
import { docsAssistantPanel } from "@abstractframework/panel-chat";
import {
  AfAppShell,
  Icon,
  GatewayConnectModal,
  appIdentity,
  useAppearanceSettings,
  useGatewayConnection,
  useVoiceDefaults,
  useVoicePreferences,
  voiceCaptureMode,
  type VoiceDefaults,
  type AfAppShellTopBar,
  type AfDrawerSystemProps,
  type GatewayConnection,
} from "@abstractframework/ui-kit";
import { useCallback, useEffect, useMemo, useState } from "react";

import { version as APP_VERSION } from "../package.json";
import { GatewayClient } from "./gateway/client";
import { themeGroup } from "./lib/theme";
import type { AssistantHost } from "./host";
import { SessionList } from "./ui/SessionList";
import { CAPTURE_DEFAULTS, SettingsPanel } from "./ui/SettingsPanel";
import { useConversations, type AttentionSeen } from "./ui/useConversations";
import { Workspace } from "./ui/Workspace";
import { useAssistantPreferences, type AssistantPreferences } from "./ui/useAssistantPreferences";

function systemPrefersLight(): boolean {
  try {
    return typeof matchMedia === "function" && matchMedia("(prefers-color-scheme: light)").matches;
  } catch {
    return false;
  }
}

type Drawers = Omit<AfDrawerSystemProps, "children">;

function Splash(props: { conn: GatewayConnection }) {
  if (props.conn.phase === "loading")
    return (
      <div className="aa-splash" aria-busy="true">
        <p>Connecting to your gateway…</p>
      </div>
    );
  return (
    <div className="aa-splash">
      <p>Sign in to your gateway to talk with the Assistant.</p>
      <button type="button" className="aa-button aa-button--primary" onClick={props.conn.openModal}>
        Sign in
      </button>
    </div>
  );
}

const VOICE_KEY = "abstractassistant.voice";

function ConnectedApp(props: { client: GatewayClient; host: AssistantHost; conn: GatewayConnection; topBar: AfAppShellTopBar; drawers: Drawers;
  appearance: AssistantPreferences; onSettings: () => void }) {
  const [voicePrefs, setVoicePrefs] = useVoicePreferences(VOICE_KEY);
  const { client, conn } = props;
  const [selected, setSelected] = useState<{ sessionId: string; runId: string }>({ sessionId: "", runId: "" });
  const [seen, setSeen] = useState<AttentionSeen | null>(null);
  const [navOpen, setNavOpen] = useState(false);
  const [selectionEpoch, setSelectionEpoch] = useState(0);
  const onSignedOut = useCallback(() => void conn.refresh(), [conn]);
  const conversations = useConversations(client, { onSignedOut, onAttentionSeen: setSeen });
  const title = selected.sessionId ? conversations.titles[selected.sessionId] || "Conversation" : "New conversation";
  return (
    <AfAppShell
      className="aa-shell"
      topBar={props.topBar}
      drawers={props.drawers}
      nav={{
        label: "Conversations",
        width: 264,
        open: navOpen,
        onOpenChange: setNavOpen,
        content: (
          <SessionList
            rows={conversations.rows}
            titles={conversations.titles}
            truncated={conversations.truncated}
            error={conversations.error}
            notice={conversations.notice}
            activeId={selected.sessionId}
            onOpen={(r) => {
              setSelectionEpoch((n) => n + 1);
              setNavOpen(false);
              setSelected({ sessionId: r.session_id, runId: r.latest_run_id });
            }}
            onNew={() => {
              setSelectionEpoch((n) => n + 1);
              setNavOpen(false);
              setSelected({ sessionId: "", runId: "" });
            }}
            onRefresh={() => void conversations.refresh()}
            onSettings={props.onSettings}
          />
        ),
      }}
    >
      <Workspace
        key={selectionEpoch}
        client={client}
        host={props.host}
        sessionId={selected.sessionId}
        runId={selected.runId}
        title={title}
        seen={seen}
        eventsNotice={conversations.eventsError}
        voicePrefs={voicePrefs}
        onVoicePrefsChange={setVoicePrefs}
        appearance={props.appearance}
        onSettings={props.onSettings}
        captureMode={voicePrefs.capture_mode ? voiceCaptureMode(voicePrefs.capture_mode) : CAPTURE_DEFAULTS.capture_mode}
        autoSend={typeof voicePrefs.auto_send === "boolean" ? voicePrefs.auto_send : CAPTURE_DEFAULTS.auto_send}
        onStarted={(runId, sessionId) => {
          setSelected({ sessionId, runId });
          void conversations.refresh();
        }}
        onNewChat={() => { setSelectionEpoch((n) => n + 1); setSelected({ sessionId: "", runId: "" }); }}
        onTurnEnded={() => void conversations.refresh()}
        onSignedOut={onSignedOut}
      />
    </AfAppShell>
  );
}

/** The browser host's sign-in: the kit's ONE connection machine (abstractuic
 * docs/adoption-guide.md, "Gateway connection surface"), against this app server's
 * `api/connection/gateway`. */
function BrowserApp({ host }: { host: AssistantHost }) {
  const conn = useGatewayConnection({ appName: "AbstractAssistant", variant: "blocking" });
  const client = useMemo(() => new GatewayClient(host), [host]);
  const [appearance, setAppearance] = useAppearanceSettings("abstractassistant", { defaults: { theme: systemPrefersLight() ? "light" : "dark" } });
  useEffect(() => {
    document.documentElement.dataset.theme = themeGroup(appearance.theme);
  }, [appearance.theme]);
  const [panel, setPanel] = useState<string | null>(null);
  const identity = useMemo(() => appIdentity("abstractassistant", APP_VERSION), []);
  const [voicePrefs, setVoicePrefs] = useVoicePreferences(VOICE_KEY);
  const companion = useAssistantPreferences();
  const voiceDefaults = useVoiceDefaults(conn.connected ? () => client.voiceDefaults() as Promise<VoiceDefaults> : null, client);
  const panels = useMemo(
    () => [
      docsPanel(),
      ...(conn.connected
        ? [
            {
              id: "settings",
              label: "Settings",
              icon: "settings" as const,
              mode: "drawer" as const,
              defaultWidth: 420,
              content: <SettingsPanel client={client} prefs={voicePrefs} onPrefsChange={setVoicePrefs} defaults={voiceDefaults.value}
                appearance={companion.value} onAppearanceChange={companion.change} preferenceError={companion.error} active={panel === "settings"} />,
            },
          ]
        : []),
    ],
    [client, conn.connected, panel, voicePrefs, setVoicePrefs, voiceDefaults.value, companion.value, companion.change, companion.error],
  );
  // Compatibility with published panel-chat 0.6.4. The shared component now owns
  // this fill/layout fix; remove the wrapper when that package update is adopted.
  function docsPanel() {
    const docs = docsAssistantPanel({ app: "assistant-web", name: "AbstractAssistant" }, client.fetchGateway, {
        connected: conn.connected,
        visible: panel === "docs",
        voicePreferences: voicePrefs,
        placeholder: "Ask about the Assistant…",
        suggestions: ["How do I use voice?", "How do conversations work?", "What can the Assistant do?"],
      });
    return { ...docs, fill: true, content: <div className="aa-docs-panel">{docs.content}<p className="aa-docs-grounding">Answers use the Assistant documentation.</p></div> };
  }
  const topBar: AfAppShellTopBar = {
    brand: { name: "Assistant", mark: <span className="aa-brand-mark"><Icon name="sparkle" size={18} /></span> },
    connection: conn,
    identity: "menu",
    appearance: { value: appearance, onChange: setAppearance },
    about: { identity, fetch: client.fetchGateway },
    docs: { open: panel === "docs", onToggle: () => setPanel((p) => (p === "docs" ? null : "docs")) },
  };
  const drawers: Drawers = {
    panels,
    active: panel,
    onActiveChange: (id) => setPanel(id),
    ariaLabel: "Assistant panels",
    storageKey: "abstractassistant.panels",
    overlay: true,
    restoreActive: false,
  };
  return (
    <>
      <GatewayConnectModal {...conn.modalProps} />
      {conn.connected ? (
        <ConnectedApp client={client} host={host} conn={conn} topBar={topBar} drawers={drawers}
          appearance={companion.value} onSettings={() => setPanel("settings")} />
      ) : (
        <AfAppShell topBar={topBar} drawers={drawers}>
          <Splash conn={conn} />
        </AfAppShell>
      )}
    </>
  );
}

export function App({ host }: { host: AssistantHost }) {
  if (host.signIn === "app-server-modal") return <BrowserApp host={host} />;
  // A host that signs in natively (the future desktop shell) has not been written: say so
  // instead of rendering a half-connected page.
  throw new Error(`Host sign-in "${host.signIn}" is not implemented in this build (ADR 0007, Hosts).`);
}
