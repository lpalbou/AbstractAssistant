/**
 * The AbstractAssistant web server: the built app (`dist/`) and the
 * app-origin gateway session proxy, on the shared app-server kit
 * (`@abstractframework/app-server`).
 *
 * Ported from abstractcode/web/bin/server.js (same contract, fewer routes):
 * - Serves under the gateway's `/apps/assistant-web/` as well as on its own
 *   port (`createMountedHandler`: base path from `X-Forwarded-Prefix`, the
 *   browser's address from a loopback peer's `X-Forwarded-For`, the identity
 *   header `X-AbstractFramework-App: assistant-web; mount=1`). The shell gets
 *   `<base href>` (`injectShell`), so every asset and API call resolves under
 *   the base.
 * - `/api/connection/gateway` and `/api/gateway/*` go through the kit's
 *   session proxy (HttpOnly session cookie + CSRF twin at `Path=<base>/`,
 *   browser `Authorization` and cookies stripped, server-pinned gateway URL).
 *   The browser never holds a gateway token.
 * - In front of the proxy, as in abstractcode: a browser mutation must come
 *   from this app's own origin, a sign-in must be JSON, and a sign-in over a
 *   loopback socket must name a loopback host (DNS-rebinding guard).
 *
 * The catalog id `assistant-web` and the cookie prefix `abstractassistant`
 * are PROPOSED (ADR 0007): the gateway serves only the apps in its catalog
 * (abstractgateway apps_manager.py `APPS`), and this id is not in it yet.
 */
