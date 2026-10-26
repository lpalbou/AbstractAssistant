/**
 * Which host runs this page. The app server's shell says it
 * (`window.__ABSTRACT_UI_CONFIG__.host`, injected by bin/server.js); the Vite
 * dev server serves index.html as is, so in development the browser host is
 * assumed. Anything else is an error, never a guess.
 */
import { createBrowserHost } from "./browser";
import type { AssistantHost } from "./types";

export type { AssistantHost, AuthAdapter, CapabilityState, HostCapabilities, HostKind, SignInSurface } from "./types";

export function resolveHost(config: unknown, isDev: boolean): AssistantHost {
  const declared = config && typeof config === "object" ? (config as { host?: unknown }).host : undefined;
  if (declared === "browser" || (declared === undefined && isDev)) return createBrowserHost();
  if (declared === "tauri") {
    throw new Error("The desktop (Tauri) host is not implemented yet: see ADR 0007, 'Hosts', and the coming ADR 0008.");
  }
  if (declared === undefined) {
    throw new Error("This page was not served by the AbstractAssistant web server (no host configuration in the page).");
  }
  throw new Error(`Unknown host ${JSON.stringify(declared)} in the page configuration.`);
}
