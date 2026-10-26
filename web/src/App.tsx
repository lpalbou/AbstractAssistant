import { GatewayConnectModal, useGatewayConnection } from "@abstractframework/ui-kit";
import { useMemo } from "react";

import { GatewayClient } from "./gateway/client";
import type { AssistantHost } from "./host";
import { Workspace } from "./ui/Workspace";

/** The browser host's sign-in: the kit's ONE connection machine (abstractuic
 * docs/adoption-guide.md, "Gateway connection surface"), against this app
 * server's `api/connection/gateway`. Blocking: there is nothing to show
 * signed out. */
function BrowserGate({ host }: { host: AssistantHost }) {
  const conn = useGatewayConnection({ appName: "AbstractAssistant", variant: "blocking" });
  const client = useMemo(() => new GatewayClient(host), [host]);
  return (
    <>
      <GatewayConnectModal {...conn.modalProps} />
      {conn.phase === "loading" ? (
        <main className="aa-splash" aria-busy="true">
          <p>Connecting to your gateway…</p>
        </main>
      ) : conn.connected ? (
        <Workspace client={client} host={host} onSignedOut={() => void conn.refresh()} onSignOut={() => void conn.signOut()} />
      ) : (
        <main className="aa-splash">
          <p>Sign in to your gateway to talk with the Assistant.</p>
          <button type="button" className="aa-button aa-button--primary" onClick={conn.openModal}>
            Sign in
          </button>
        </main>
      )}
    </>
  );
}

export function App({ host }: { host: AssistantHost }) {
  if (host.signIn === "app-server-modal") return <BrowserGate host={host} />;
  // A host that signs in natively (the future desktop shell) has not been
  // written: say so instead of rendering a half-connected page.
  throw new Error(`Host sign-in "${host.signIn}" is not implemented in this build (ADR 0007, Hosts).`);
}
