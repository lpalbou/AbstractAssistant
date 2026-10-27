/**
 * The app shell, composed from the kit (ADR 0001; backlog 0036): `AfAppShell` = the header
 * (brand · the top-right cluster: docs assistant · appearance · about · identity · connection
 * pill), the drawer system (the docs assistant), and the conversations as its navigation.
 */
import { docsAssistantPanel } from "@abstractframework/panel-chat";
import {
  AfAppShell,
  GatewayConnectModal,
  appIdentity,
  useAppearanceSettings,
  useGatewayConnection,
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
import { useConversations, type AttentionSeen } from "./ui/useConversations";
import { Workspace } from "./ui/Workspace";

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

function ConnectedApp(props: { client: GatewayClient; host: AssistantHost; conn: GatewayConnection; topBar: AfAppShellTopBar; drawers: Drawers }) {
  const { client, conn } = props;
  const [selected, setSelected] = useState<{ sessionId: string; runId: string }>({ sessionId: "", runId: "" });
  const [seen, setSeen] = useState<AttentionSeen | null>(null);
  const [navOpen, setNavOpen] = useState(false);
  const onSignedOut = useCallback(() => void conn.refresh(), [conn]);
  const conversations = useConversations(client, { onSignedOut, onAttentionSeen: setSeen });
  const row = conversations.rows.find((r) => r.session_id === selected.sessionId);
  const title = selected.sessionId ? conversations.titles[selected.sessionId] || "Conversation" : "New conversation";
  return (
    <AfAppShell
      topBar={props.topBar}
      drawers={props.drawers}
      nav={{
        label: "Conversations",
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
              setNavOpen(false);
              setSelected({ sessionId: r.session_id, runId: r.latest_run_id });
            }}
            onNew={() => {
              setNavOpen(false);
              setSelected({ sessionId: "", runId: "" });
            }}
            onRefresh={() => void conversations.refresh()}
          />
        ),
      }}
    >
      <Workspace
        client={client}
        host={props.host}
        sessionId={selected.sessionId}
        runId={selected.runId}
        title={title}
        {...(row ? { listState: row.state } : {})}
        seen={seen}
        eventsNotice={conversations.eventsError}
        voicePrefs={{}}
        captureMode="toggle"
        onStarted={(runId, sessionId) => {
          setSelected({ sessionId, runId });
          void conversations.refresh();
        }}
        onNewChat={() => setSelected({ sessionId: "", runId: "" })}
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
  const panels = useMemo(
    () => [
      // The gateway's docs corpus has no "assistant" id yet (backlog 0036): the drawer is wired
      // and the first question answers with the gateway's own refusal until it has one.
      docsAssistantPanel({ app: "assistant", name: "AbstractAssistant" }, client.fetchGateway, {
        connected: conn.connected,
        placeholder: "Ask about AbstractAssistant (from the gateway's Assistant docs, docs/corpus?app=assistant)",
      }),
    ],
    [client, conn.connected],
  );
  const topBar: AfAppShellTopBar = {
    brand: { name: "Assistant" },
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
  };
  return (
    <>
      <GatewayConnectModal {...conn.modalProps} />
      {conn.connected ? (
        <ConnectedApp client={client} host={host} conn={conn} topBar={topBar} drawers={drawers} />
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
