#!/usr/bin/env node
import { createGatewayUrlResolver, parseAppFlagsOrExit } from "@abstractframework/app-server";

import { createAssistantServer } from "./server.js";

// The shared launch flags (abstractuic app-server): --gateway-url, --port,
// --host (default 127.0.0.1: the gateway serves this app at /apps/assistant-web/).
const flags = parseAppFlagsOrExit(process.argv.slice(2), {
  appName: "AbstractAssistant Web",
  command: "abstractassistant-web",
  envPrefix: "ABSTRACTASSISTANT",
  defaultPort: 3008,
});

const fixed = flags.gatewayUrlSource === "flag" || flags.gatewayUrlSource.startsWith("env:");
const server = createAssistantServer({ defaultGatewayUrl: fixed ? flags.gatewayUrl : createGatewayUrlResolver() });

server.listen(flags.port, flags.host, () => {
  console.log(`AbstractAssistant Web on http://${flags.host}:${flags.port}/ (gateway ${flags.gatewayUrl}, from ${flags.gatewayUrlSource})`);
});

function shutdown() {
  server.close(() => process.exit(0));
}
process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
