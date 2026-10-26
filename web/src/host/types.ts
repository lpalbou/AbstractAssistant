/**
 * What the frontend needs from whatever hosts it (ADR 0007, "Hosts: browser
 * and Tauri shell"). ONE small interface, so the same UI codebase can run in
 * a browser tab (served by the gateway at /apps/assistant-web/) and, later,
 * inside a desktop shell (a Tauri WebView, ADR 0008 — not written yet).
 *
 * Nothing outside src/host/ may assume same-origin, cookies or a bearer
 * token: every gateway request goes through `gatewayUrl()` + `auth`.
 */

export type HostKind = "browser" | "tauri";

/** A host capability: present, or absent with the sentence that says why. */
export type CapabilityState = { available: true } | { available: false; reason: string };

/**
 * Native affordances a host may offer. The browser host reports most of
 * them unavailable, honestly, instead of faking them.
 */
export type HostCapabilities = {
  /** A menu-bar / system-tray icon and badge. */
  tray: CapabilityState;
  /** A system-wide shortcut that opens the Assistant from anywhere. */
  globalHotkey: CapabilityState;
  /** OS notifications while the app is not in front. */
  systemNotifications: CapabilityState;
  /** Start with the session (login item). */
  autostart: CapabilityState;
  /** Microphone capture for dictation (getUserMedia + MediaRecorder). */
  microphone: CapabilityState;
  /** Audio playback for read aloud (Web Audio). */
  audioPlayback: CapabilityState;
};

/**
 * How a gateway request is authenticated. The browser host uses the app
 * server's cookie session (the token never reaches the page); a desktop
 * host would hold a bearer token on the native side.
 */
export type AuthAdapter = {
  readonly kind: "app-cookie-session" | "bearer";
  /** fetch `credentials` for gateway requests. */
  readonly credentials: RequestCredentials;
  /**
   * Headers to add to one gateway request. `mutating` is true for
   * POST/PUT/PATCH/DELETE. Throws when the request cannot be authenticated
   * (e.g. no CSRF cookie: the browser session is gone).
   */
  headers(mutating: boolean): Record<string, string>;
};

/** The sign-in surface the host provides. */
export type SignInSurface =
  /** The app server's `api/connection/gateway` + the kit's GatewayConnectModal. */
  | "app-server-modal"
  /** The host signs in natively and hands the frontend a ready AuthAdapter. */
  | "host-native";

export type AssistantHost = {
  readonly kind: HostKind;
  /** URL of a gateway API route: `gatewayUrl("runs/start")`. Never rooted at "/". */
  gatewayUrl(route: string): string;
  readonly auth: AuthAdapter;
  readonly signIn: SignInSurface;
  readonly capabilities: HostCapabilities;
};
