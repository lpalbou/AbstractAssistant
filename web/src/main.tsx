import React from "react";
import { createRoot } from "react-dom/client";

import "./styles/index.css";
import { App } from "./App";
import { resolveHost } from "./host";

const root = createRoot(document.getElementById("root") as HTMLElement);
try {
  const config = (window as unknown as { __ABSTRACT_UI_CONFIG__?: unknown }).__ABSTRACT_UI_CONFIG__;
  const host = resolveHost(config, import.meta.env.DEV);
  root.render(
    <React.StrictMode>
      <App host={host} />
    </React.StrictMode>,
  );
} catch (err) {
  root.render(
    <main className="aa-fatal" role="alert">
      <h1>AbstractAssistant cannot start</h1>
      <p>{err instanceof Error ? err.message : String(err)}</p>
    </main>,
  );
}