import * as http from "node:http";
import { existsSync, readFileSync, statSync } from "node:fs";
import { isIP } from "node:net";
import { dirname, extname, join, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

import {
  createGatewaySessionProxy,
  createMountedHandler,
  injectShell,
  requestContext,
  socketPeerAddress,
} from "@abstractframework/app-server";

const BIN_DIR = dirname(fileURLToPath(import.meta.url));
const DEFAULT_DIST_DIR = resolve(BIN_DIR, "..", "dist");
/** The gateway's catalog id (PROPOSED): `/apps/assistant-web/` and the identity header. */
export const APP_ID = "assistant-web";
/** Cookie / CSRF-header prefix: `abstractassistant_gateway_*`, `x-abstractassistant-csrf`. */
export const COOKIE_APP_ID = "abstractassistant";
const CONNECTION_PATH = "/api/connection/gateway";
const GATEWAY_PREFIX = "/api/gateway/";
const MIME_TYPES = {
  ".html": "text/html",
  ".js": "application/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".webmanifest": "application/manifest+json",
  ".woff2": "font/woff2",
};

function sendJson(res, status, payload) {
  if (res.headersSent) {
    res.destroy();
    return;
  }
  res.writeHead(status, { "Content-Type": "application/json; charset=utf-8" });
  res.end(JSON.stringify(payload));
}

function firstHeader(value) {
  return String(Array.isArray(value) ? value[0] : value || "")
    .split(",", 1)[0]
    .trim();
}

function mutatingMethod(method) {
  return ["POST", "PUT", "PATCH", "DELETE"].includes(String(method || "GET").toUpperCase());
}

function hostnameOf(host) {
  const raw = String(host || "").trim().toLowerCase();
  if (raw.startsWith("[")) return raw.slice(1).split("]", 1)[0];
  return (raw.match(/:/g) || []).length === 1 ? raw.split(":")[0] : raw;
}

/** `localhost`, `*.localhost`, `::1` or a 127.x IP LITERAL (never a DNS name starting "127."). */
function isLoopbackHostname(host) {
  const h = hostnameOf(host);
  if (h === "localhost" || h.endsWith(".localhost") || h === "::1") return true;
  return isIP(h) === 4 && h.startsWith("127.");
}

/** A browser mutation must come from the origin the browser sees this app at. */
function browserMutationAllowed(req, ctx) {
  const origin = firstHeader(req.headers.origin);
  if (origin) {
    try {
      return new URL(origin).origin === new URL(`${ctx.proto}://${ctx.host}`).origin;
    } catch {
      return false;
    }
  }
  return firstHeader(req.headers["sec-fetch-site"]).toLowerCase() !== "cross-site";
}

function jsonRequest(req) {
  return firstHeader(req.headers["content-type"]).split(";", 1)[0].trim().toLowerCase() === "application/json";
}

function isLoopbackPeerSocket(req) {
  const peer = socketPeerAddress(req);
  return peer === "::1" || peer.startsWith("127.");
}

function trustProxyDeclared() {
  return ["ABSTRACTASSISTANT_TRUST_PROXY_HEADERS", "ABSTRACTGATEWAY_TRUST_PROXY_HEADERS"].some((name) =>
    ["1", "true", "yes", "y", "on"].includes(String(process.env[name] || "").trim().toLowerCase()),
  );
}

function pathnameOf(req) {
  return new URL(req.url || "/", "http://abstractassistant.local").pathname;
}

/**
 * The gateway half: connection API + `/api/gateway/*`, guarded, then the kit
 * proxy. Connect-compatible (`next` for every other path), so the Vite dev
 * server mounts the SAME code.
 */
export function createGatewayMiddleware(options = {}) {
  const proxy = createGatewaySessionProxy({
    appId: COOKIE_APP_ID,
    ...(options.defaultGatewayUrl ? { defaultGatewayUrl: options.defaultGatewayUrl } : {}),
    connectionPath: CONNECTION_PATH,
    proxyPrefix: GATEWAY_PREFIX,
  });
  function middleware(req, res, next) {
    let pathname;
    try {
      pathname = pathnameOf(req);
    } catch {
      sendJson(res, 400, { detail: "Invalid request URL" });
      return;
    }
    const owned = pathname === CONNECTION_PATH || pathname.startsWith(GATEWAY_PREFIX);
    if (!owned) {
      if (typeof next === "function") next();
      else sendJson(res, 404, { detail: "Not found" });
      return;
    }
    let ctx;
    try {
      ctx = requestContext(req);
    } catch (error) {
      sendJson(res, Number(error?.status) || 400, { detail: String(error?.message || error) });
      return;
    }
    if (
      pathname === CONNECTION_PATH &&
      mutatingMethod(req.method) &&
      isLoopbackPeerSocket(req) &&
      !isLoopbackHostname(req.headers.host) &&
      !trustProxyDeclared()
    ) {
      sendJson(res, 403, {
        detail: `Sign-in refused: this local app was reached under the host name ${hostnameOf(req.headers.host) || "(none)"}, not a loopback address.`,
        reason_code: "host_not_allowed",
      });
      return;
    }
    if (mutatingMethod(req.method) && !browserMutationAllowed(req, ctx)) {
      sendJson(res, 403, { detail: "Cross-origin browser requests are not allowed", reason_code: "origin_required" });
      return;
    }
    if (pathname === CONNECTION_PATH && req.method === "POST" && !jsonRequest(req)) {
      sendJson(res, 415, { detail: "Gateway connection requests require Content-Type: application/json" });
      return;
    }
    proxy.handle(req, res, pathname);
  }
  middleware.proxy = proxy;
  return middleware;
}

function unsafeStaticPath(req) {
  const rawPath = String(req.url || "/").split("?", 1)[0];
  let decoded;
  try {
    decoded = decodeURIComponent(rawPath);
  } catch {
    return true;
  }
  return decoded.includes("\0") || decoded.split(/[\\/]+/).includes("..");
}

function isFile(filePath) {
  try {
    return existsSync(filePath) && statSync(filePath).isFile();
  } catch {
    return false;
  }
}

function serveFile(res, filePath) {
  if (!isFile(filePath)) return false;
  res.writeHead(200, {
    "Content-Type": MIME_TYPES[extname(filePath).toLowerCase()] || "application/octet-stream",
    "Cache-Control": "no-cache",
  });
  res.end(readFileSync(filePath));
  return true;
}

function serveShell(res, distDir, basePath) {
  const index = join(distDir, "index.html");
  if (!isFile(index)) return false;
  // `host: "browser"` tells the frontend which host adapter to build (src/host/).
  const html = injectShell(readFileSync(index, "utf8"), { basePath, config: { host: "browser" } });
  res.writeHead(200, { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-cache" });
  res.end(html);
  return true;
}

export function createAssistantRequestHandler(options = {}) {
  const distDir = resolve(options.distDir || DEFAULT_DIST_DIR);
  const gatewayMiddleware = createGatewayMiddleware(options);
  return createMountedHandler({ appId: APP_ID }, (req, res, ctx) => {
    gatewayMiddleware(req, res, () => {
      let pathname;
      try {
        pathname = decodeURIComponent(pathnameOf(req));
      } catch {
        res.writeHead(400);
        res.end("Bad Request");
        return;
      }
      if (pathname === "/api" || pathname.startsWith("/api/")) {
        sendJson(res, 404, { detail: "Not found" });
        return;
      }
      if (unsafeStaticPath(req)) {
        res.writeHead(400);
        res.end("Bad Request");
        return;
      }
      if (pathname === "/" || pathname === "/index.html") {
        if (serveShell(res, distDir, ctx.basePath)) return;
      }
      const filePath = resolve(distDir, pathname.replace(/^\/+/, ""));
      if (filePath !== distDir && !filePath.startsWith(`${distDir}${sep}`)) {
        res.writeHead(400);
        res.end("Bad Request");
        return;
      }
      if (serveFile(res, filePath)) return;
      if (serveShell(res, distDir, ctx.basePath)) return;
      res.writeHead(404);
      res.end("Not Found");
    });
  });
}

export function createAssistantServer(options = {}) {
  return http.createServer(createAssistantRequestHandler(options));
}
