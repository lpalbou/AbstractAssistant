/**
 * The browser host: the page is served by this package's app server
 * (bin/server.js), on its own port or under the gateway's
 * /apps/assistant-web/. Same-origin RELATIVE URLs ("api/gateway/…", resolved
 * under the page's <base href>, as abstractcode/web does with the kit's
 * gatewayApiPath), the app server's HttpOnly cookie session, and its
 * readable CSRF twin sent back on every mutation.
 */
import { gatewayApiPath, joinBaseUrl } from "@abstractframework/ui-kit";

import type { AssistantHost, CapabilityState, HostCapabilities } from "./types";

/** The app server's cookie prefix (bin/server.js COOKIE_APP_ID) and its CSRF names. */
export const COOKIE_APP_ID = "abstractassistant";
export const CSRF_COOKIE = `${COOKIE_APP_ID}_gateway_csrf`;
export const CSRF_HEADER = "X-AbstractAssistant-CSRF";

export function readCookie(cookieHeader: string, name: string): string {
  for (const part of String(cookieHeader || "").split(";")) {
    const p = part.trim();
    if (p.startsWith(`${name}=`)) {
      try {
        return decodeURIComponent(p.slice(name.length + 1));
      } catch {
        return "";
      }
    }
  }
  return "";
}

const unavailable = (reason: string): CapabilityState => ({ available: false, reason });

export function browserCapabilities(env: {
  secureContext: boolean;
  hasGetUserMedia: boolean;
  hasMediaRecorder: boolean;
  hasAudioContext: boolean;
}): HostCapabilities {
  let microphone: CapabilityState = { available: true };
  if (!env.secureContext) {
    // Browsers expose the microphone only to secure pages: https://, or
    // http://localhost / 127.0.0.1. A plain http:// LAN address is not one.
    microphone = unavailable(
      "Dictation needs a secure page: open the Assistant over https:// (or on the gateway machine at http://127.0.0.1).",
    );
  } else if (!env.hasGetUserMedia || !env.hasMediaRecorder) {
    microphone = unavailable("This browser cannot record audio (no getUserMedia or MediaRecorder).");
  }
  return {
    tray: unavailable("A browser tab has no menu-bar icon; the desktop app has one."),
    globalHotkey: unavailable("A browser tab cannot listen for a system-wide shortcut."),
    systemNotifications: unavailable("Not in this version: notifications while the tab is closed need a service worker and web push (ADR 0007, v2)."),
    autostart: unavailable("A browser tab does not start with your session."),
    microphone,
    audioPlayback: env.hasAudioContext
      ? { available: true }
      : unavailable("This browser has no Web Audio: read aloud is unavailable."),
  };
}

export function createBrowserHost(): AssistantHost {
  const w = globalThis as unknown as {
    isSecureContext?: boolean;
    navigator?: { mediaDevices?: { getUserMedia?: unknown } };
    MediaRecorder?: unknown;
    AudioContext?: unknown;
    webkitAudioContext?: unknown;
  };
  return {
    kind: "browser",
    // "" base: relative to the page, so under /apps/assistant-web/ the call
    // reaches this app's own server, which proxies it to the gateway.
    gatewayUrl: (route: string) => joinBaseUrl("", gatewayApiPath(route)),
    auth: {
      kind: "app-cookie-session",
      credentials: "same-origin",
      headers(mutating: boolean): Record<string, string> {
        if (!mutating) return {};
        const csrf = readCookie(typeof document === "undefined" ? "" : document.cookie, CSRF_COOKIE);
        if (!csrf) {
          throw new Error("You are signed out of the gateway (no session cookie on this page): sign in again.");
        }
        return { [CSRF_HEADER]: csrf };
      },
    },
    signIn: "app-server-modal",
    capabilities: browserCapabilities({
      secureContext: Boolean(w.isSecureContext),
      hasGetUserMedia: typeof w.navigator?.mediaDevices?.getUserMedia === "function",
      hasMediaRecorder: typeof w.MediaRecorder === "function",
      hasAudioContext: typeof w.AudioContext === "function" || typeof w.webkitAudioContext === "function",
    }),
  };
}
