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

// A port already in use (or a host this machine does not have) is a one-line
// error and exit code 1, never a stack trace: the gateway's app manager and a
// person at a terminal both read the first line.
server.on("error", (error) => {
  const where = `${flags.host}:${flags.port}`;
  const reason =
    error?.code === "EADDRINUSE"
      ? `port ${flags.port} is already in use (choose another with --port)`
      : error?.code === "EADDRNOTAVAIL"
        ? `${flags.host} is not an address of this computer (see --host)`
        : String(error?.message || error);
  console.error(`AbstractAssistant Web could not listen on ${where}: ${reason}`);
  process.exit(1);
});

server.listen(flags.port, flags.host, () => {
  console.log(`AbstractAssistant Web on http://${flags.host}:${flags.port}/ (gateway ${flags.gatewayUrl}, from ${flags.gatewayUrlSource})`);
});

// Stop promptly: close() alone waits for every open connection, and a live
// reply stream stays open for minutes, so the open sockets are closed too.
function shutdown() {
  server.close(() => process.exit(0));
  server.closeAllConnections?.();
}
process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
