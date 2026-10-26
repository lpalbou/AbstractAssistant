import { describe, expect, it } from "vitest";

import { browserCapabilities, readCookie } from "./browser";
import { resolveHost } from "./index";

describe("host selection", () => {
  it("builds the browser host from the shell config, or in development", () => {
    expect(resolveHost({ host: "browser", base_path: "/apps/assistant-web" }, false).kind).toBe("browser");
    expect(resolveHost(undefined, true).kind).toBe("browser");
  });
  it("refuses a page without host config in production, and the unwritten Tauri host", () => {
    expect(() => resolveHost(undefined, false)).toThrow(/not served by the AbstractAssistant web server/);
    expect(() => resolveHost({ host: "tauri" }, false)).toThrow(/not implemented/);
    expect(() => resolveHost({ host: "electron" }, false)).toThrow(/Unknown host/);
  });
  it("browser URLs are relative to the page (never rooted), so /apps/assistant-web/ keeps them", () => {
    const h = resolveHost({ host: "browser" }, false);
    expect(h.gatewayUrl("runs/start")).toBe("api/gateway/runs/start");
    expect(() => h.gatewayUrl("/runs/start")).toThrow();
  });
  it("a mutation without the CSRF cookie throws instead of going out unauthenticated", () => {
    const h = resolveHost({ host: "browser" }, false);
    expect(h.auth.headers(false)).toEqual({});
    expect(() => h.auth.headers(true)).toThrow(/signed out/);
  });
});

describe("browser capabilities are reported, not faked", () => {
  it("the microphone needs a secure page", () => {
    const caps = browserCapabilities({ secureContext: false, hasGetUserMedia: true, hasMediaRecorder: true, hasAudioContext: true });
    expect(caps.microphone.available).toBe(false);
    expect(caps.tray.available).toBe(false);
    expect(caps.audioPlayback.available).toBe(true);
    expect(browserCapabilities({ secureContext: true, hasGetUserMedia: true, hasMediaRecorder: true, hasAudioContext: false }).microphone.available).toBe(true);
  });
  it("reads the app server's CSRF cookie", () => {
    expect(readCookie("a=1; abstractassistant_gateway_csrf=t%2Bk; b=2", "abstractassistant_gateway_csrf")).toBe("t+k");
    expect(readCookie("a=1", "abstractassistant_gateway_csrf")).toBe("");
  });
});
