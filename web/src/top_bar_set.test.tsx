// The shared top-bar set (operator ruling 2026-10-29: "change the widget once,
// it changes everywhere"): the docs drawer button, the theme picker
// (Appearance), the About dialog and the account widget are the KIT's
// components, never local copies. The browser app's header is the kit's
// AfAppShell, whose cluster is AfTopBarActions: its `topBar` passes all four
// (the docs toggle opens panel-chat's docsAssistantPanel, appearance
// {value, onChange} makes the kit render AfAppearanceDialog, `about` its
// AfAboutDialog, identity "menu" with the useGatewayConnection value its ONE
// account widget). Removing a piece from App.tsx turns this red.
import React from "react";
import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AfAppShell, appIdentity, type AfAppShellTopBar } from "@abstractframework/ui-kit";

const app = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");

/** The `const topBar: AfAppShellTopBar = { ... };` object literal in App.tsx (brace-aware). */
function topBarLiteral(src: string): string {
  const start = src.indexOf("const topBar: AfAppShellTopBar = {");
  expect(start, "the topBar literal in App.tsx").toBeGreaterThanOrEqual(0);
  let depth = 0;
  for (let i = src.indexOf("{", start); i < src.length; i++) {
    if (src[i] === "{") depth++;
    else if (src[i] === "}" && --depth === 0) return src.slice(start, i + 1);
  }
  throw new Error("the topBar literal is never closed");
}

describe("the shared top-bar set", () => {
  const bar = topBarLiteral(app);

  it("passes the four kit pieces to the kit shell's top bar", () => {
    expect(bar).toMatch(/\bdocs: \{ open: panel === "docs",/);
    expect(bar).toMatch(/\bappearance: \{ value: appearance, onChange: setAppearance \}/);
    expect(bar).toMatch(/\babout: \{ identity, fetch: client\.fetchGateway \}/);
    expect(bar).toMatch(/\bidentity: "menu"/);
    expect(bar).toMatch(/\bconnection: conn,/);
    expect(app).toMatch(/const conn = useGatewayConnection\(/);
  });

  it("renders it through the kit (AfAppShell) and panel-chat's docs panel, never local copies", () => {
    expect((app.match(/<AfAppShell\b[^>]*topBar=\{(?:props\.)?topBar\}/g) || []).length).toBe(2);
    expect(app).toMatch(/import \{ docsAssistantPanel \} from "@abstractframework\/panel-chat"/);
    expect(app).toMatch(/docsAssistantPanel\(\{ app: "assistant", name: "AbstractAssistant" \}/);
    for (const local of [/function \w*About\w*Dialog/, /function \w*Appearance\w*Dialog/, /Signed in as/, /af-topbar__/]) expect(app).not.toMatch(local);
  });

  it("the installed kit renders the set with the one account widget (ui-kit 0.9.6)", () => {
    const noop = () => {};
    const status = { ok: true, has_session: true, gateway_url: "http://gw.local:8080", gateway: { ok: true, principal: { user_id: "alice" } } };
    const topBar: AfAppShellTopBar = {
      brand: { name: "Assistant" },
      docs: { open: false, onToggle: noop },
      appearance: { onOpen: noop },
      about: { identity: appIdentity("abstractassistant", "0.0.0") },
      identity: "menu",
      connection: { phase: "connected", onConnect: noop, onDisconnect: noop, status },
    };
    const html = renderToStaticMarkup(<AfAppShell topBar={topBar}>{null}</AfAppShell>);
    const at = ["af-topbar__btn--docs", "af-topbar__btn--appearance", "af-topbar__btn--about", 'data-af-identity="menu"'].map((m) => html.indexOf(m));
    expect(at.every((v, i) => v >= 0 && (i === 0 || v > at[i - 1]))).toBe(true);
    expect(html).toContain('<span class="af-topbar__identity-label">alice</span>');
    expect(html).not.toContain("af-topbar__pill");
  });
});
