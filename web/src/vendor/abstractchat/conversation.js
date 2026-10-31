// dist/workflow_chat.js
import { jsx as _jsx16, jsxs as _jsxs14, Fragment as _Fragment6 } from "react/jsx-runtime";

// dist/message_artifacts.js
import { jsx as _jsx5, jsxs as _jsxs4 } from "react/jsx-runtime";
import { createContext, useContext, useEffect as useEffect5, useMemo as useMemo2, useRef as useRef3, useState as useState5 } from "react";
import { gatewayApiPath as gatewayApiPath3, Icon as Icon3 } from "@abstractframework/ui-kit";

// dist/attachment_uploads.js
import { useEffect as useEffect4, useMemo, useRef as useRef2, useState as useState4 } from "react";
import { randomId } from "@abstractframework/ui-kit";

// dist/workspace_browser.js
import { jsx as _jsx4, jsxs as _jsxs3, Fragment as _Fragment2 } from "react/jsx-runtime";
import React2, { useCallback, useEffect as useEffect3, useState as useState3 } from "react";
import { Icon as Icon2, formatExactTime, formatRelativeTime, gatewayApiPath as gatewayApiPath2, gatewayResourcePath } from "@abstractframework/ui-kit";

// dist/file_viewer.js
import { jsx as _jsx3 } from "react/jsx-runtime";
import { useEffect as useEffect2, useState as useState2 } from "react";
import { AfFileViewer, fileViewerKind, fileViewerNeedsText, formatFileSize, gatewayApiPath } from "@abstractframework/ui-kit";

// dist/markdown.js
import { jsx as _jsx2, jsxs as _jsxs2 } from "react/jsx-runtime";
import React, { useEffect, useRef, useState } from "react";
import { codeLanguage, highlightCode, Icon } from "@abstractframework/ui-kit";

// dist/utils.js
function tryParseJson(text) {
  const trimmed = String(text ?? "").trim();
  if (!trimmed)
    return null;
  if (!(trimmed.startsWith("{") && trimmed.endsWith("}") || trimmed.startsWith("[") && trimmed.endsWith("]")))
    return null;
  try {
    return JSON.parse(trimmed);
  } catch {
    return null;
  }
}
function safeJson(value) {
  if (value == null)
    return "";
  if (typeof value === "string")
    return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}
function formatMessageHeader(m) {
  const role = String(m.role || "message").trim() || "message";
  const title = String(m.title || "").trim();
  const ts = String(m.ts || "").trim();
  const parts = [role];
  if (title)
    parts.push(title);
  if (ts)
    parts.push(ts);
  return parts.join(" \xB7 ");
}
function ensureTrailingNewline(s) {
  return s.endsWith("\n") ? s : `${s}
`;
}
function isAlreadyFenced(content) {
  return String(content || "").trimStart().startsWith("```");
}
function chatToMarkdown(messages, opts) {
  const heading = String(opts?.heading || "Chat").trim() || "Chat";
  const lines = [`# ${heading}`, ""];
  for (const m of messages) {
    const header = formatMessageHeader(m);
    lines.push(`## ${header}`, "");
    const content = String(m.content || "");
    const parsed = tryParseJson(content);
    if (parsed !== null && !isAlreadyFenced(content)) {
      lines.push("```json", safeJson(parsed).trimEnd(), "```", "");
    } else {
      lines.push(ensureTrailingNewline(content).trimEnd(), "");
    }
    lines.push("---", "");
  }
  while (lines.length && !lines[lines.length - 1].trim())
    lines.pop();
  if (lines.length && lines[lines.length - 1] === "---")
    lines.pop();
  return `${lines.join("\n").trimEnd()}
`;
}
async function copyText(text) {
  const value = String(text || "");
  if (!value)
    return false;
  try {
    if (typeof navigator !== "undefined" && typeof navigator.clipboard?.writeText === "function") {
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch {
  }
  try {
    const el = document.createElement("textarea");
    el.value = value;
    el.style.position = "fixed";
    el.style.left = "-9999px";
    document.body.appendChild(el);
    el.select();
    const ok = document.execCommand("copy") === true;
    document.body.removeChild(el);
    return ok;
  } catch {
    return false;
  }
}
function downloadTextFile(opts) {
  const filename = String(opts.filename || "").trim() || "export.txt";
  const text = String(opts.text || "");
  const mime = String(opts.mime || "text/plain;charset=utf-8");
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1e3);
}

// dist/text_links.js
import { jsx as _jsx, Fragment as _Fragment, jsxs as _jsxs } from "react/jsx-runtime";
function splitTextLinks(text) {
  const out = [];
  const pattern = /(?:https?:\/\/|www\.)[^\s<>"'`\\]+/gi;
  let end = 0;
  for (const m of text.matchAll(pattern)) {
    const start = m.index;
    if (start > 0 && /[\w@]/.test(text[start - 1]))
      continue;
    let label = m[0].replace(/[.,;:!?]+$/, "");
    for (const [open, close] of [
      ["(", ")"],
      ["[", "]"],
      ["{", "}"]
    ])
      while (label.endsWith(close) && label.split(close).length > label.split(open).length)
        label = label.slice(0, -1);
    const href = /^www\./i.test(label) ? `https://${label}` : label;
    try {
      const url = new URL(href);
      if (!["http:", "https:"].includes(url.protocol) || !url.hostname || /[\u0000-\u001f\u007f]/.test(href))
        continue;
    } catch {
      continue;
    }
    if (start > end)
      out.push({ text: text.slice(end, start) });
    out.push({ text: label, href });
    end = start + label.length;
  }
  if (end < text.length)
    out.push({ text: text.slice(end) });
  return out;
}
function textLinks(text) {
  return splitTextLinks(text).map((p, i) => p.href ? _jsx("a", { className: "pc-md_link", href: p.href, target: "_blank", rel: "noopener noreferrer", children: p.text }, i) : p.text);
}
function TextLinks({ text }) {
  return _jsx(_Fragment, { children: textLinks(String(text ?? "")) });
}
function JsonTextLinks({ text }) {
  return _jsxs(_Fragment, { children: ['"', splitTextLinks(text).map((p, i) => p.href ? _jsx("a", { className: "pc-md_link", href: p.href, target: "_blank", rel: "noopener noreferrer", children: p.text }, i) : JSON.stringify(p.text).slice(1, -1)), '"'] });
}

// dist/markdown.js
function MarkdownCodeBlock({ code, lang }) {
  const [state, setState] = useState("idle");
  const timer = useRef(null);
  useEffect(() => () => {
    if (timer.current !== null)
      window.clearTimeout(timer.current);
  }, []);
  const tokens = highlightCode(code, codeLanguage(lang));
  return _jsxs2("div", { className: "pc-md_codeblock", children: [_jsx2("button", { type: "button", className: `pc-md_copy${state !== "idle" ? ` pc-md_copy--${state}` : ""}`, "aria-label": "Copy code", title: state === "idle" ? "Copy" : state === "copied" ? "Copied" : "Copy failed", onClick: async () => {
    const ok = await copyText(code);
    setState(ok ? "copied" : "failed");
    if (timer.current !== null)
      window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setState("idle"), 900);
  }, children: _jsx2(Icon, { name: state === "copied" ? "check" : "copy", size: 14 }) }), _jsx2("pre", { className: "pc-md_pre", children: _jsx2("code", { className: lang ? `language-${lang}` : void 0, children: tokens.map((t, k) => t.kind === "plain" ? _jsx2(React.Fragment, { children: t.text }, k) : _jsx2("span", { className: `af-code__${t.kind}`, children: t.text }, k)) }) })] });
}
function highlightInline(text, state, linkify = true) {
  const s = String(text ?? "");
  if (linkify)
    return splitTextLinks(s).map((part, i) => part.href ? _jsx2("a", { className: "pc-md_link", href: part.href, target: "_blank", rel: "noopener noreferrer", children: highlightInline(part.text, state, false) }, i) : _jsx2(React.Fragment, { children: highlightInline(part.text, state, false) }, i));
  if (!state || !state.needles.length)
    return linkify ? textLinks(s) : [s];
  const out = [];
  const hayLower = s.toLowerCase();
  let pos = 0;
  while (pos < s.length) {
    let bestStart = -1;
    let bestNeedle = "";
    for (let i = 0; i < state.needlesLower.length; i++) {
      const needleLower = state.needlesLower[i];
      if (!needleLower)
        continue;
      const idx = hayLower.indexOf(needleLower, pos);
      if (idx === -1)
        continue;
      const needle = state.needles[i] || "";
      if (!needle)
        continue;
      if (bestStart === -1 || idx < bestStart || idx === bestStart && needle.length > bestNeedle.length) {
        bestStart = idx;
        bestNeedle = needle;
      }
    }
    if (bestStart === -1 || !bestNeedle) {
      out.push(...linkify ? textLinks(s.slice(pos)) : [s.slice(pos)]);
      break;
    }
    if (bestStart > pos)
      out.push(...linkify ? textLinks(s.slice(pos, bestStart)) : [s.slice(pos, bestStart)]);
    const id = state.hits === 0 && state.id ? state.id : void 0;
    const matchedText = s.slice(bestStart, bestStart + bestNeedle.length);
    out.push(_jsx2("span", { id, className: state.className, children: matchedText }, `hl:${state.hits}`));
    state.hits += 1;
    pos = bestStart + bestNeedle.length;
  }
  return out;
}
function safeHref(href) {
  const value = String(href || "").trim();
  if (!value)
    return void 0;
  if (/^(https?:|mailto:|tel:|#|\/)/i.test(value))
    return value;
  return void 0;
}
var SENTINEL_BASE = "http://same-origin.invalid/";
function isRelativeReference(value) {
  try {
    const resolved = new URL(value, SENTINEL_BASE);
    return resolved.protocol === "http:" && resolved.origin === new URL(SENTINEL_BASE).origin;
  } catch {
    return false;
  }
}
function safeImageSrc(src) {
  const value = String(src || "").trim();
  return safeHref(value) ?? (value && isRelativeReference(value) ? value : void 0);
}
var inlineImagePolicy = null;
function sameOriginImage(src) {
  const value = String(src || "").trim();
  if (!value)
    return false;
  const pageBase = typeof document !== "undefined" && document.baseURI ? document.baseURI : null;
  if (pageBase === null && /^[a-z][a-z0-9+.-]*:/i.test(value))
    return false;
  const base = pageBase ?? SENTINEL_BASE;
  let origin;
  let resolved;
  try {
    origin = new URL(base).origin;
    resolved = new URL(value, base);
  } catch {
    return false;
  }
  if (resolved.protocol !== "http:" && resolved.protocol !== "https:")
    return false;
  return resolved.origin === origin;
}
function imageLink(key, src, alt) {
  return _jsx2("a", { className: "pc-md_link pc-md_image_link", href: src, target: "_blank", rel: "noopener noreferrer", children: `image: ${alt || src}` }, key);
}
function isWordChar(ch) {
  return Boolean(ch) && /[\p{L}\p{N}]/u.test(ch);
}
function renderInline(text, highlight) {
  const out = [];
  const s = String(text ?? "");
  let i = 0;
  let buf = "";
  const flush = () => {
    if (!buf)
      return;
    for (const node of highlightInline(buf, highlight))
      out.push(node);
    buf = "";
  };
  while (i < s.length) {
    const ch = s[i];
    if (ch === "!" && s[i + 1] === "[") {
      const labelEnd = s.indexOf("]", i + 2);
      if (labelEnd !== -1 && s[labelEnd + 1] === "(") {
        const hrefEnd = s.indexOf(")", labelEnd + 2);
        if (hrefEnd !== -1) {
          const alt = s.slice(i + 2, labelEnd);
          const src = safeImageSrc(s.slice(labelEnd + 2, hrefEnd));
          if (src && inlineImagePolicy && !inlineImagePolicy(src)) {
            flush();
            out.push(imageLink(`img:${i}`, src, alt));
            i = hrefEnd + 1;
            continue;
          }
          if (src) {
            flush();
            out.push(_jsxs2("span", { className: "pc-md_image_inline", children: [_jsx2("img", { className: "pc-md_img", src, alt, loading: "lazy" }), alt ? _jsx2("span", { className: "pc-md_img_caption", children: highlight ? highlightInline(alt, highlight) : alt }) : null] }, `img:${i}`));
            i = hrefEnd + 1;
            continue;
          }
        }
      }
    }
    if (ch === "[") {
      const labelEnd = s.indexOf("]", i + 1);
      if (labelEnd !== -1 && s[labelEnd + 1] === "(") {
        const hrefEnd = s.indexOf(")", labelEnd + 2);
        if (hrefEnd !== -1) {
          const label = s.slice(i + 1, labelEnd);
          const href = safeHref(s.slice(labelEnd + 2, hrefEnd));
          if (href) {
            flush();
            out.push(_jsx2("a", { className: "pc-md_link", href, target: href.startsWith("#") ? void 0 : "_blank", rel: "noopener noreferrer", children: highlight ? highlightInline(label, highlight, false) : label }, `link:${i}`));
            i = hrefEnd + 1;
            continue;
          }
        }
      }
    }
    if (ch === "`") {
      const j = s.indexOf("`", i + 1);
      if (j !== -1) {
        flush();
        const inner = s.slice(i + 1, j);
        out.push(_jsx2("code", { children: highlight ? highlightInline(inner, highlight) : textLinks(inner) }, `code:${i}`));
        i = j + 1;
        continue;
      }
    }
    if (ch === "_" && !isWordChar(s[i - 1])) {
      const marker = s[i + 1] === "_" ? "__" : "_";
      const n = marker.length;
      if (s[i + n] && !/\s/.test(s[i + n]) && s[i + n] !== "_") {
        let j = s.indexOf(marker, i + n);
        while (j !== -1 && (/\s/.test(s[j - 1] || " ") || isWordChar(s[j + n]) || n === 1 && s[j + 1] === "_"))
          j = s.indexOf(marker, j + 1);
        if (j !== -1 && j > i + n) {
          flush();
          const inner = s.slice(i + n, j);
          const nodes = renderInline(inner, highlight);
          out.push(n === 2 ? _jsx2("strong", { children: nodes }, `ubold:${i}`) : _jsx2("em", { children: nodes }, `uem:${i}`));
          i = j + n;
          continue;
        }
      }
    }
    if (ch === "*" && s[i + 1] === "*") {
      const j = s.indexOf("**", i + 2);
      if (j !== -1) {
        flush();
        const inner = s.slice(i + 2, j);
        out.push(_jsx2("strong", { children: highlight ? highlightInline(inner, highlight) : textLinks(inner) }, `bold:${i}`));
        i = j + 2;
        continue;
      }
    }
    if (ch === "*" && s[i + 1] !== "*") {
      const j = s.indexOf("*", i + 1);
      if (j !== -1) {
        flush();
        const inner = s.slice(i + 1, j);
        out.push(_jsx2("em", { children: highlight ? highlightInline(inner, highlight) : textLinks(inner) }, `em:${i}`));
        i = j + 1;
        continue;
      }
    }
    buf += ch;
    i += 1;
  }
  flush();
  return out;
}
function normalizeLines(text) {
  const s = String(text ?? "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  return s.split("\n");
}
function parseListItemLine(line) {
  const s = String(line ?? "");
  const m = s.match(/^([ \t]*)(?:([-*+])|(\d{1,9})[.)])\s+(.*)$/);
  if (!m)
    return null;
  const indent = m[1].replace(/\t/g, "    ").length;
  return {
    indent,
    ordered: Boolean(m[3]),
    start: m[3] ? Math.max(1, parseInt(m[3], 10) || 1) : 1,
    content: m[4] ?? ""
  };
}
function buildListTree(itemLines) {
  const entries = [];
  for (const raw of itemLines) {
    const item = parseListItemLine(raw);
    if (item) {
      entries.push(item);
    } else if (entries.length > 0 && raw.trim()) {
      entries[entries.length - 1].content += ` ${raw.trim()}`;
    }
  }
  const roots = [];
  const stack = [];
  for (const e of entries) {
    while (stack.length > 0 && e.indent < stack[stack.length - 1].indent)
      stack.pop();
    let top = stack.length > 0 ? stack[stack.length - 1] : null;
    if (top && e.indent > top.indent) {
      const parentItems = top.node.items;
      const parent = parentItems[parentItems.length - 1];
      if (parent) {
        const node = { ordered: e.ordered, start: e.start, items: [] };
        parent.children.push(node);
        stack.push({ indent: e.indent, node });
        top = stack[stack.length - 1];
      }
    } else if (top && top.node.ordered !== e.ordered) {
      stack.pop();
      const up = stack.length > 0 ? stack[stack.length - 1] : null;
      const node = { ordered: e.ordered, start: e.start, items: [] };
      if (up) {
        const parentItems = up.node.items;
        const parent = parentItems[parentItems.length - 1];
        if (parent)
          parent.children.push(node);
        else
          up.node.items.push({ content: "", children: [node] });
      } else {
        roots.push(node);
      }
      stack.push({ indent: e.indent, node });
      top = stack[stack.length - 1];
    }
    if (!top) {
      const node = { ordered: e.ordered, start: e.start, items: [] };
      roots.push(node);
      stack.push({ indent: e.indent, node });
      top = stack[stack.length - 1];
    }
    top.node.items.push({ content: e.content, children: [] });
  }
  return roots;
}
function renderListNode(node, highlight, key) {
  const children = node.items.map((it, idx) => _jsxs2("li", { children: [renderInline(it.content, highlight), it.children.map((child, cIdx) => renderListNode(child, highlight, `${key}:${idx}:${cIdx}`))] }, `${key}:li:${idx}`));
  return node.ordered ? _jsx2("ol", { className: "pc-md_ol", start: node.start !== 1 ? node.start : void 0, children }, key) : _jsx2("ul", { className: "pc-md_ul", children }, key);
}
function renderListRegion(itemLines, highlight, keyBase) {
  return buildListTree(itemLines).map((root, idx) => renderListNode(root, highlight, `${keyBase}:${idx}`));
}
function splitTableRow(line) {
  let s = String(line ?? "").trim();
  if (!s)
    return [];
  if (s.startsWith("|"))
    s = s.slice(1);
  if (s.endsWith("|"))
    s = s.slice(0, -1);
  return s.split("|").map((c) => String(c ?? "").trim());
}
function isTableSeparator(line) {
  let s = String(line ?? "").trim();
  if (!s)
    return false;
  if (s.startsWith("|"))
    s = s.slice(1);
  if (s.endsWith("|"))
    s = s.slice(0, -1);
  const cells = s.split("|").map((c) => String(c ?? "").trim());
  if (cells.length < 2)
    return false;
  return cells.every((c) => /^:?-{3,}:?$/.test(c));
}
var HEADING_RE = /^(#{1,5})\s+(.*)$/;
function isFenceLine(line) {
  return line.trim().startsWith("```");
}
function isQuoteLine(line) {
  return line.trimStart().startsWith(">");
}
function Markdown(props) {
  const previous = inlineImagePolicy;
  inlineImagePolicy = props.images === "link" ? props.inlineImage || sameOriginImage : null;
  try {
    return renderMarkdown(props);
  } finally {
    inlineImagePolicy = previous;
  }
}
function renderMarkdown({ text, className, highlight, highlights, highlightClassName, highlightId }) {
  const lines = normalizeLines(text);
  const blocks = [];
  const needlesRaw = [];
  if (Array.isArray(highlights))
    needlesRaw.push(...highlights);
  if (typeof highlight === "string" && highlight.trim())
    needlesRaw.push(highlight);
  const needles = Array.from(new Set(needlesRaw.map((s) => String(s ?? "").trim()).filter(Boolean))).filter((n) => n.length >= 4);
  const highlightState = needles.length ? {
    needles,
    needlesLower: needles.map((n) => n.toLowerCase()),
    className: highlightClassName || "pc-md_hl",
    id: highlightId,
    hits: 0
  } : null;
  let i = 0;
  while (i < lines.length) {
    const line = String(lines[i] ?? "");
    if (!line.trim()) {
      i += 1;
      continue;
    }
    const hr = line.trim();
    if (/^([-_*])(\s*\1){2,}$/.test(hr)) {
      blocks.push(_jsx2("hr", { className: "pc-md_hr" }, `hr:${i}`));
      i += 1;
      continue;
    }
    const imageM = line.match(/^\s*!\[([^\]]*)\]\(([^)]+)\)\s*$/);
    if (imageM) {
      const src = safeImageSrc(imageM[2] || "");
      if (src && inlineImagePolicy && !inlineImagePolicy(src)) {
        blocks.push(_jsx2("p", { className: "pc-md_p", children: imageLink(`img:${i}`, src, imageM[1] || "") }, `p:${i}`));
        i += 1;
        continue;
      }
      if (src) {
        const alt = imageM[1] || "";
        blocks.push(_jsxs2("figure", { className: "pc-md_figure", children: [_jsx2("img", { className: "pc-md_img", src, alt, loading: "lazy" }), alt ? _jsx2("figcaption", { children: renderInline(alt, highlightState) }) : null] }, `figure:${i}`));
        i += 1;
        continue;
      }
    }
    if (isFenceLine(line)) {
      const fence = line.trim();
      const lang = fence.replace(/```/g, "").trim();
      const codeLines = [];
      i += 1;
      while (i < lines.length && !String(lines[i] ?? "").trim().startsWith("```")) {
        codeLines.push(String(lines[i] ?? ""));
        i += 1;
      }
      if (i < lines.length)
        i += 1;
      const code = codeLines.join("\n");
      blocks.push(_jsx2(MarkdownCodeBlock, { code, lang }, `pre:${i}`));
      continue;
    }
    const headingM = line.match(HEADING_RE);
    if (headingM) {
      const level = headingM[1].length;
      const content = headingM[2] || "";
      const nodes = renderInline(content, highlightState);
      if (level === 1)
        blocks.push(_jsx2("h1", { children: nodes }, `h1:${i}`));
      else if (level === 2)
        blocks.push(_jsx2("h2", { children: nodes }, `h2:${i}`));
      else if (level === 3)
        blocks.push(_jsx2("h3", { children: nodes }, `h3:${i}`));
      else if (level === 4)
        blocks.push(_jsx2("h4", { children: nodes }, `h4:${i}`));
      else
        blocks.push(_jsx2("h5", { children: nodes }, `h5:${i}`));
      i += 1;
      continue;
    }
    if (isQuoteLine(line)) {
      const quoteLines = [];
      while (i < lines.length && String(lines[i] ?? "").trimStart().startsWith(">")) {
        const raw = String(lines[i] ?? "");
        const t = raw.trimStart();
        quoteLines.push(t.replace(/^>\s?/, ""));
        i += 1;
      }
      blocks.push(_jsx2("blockquote", { className: "pc-md_quote", children: quoteLines.map((q, idx) => _jsxs2(React.Fragment, { children: [renderInline(q, highlightState), idx < quoteLines.length - 1 ? _jsx2("br", {}) : null] }, `q:${i}:${idx}`)) }, `quote:${i}`));
      continue;
    }
    if (line.includes("|") && i + 1 < lines.length && isTableSeparator(String(lines[i + 1] ?? ""))) {
      const headers = splitTableRow(line);
      const colCount = Math.max(1, headers.length);
      const rows = [];
      i += 2;
      while (i < lines.length) {
        const rowLine = String(lines[i] ?? "");
        if (!rowLine.trim())
          break;
        if (!rowLine.includes("|"))
          break;
        const cells = splitTableRow(rowLine);
        const normalized = [];
        for (let c = 0; c < colCount; c++)
          normalized.push(cells[c] ?? "");
        rows.push(normalized);
        i += 1;
      }
      blocks.push(_jsx2("div", { className: "pc-md_table_wrap", children: _jsxs2("table", { className: "pc-md_table", children: [_jsx2("thead", { children: _jsx2("tr", { children: headers.slice(0, colCount).map((h, idx) => _jsx2("th", { children: renderInline(h, highlightState) }, `th:${i}:${idx}`)) }) }), _jsx2("tbody", { children: rows.map((r, rIdx) => _jsx2("tr", { children: r.map((cell, cIdx) => _jsx2("td", { children: renderInline(cell, highlightState) }, `td:${i}:${rIdx}:${cIdx}`)) }, `tr:${i}:${rIdx}`)) })] }) }, `table:${i}`));
      continue;
    }
    if (parseListItemLine(line)) {
      const itemLines = [];
      while (i < lines.length) {
        const cur = String(lines[i] ?? "");
        if (!cur.trim())
          break;
        if (cur.trimStart().startsWith("```"))
          break;
        if (parseListItemLine(cur) || /^\s{2,}\S/.test(cur)) {
          itemLines.push(cur);
          i += 1;
          continue;
        }
        break;
      }
      blocks.push(_jsx2(React.Fragment, { children: renderListRegion(itemLines, highlightState, `list:${i}`) }, `list:${i}`));
      continue;
    }
    const paraLines = [];
    while (i < lines.length && String(lines[i] ?? "").trim()) {
      if (paraLines.length > 0 && parseListItemLine(String(lines[i] ?? "")))
        break;
      const cur_line = String(lines[i] ?? "");
      if (paraLines.length > 0 && (HEADING_RE.test(cur_line) || isFenceLine(cur_line) || isQuoteLine(cur_line)))
        break;
      if (paraLines.length > 0 && cur_line.includes("|") && i + 1 < lines.length && isTableSeparator(String(lines[i + 1] ?? "")))
        break;
      paraLines.push(cur_line);
      i += 1;
    }
    blocks.push(_jsx2("p", { className: "pc-md_p", children: paraLines.map((pl, idx) => _jsxs2(React.Fragment, { children: [renderInline(pl, highlightState), idx < paraLines.length - 1 ? _jsx2("br", {}) : null] }, `pl:${i}:${idx}`)) }, `p:${i}`));
  }
  const cls = ["pc-md", className].filter(Boolean).join(" ");
  return _jsx2("div", { className: cls, children: blocks });
}

// dist/file_viewer.js
var PREVIEW_TEXT_LIMIT = 1024 * 1024;
var PREVIEW_BLOB_LIMIT = 25 * 1024 * 1024;
function FileViewer(props) {
  const { markdownImages, inlineImage, renderMarkdown: renderMarkdown2, ...rest } = props;
  return _jsx3(AfFileViewer, { ...rest, nowMs: props.nowMs ?? Date.now(), renderMarkdown: renderMarkdown2 || ((text) => _jsx3(Markdown, { text, ...markdownImages ? { images: markdownImages } : {}, ...inlineImage ? { inlineImage } : {} })) });
}

// dist/workspace_browser.js
async function gatewayResponseError(response, what) {
  let reason = "";
  try {
    const text = await response.text();
    try {
      const body = JSON.parse(text);
      const detail = body?.detail ?? body?.error ?? body?.message;
      reason = typeof detail === "string" ? detail : detail && typeof detail.message === "string" ? detail.message : text;
    } catch {
      reason = text;
    }
  } catch {
    reason = "";
  }
  return new Error(`${what} (HTTP ${response.status}): ${reason.trim() || response.statusText || "no reason given"}`);
}
function formatBytes(n) {
  if (typeof n !== "number" || !Number.isFinite(n) || n < 0)
    return "";
  if (n < 1024)
    return `${n} B`;
  const units = ["KiB", "MiB", "GiB", "TiB"];
  let v = n / 1024;
  let u = 0;
  while (v >= 1024 && u < units.length - 1) {
    v /= 1024;
    u += 1;
  }
  return `${v < 10 ? v.toFixed(1) : Math.round(v)} ${units[u]}`;
}
var TAB_SAFE_TYPES = /* @__PURE__ */ new Set(["image/png", "image/jpeg", "image/gif", "image/webp", "image/avif", "image/bmp", "application/pdf", "text/plain", "application/json"]);
function tabOpenPlan(contentType) {
  const type = String(contentType || "").split(";", 1)[0].trim().toLowerCase();
  if (TAB_SAFE_TYPES.has(type))
    return { mode: "open", type };
  if (type.startsWith("text/") || type.endsWith("+xml") || type.endsWith("+json") || type.endsWith("/xml") || type.endsWith("/javascript") || type.endsWith("/x-yaml") || type.endsWith("/toml"))
    return { mode: "open", type: "text/plain;charset=utf-8" };
  return { mode: "download" };
}
function deliverBlob(blob, name, mode) {
  const plan = mode === "open" ? tabOpenPlan(blob.type) : { mode: "download" };
  const safe = plan.mode === "open" && plan.type !== blob.type ? new Blob([blob], { type: plan.type }) : blob;
  const url = URL.createObjectURL(safe);
  if (plan.mode === "open") {
    window.open(url, "_blank", "noopener");
  } else {
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }
  window.setTimeout(() => URL.revokeObjectURL(url), 6e4);
}

// dist/attachment_uploads.js
async function runBounded(items, limit, worker) {
  let next = 0;
  const lanes = Array.from({ length: Math.max(1, Math.min(Math.floor(limit) || 1, items.length)) }, async () => {
    while (next < items.length) {
      const item = items[next];
      next += 1;
      await worker(item);
    }
  });
  await Promise.all(lanes);
}
var files = (count) => `${count} ${count === 1 ? "file" : "files"}`;
function unattachedSendBlock(items) {
  const waiting = items.filter((item) => item.state === "queued" || item.state === "uploading").length;
  if (waiting)
    return `Wait for ${files(waiting)} to finish uploading.`;
  const broken = items.filter((item) => item.state === "failed" || item.state === "refused");
  if (!broken.length)
    return null;
  const retryable = broken.some((item) => item.state === "failed");
  if (broken.length === 1)
    return `"${broken[0].name}" was not attached. ${retryable ? "Retry or remove" : "Remove"} it before sending.`;
  return `${files(broken.length)} were not attached. ${retryable ? "Retry or remove" : "Remove"} them before sending.`;
}

// dist/message_artifacts.js
var obj = (v) => v && typeof v === "object" && !Array.isArray(v) ? v : {};
function messageArtifactRefs(value, runId) {
  const refs = [], seen = /* @__PURE__ */ new Set();
  const walk = (v, depth = 0) => {
    if (depth > 8)
      return;
    if (Array.isArray(v)) {
      v.forEach((x) => walk(x, depth + 1));
      return;
    }
    const r = obj(v), id = r.$artifact || r.artifact_id;
    if (typeof id === "string" && id) {
      const owner = typeof r.run_id === "string" ? r.run_id : typeof r.artifact_run_id === "string" ? r.artifact_run_id : runId, key = JSON.stringify([owner, id]);
      if (!seen.has(key)) {
        seen.add(key);
        refs.push({
          id,
          runId: owner,
          ...typeof (r.filename || r.name) === "string" ? { name: String(r.filename || r.name) } : {}
        });
      }
      return;
    }
    Object.values(r).forEach((x) => {
      if (x && typeof x === "object")
        walk(x, depth + 1);
    });
  };
  walk(value);
  return refs;
}
function submittedArtifacts(body, runId) {
  const root = obj(body), input = obj(root.input_data || body), context = obj(input.context);
  return messageArtifactRefs([
    input.attachments,
    context.attachments,
    input.image_artifact,
    context.image_artifact
  ], runId);
}
function outputArtifacts(output, runId) {
  const r = obj(output);
  return messageArtifactRefs([
    r.attachments,
    r.artifacts,
    r.files,
    r.image_artifact,
    r.audio_artifact,
    r.video_artifact,
    r.music_artifact,
    obj(r.meta).attachments,
    obj(r.meta).files,
    obj(r.meta).artifacts,
    obj(r.meta).image_artifact,
    obj(r.meta).video_artifact,
    obj(r.meta).audio_artifact,
    obj(r.meta).music_artifact,
    ...r.result ? [
      obj(r.result).attachments,
      obj(r.result).artifacts,
      obj(r.result).files
    ] : []
  ], runId);
}
function useMessageArtifacts(messages, fetchGateway, scope, run) {
  const [attempt, setAttempt] = useState5(0);
  const cache = useRef3({ owner: scope, refs: /* @__PURE__ */ new Map(), outputs: /* @__PURE__ */ new Map() });
  if (cache.current.owner !== scope)
    cache.current = { owner: scope, refs: /* @__PURE__ */ new Map(), outputs: /* @__PURE__ */ new Map() };
  const signature = JSON.stringify([
    ...new Set(messages.filter((m) => m.role === "user" && m.runId).map((m) => m.runId))
  ]);
  const [inputs, setInputs] = useState5({ owner: scope, refs: {}, error: "" });
  useEffect5(() => {
    const abort = new AbortController(), ids = JSON.parse(signature).filter((id) => !cache.current.refs.has(id));
    const currentIds = new Set(JSON.parse(signature));
    for (const key of cache.current.refs.keys())
      if (!currentIds.has(key))
        cache.current.refs.delete(key);
    for (const key of cache.current.outputs.keys())
      if (!currentIds.has(key))
        cache.current.outputs.delete(key);
    setInputs({
      owner: scope,
      refs: Object.fromEntries(cache.current.refs),
      error: ""
    });
    if (!fetchGateway)
      return () => abort.abort();
    void runBounded(ids, 4, async (id) => {
      try {
        const response = await fetchGateway(gatewayApiPath3(`runs/${encodeURIComponent(id)}/input_data`), { signal: abort.signal });
        if (!response.ok)
          throw await gatewayResponseError(response, "Message attachments could not be checked");
        const refs = submittedArtifacts(await response.json(), id);
        if (!abort.signal.aborted && cache.current.owner === scope) {
          cache.current.refs.set(id, refs);
          setInputs((old) => ({ ...old, refs: { ...old.refs, [id]: refs } }));
        }
      } catch (e) {
        if (!abort.signal.aborted && cache.current.owner === scope)
          setInputs((old) => ({
            ...old,
            error: e instanceof Error ? e.message : String(e)
          }));
      }
    });
    return () => abort.abort();
  }, [fetchGateway, scope, signature, attempt]);
  const missing = JSON.stringify(JSON.parse(signature).filter((id) => !messages.some((m) => m.runId === id && m.role === "assistant")));
  const [restored, setRestored] = useState5({ owner: scope, files: {}, error: "" });
  useEffect5(() => {
    const abort = new AbortController();
    setRestored((old) => old.owner === scope ? { ...old, error: "" } : { owner: scope, files: {}, error: "" });
    if (fetchGateway)
      void runBounded(JSON.parse(missing).filter((id) => !cache.current.outputs.has(id)), 4, async (id) => {
        if (id === run?.runId && outputArtifacts(run.output, id).length)
          return;
        try {
          const response = await fetchGateway(gatewayApiPath3(`runs/${encodeURIComponent(id)}`), { signal: abort.signal });
          if (!response.ok)
            throw await gatewayResponseError(response, "Attached reply could not be checked");
          const body = obj(await response.json());
          const files2 = body.status === "completed" ? outputArtifacts(body.output, id) : [];
          if (!abort.signal.aborted && cache.current.owner === scope) {
            if (["completed", "failed", "cancelled"].includes(String(body.status)))
              cache.current.outputs.set(id, files2);
            setRestored((old) => old.owner === scope ? { ...old, files: { ...old.files, [id]: files2 } } : old);
          }
        } catch (e) {
          if (!abort.signal.aborted)
            setRestored((old) => old.owner === scope ? {
              ...old,
              error: e instanceof Error ? e.message : String(e)
            } : old);
        }
      });
    return () => abort.abort();
  }, [fetchGateway, scope, missing, run?.runId, run?.output, attempt]);
  const shown = useMemo2(() => {
    const inputShown = /* @__PURE__ */ new Set();
    const list = messages.map((m) => {
      const originalPrompt = m.role === "user" && Boolean(m.runId) && !inputShown.has(m.runId);
      if (originalPrompt)
        inputShown.add(m.runId);
      const submitted = originalPrompt && inputs.owner === scope ? inputs.refs[m.runId || ""] || [] : [];
      const refs = [
        ...m.artifactRefs || [],
        ...(m.artifactIds || []).filter((id) => ![...m.artifactRefs || [], ...submitted].some((r) => r.id === id)).map((id) => ({ id, runId: m.runId || "" })),
        ...submitted
      ];
      const unique = [
        ...new Map(refs.filter((r) => r.id && r.runId).map((r) => [JSON.stringify([r.runId, r.id]), r])).values()
      ];
      return unique.length ? { ...m, artifactRefs: unique } : m;
    });
    const visibleRuns = new Set(messages.map((message) => message.runId));
    const outcomes = [
      ...restored.owner === scope ? Object.entries(restored.files).filter(([id]) => visibleRuns.has(id)) : [],
      ...run ? [
        [run.runId, outputArtifacts(run.output, run.runId)]
      ] : []
    ];
    for (const [outputRunId, refs] of outcomes) {
      if (refs.length) {
        let i = -1;
        for (let j = list.length - 1; j >= 0; j--)
          if (list[j].role === "assistant" && list[j].runId === outputRunId && !list[j].live) {
            i = j;
            break;
          }
        if (i < 0) {
          const after = list.reduce((last, message, index) => message.runId === outputRunId ? index : last, -1);
          list.splice(after + 1, 0, {
            id: `attachments:${outputRunId}`,
            kind: "attachments",
            role: "assistant",
            runId: outputRunId,
            content: "",
            artifactRefs: refs
          });
        } else
          list[i] = {
            ...list[i],
            artifactRefs: [
              ...new Map([...list[i].artifactRefs || [], ...refs].map((r) => [
                JSON.stringify([r.runId, r.id]),
                r
              ])).values()
            ]
          };
      }
    }
    return list;
  }, [messages, inputs, restored, scope, run?.runId, run?.output]);
  return {
    messages: shown,
    error: [
      inputs.owner === scope ? inputs.error : "",
      restored.owner === scope ? restored.error : ""
    ].filter(Boolean).join(" "),
    retry: () => setAttempt((n) => n + 1)
  };
}
var ArtifactFetchContext = createContext(void 0);
function MessageArtifactChip({ artifact }) {
  const fetchGateway = useContext(ArtifactFetchContext), [name, setName] = useState5(artifact.name || `Attachment ${artifact.id}`), [error, setError] = useState5(""), [busy, setBusy] = useState5(false), action = useRef3(null);
  const path = gatewayApiPath3(`runs/${encodeURIComponent(artifact.runId)}/artifacts/${encodeURIComponent(artifact.id)}`);
  useEffect5(() => {
    const abort = new AbortController();
    setName(artifact.name || `Attachment ${artifact.id}`);
    setError("");
    setBusy(false);
    if (fetchGateway)
      void fetchGateway(path, { signal: abort.signal }).then(async (r) => {
        if (!r.ok)
          throw await gatewayResponseError(r, "Attachment unavailable");
        const meta = await r.json(), tags = obj(meta.tags), descriptor = obj(meta.descriptor), envelope = obj(meta.artifact_envelope_v1);
        const value = meta.filename || meta.name || tags.filename || descriptor.name || envelope.name;
        if (!abort.signal.aborted && typeof value === "string")
          setName(value);
      }).catch((e) => {
        if (!abort.signal.aborted)
          setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      abort.abort();
      action.current?.abort();
    };
  }, [fetchGateway, path, artifact.name]);
  return _jsxs4("span", { className: "pc-message-artifact", children: [_jsxs4("button", { type: "button", className: "pc-chat-attachment-chip", disabled: !fetchGateway || busy, onClick: async () => {
    if (!fetchGateway)
      return;
    const abort = new AbortController();
    action.current = abort;
    setBusy(true);
    setError("");
    try {
      const r = await fetchGateway(`${path}/content`, {
        signal: abort.signal
      });
      if (!r.ok)
        throw await gatewayResponseError(r, "Attachment could not be opened");
      const blob = await r.blob();
      if (!abort.signal.aborted)
        deliverBlob(blob, name, "open");
    } catch (e) {
      if (!abort.signal.aborted)
        setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (!abort.signal.aborted)
        setBusy(false);
    }
  }, children: [_jsx5(Icon3, { name: "paperclip", size: 14 }), _jsx5("span", { className: "pc-chat-attachment-name", children: name }), busy && " \xB7 Opening\u2026"] }), error && _jsxs4("span", { role: "status", className: "pc-message-artifact__error", children: [error, " ", _jsx5("span", { children: "Click the attachment to retry." })] })] });
}
function boundedArtifactFetch(fetchGateway) {
  let active = 0;
  const queue = [];
  const next = () => {
    while (active < 4 && queue.length)
      queue.shift()();
  };
  return (path, init = {}) => new Promise((resolve, reject) => {
    const signal = init.signal;
    let queued = true;
    const abort = () => {
      if (queued) {
        queued = false;
        reject(new DOMException("Aborted", "AbortError"));
      }
    };
    signal?.addEventListener("abort", abort, { once: true });
    if (signal?.aborted)
      abort();
    queue.push(() => {
      signal?.removeEventListener("abort", abort);
      if (!queued)
        return;
      queued = false;
      active++;
      Promise.resolve().then(() => fetchGateway(path, init)).then(resolve, reject).finally(() => {
        active--;
        next();
      });
    });
    next();
  });
}

// dist/workflow_chat.js
import { useEffect as useEffect12, useMemo as useMemo7, useRef as useRef8, useState as useState13 } from "react";
import { Icon as Icon8, useAfTooltips } from "@abstractframework/ui-kit";

// dist/chat_composer.js
import { jsx as _jsx6, jsxs as _jsxs5 } from "react/jsx-runtime";
import React3 from "react";
var ChatComposer = React3.forwardRef(function ChatComposer2(props, ref) {
  const rows = typeof props.rows === "number" && Number.isFinite(props.rows) ? Math.max(1, Math.trunc(props.rows)) : 3;
  const disabled = Boolean(props.disabled);
  const busy = Boolean(props.busy);
  const can_submit = !disabled && !busy && Boolean(String(props.value || "").trim());
  return _jsxs5("div", { className: ["pc-composer", props.className].filter(Boolean).join(" "), children: [props.leading, _jsx6("textarea", {
    ref,
    className: ["pc-composer__textarea", props.textareaClassName].filter(Boolean).join(" "),
    value: props.value,
    onChange: (e) => props.onChange(e.target.value),
    rows,
    // The textarea auto-grows (CSS field-sizing) from `rows` lines up to a
    // viewport-relative cap; the row count reaches the CSS as a variable.
    style: { ["--pc-composer-rows"]: String(rows) },
    spellCheck: false,
    autoCorrect: "off",
    autoCapitalize: "off",
    autoComplete: "off",
    placeholder: props.placeholder || "",
    "aria-label": props.ariaLabel || props.placeholder || "Message",
    disabled,
    autoFocus: Boolean(props.autoFocus),
    onPaste: props.onPaste,
    onKeyDown: (e) => {
      if (e.key !== "Enter" || e.shiftKey)
        return;
      if (e.nativeEvent.isComposing || e.keyCode === 229)
        return;
      e.preventDefault();
      if (!can_submit)
        return;
      props.onSubmit();
    }
  }), _jsxs5("div", { className: "pc-composer__row", children: [_jsx6("div", { className: "pc-composer__actions", children: props.actions }), _jsx6("button", { type: "button", className: props.sendButtonClassName || "pc-btn", disabled: !can_submit, onClick: () => props.onSubmit(), children: busy ? props.busyLabel || "Thinking\u2026" : props.sendLabel || "Send" })] }), props.overlay] });
});

// dist/chat_thread.js
import { jsx as _jsx13, jsxs as _jsxs11 } from "react/jsx-runtime";
import { useEffect as useEffect10, useMemo as useMemo6, useRef as useRef6, useState as useState11 } from "react";

// dist/chat_message_card.js
import { jsx as _jsx12, jsxs as _jsxs10 } from "react/jsx-runtime";
import { useEffect as useEffect9, useMemo as useMemo5, useRef as useRef5, useState as useState10 } from "react";
import { AfAudioPlayer, Icon as Icon5, fileViewerKind as fileViewerKind3, fileViewerNeedsText as fileViewerNeedsText2, formatFileSize as formatFileSize2 } from "@abstractframework/ui-kit";

// dist/chat_media.js
import { fileViewerKind as fileViewerKind2 } from "@abstractframework/ui-kit";
var ACTIVE_EXT = new Set("html htm xhtml xht shtml svg svgz xml xsl xslt mht mhtml".split(" "));
var INERT_TYPES = /* @__PURE__ */ new Set([
  "application/pdf",
  "application/json",
  "text/plain",
  "text/markdown",
  "text/csv",
  "text/tab-separated-values",
  "text/x-python",
  "text/javascript",
  "application/javascript",
  "text/css",
  "text/x-c",
  "text/x-shellscript",
  "text/x-typescript",
  "image/png",
  "image/jpeg",
  "image/gif",
  "image/webp",
  "image/avif",
  "image/bmp",
  // Concrete media subtypes only: WebKit renders an unsupported subtype
  // (video/html, audio/text, ...) as a document and runs its script (review N1c),
  // and a type it cannot play too (video/ogg, audio/opus: left out, N1d). This list
  // is defence in depth: every blob:/data: raw link is a download (chat_message_card).
  "video/mp4",
  "video/webm",
  "video/quicktime",
  "audio/mpeg",
  "audio/mp4",
  "audio/aac",
  "audio/wav",
  "audio/x-wav",
  "audio/ogg",
  "audio/webm",
  "audio/flac"
]);
function isLocalObjectUrl(url) {
  const value = String(url ?? "");
  if (!value.trim())
    return false;
  try {
    const base = typeof window !== "undefined" && window.location ? window.location.href : "http://same-origin.invalid/";
    const protocol = new URL(value, base).protocol;
    return protocol === "blob:" || protocol === "data:";
  } catch {
    return true;
  }
}
function objectUrlRawLinkSafe(contentType, name) {
  const base = String(name || "").split("/").pop() || "";
  const dot = base.lastIndexOf(".");
  if (dot > 0 && ACTIVE_EXT.has(base.slice(dot + 1).toLowerCase()))
    return false;
  const type = String(contentType || "").split(";", 1)[0].trim().toLowerCase();
  if (!type || type === "text/html" || type.includes("xml"))
    return false;
  return INERT_TYPES.has(type);
}
function fileRawLink(item) {
  const allowed = (url) => Boolean(url) && (!isLocalObjectUrl(url) || objectUrlRawLinkSafe(item.contentType, item.name));
  if (allowed(item.href))
    return item.href;
  if (allowed(item.src))
    return item.src;
  return void 0;
}

// dist/message_content.js
import { jsx as _jsx8 } from "react/jsx-runtime";
import { useMemo as useMemo4 } from "react";

// dist/json_viewer.js
import { jsx as _jsx7, jsxs as _jsxs6, Fragment as _Fragment3 } from "react/jsx-runtime";
import { useEffect as useEffect6, useMemo as useMemo3, useState as useState6 } from "react";
var FOLDED_DEPTH = 3;
var UNFOLDED_DEPTH = Number.MAX_SAFE_INTEGER;
function isJsonObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
function isJsonArray(value) {
  return Array.isArray(value);
}
function copyStringForJson(value) {
  if (value == null)
    return "";
  if (typeof value === "string")
    return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}
function Token({ kind, children }) {
  return _jsx7("span", { className: `pc-json-token ${kind}`, children });
}
function JsonStringValue(props) {
  const rendered = JSON.stringify(props.value);
  const isUrl = /^https?:\/\/[^\s]+$/i.test(props.value);
  const collapsible = !isUrl && (rendered.length > 96 || rendered.includes("\\n") || rendered.includes("\\r") || rendered.includes("\\t"));
  const [open, setOpen] = useState6(!collapsible || props.expansionMode === "unfolded");
  useEffect6(() => {
    if (!collapsible)
      return;
    setOpen(props.expansionMode === "unfolded");
  }, [collapsible, props.expansionMode, props.expansionVersion]);
  if (!collapsible)
    return _jsx7("span", { className: "pc-json-token string", children: _jsx7(JsonTextLinks, { text: props.value }) });
  return _jsxs6("span", { className: `pc-json-string ${open ? "open" : "collapsed"}`, children: [_jsx7("button", { type: "button", className: "pc-json-string__toggle", onClick: () => setOpen((v) => !v), "aria-label": open ? "Collapse string value" : "Expand string value", "aria-expanded": open, children: open ? "\u25BE" : "\u25B8" }), open ? _jsx7("span", { className: "pc-json-token string pc-json-string__value", children: _jsx7(JsonTextLinks, { text: props.value }) }) : _jsxs6("span", { className: "pc-json-string__preview", children: [_jsx7("span", { className: "pc-json-token string pc-json-string__preview_text", children: _jsx7(JsonTextLinks, { text: props.value }) }), _jsx7("button", { type: "button", className: "pc-json-string__suffix", onClick: () => setOpen(true), "aria-label": "Expand string value", children: "(...)" })] })] });
}
function renderPrimitive(value, expansionMode, expansionVersion) {
  if (value === null)
    return _jsx7(Token, { kind: "null", children: "null" });
  if (typeof value === "string")
    return _jsx7(JsonStringValue, { value, expansionMode, expansionVersion });
  if (typeof value === "number")
    return _jsx7(Token, { kind: "number", children: String(value) });
  if (typeof value === "boolean")
    return _jsx7(Token, { kind: "boolean", children: value ? "true" : "false" });
  return _jsx7(Token, { kind: "string", children: JSON.stringify(String(value)) });
}
function countSummary(value) {
  if (isJsonArray(value))
    return value.length === 1 ? "1 item" : `${value.length} items`;
  if (isJsonObject(value))
    return Object.keys(value).length === 1 ? "1 key" : `${Object.keys(value).length} keys`;
  return "";
}
function JsonNode(props) {
  const { label, value, depth, collapseAfterDepth, expansionMode, expansionVersion, trailingComma } = props;
  const indentPx = depth * 14;
  const isObject = isJsonObject(value);
  const isArray = isJsonArray(value);
  const isContainer = isObject || isArray;
  const defaultOpen = depth < collapseAfterDepth;
  const [open, setOpen] = useState6(defaultOpen);
  useEffect6(() => {
    setOpen(defaultOpen);
  }, [defaultOpen, expansionVersion]);
  const prefix = label ? _jsxs6(_Fragment3, { children: [_jsx7(Token, { kind: "key", children: JSON.stringify(label) }), ": "] }) : null;
  if (!isContainer) {
    return _jsxs6("div", { className: "pc-json-viewer__line", style: { paddingLeft: indentPx }, children: [prefix, renderPrimitive(value, expansionMode, expansionVersion), trailingComma ? "," : ""] });
  }
  const containerOpen = isArray ? "[" : "{";
  const containerClose = isArray ? "]" : "}";
  const summaryText = countSummary(value);
  const summaryValue = open ? `${containerOpen}` : `${containerOpen}\u2026${containerClose}${summaryText ? `  (${summaryText})` : ""}`;
  const entries = isArray ? value.map((v, i) => ({
    key: String(i),
    label: void 0,
    value: v
  })) : Object.entries(value).map(([k, v]) => ({
    key: k,
    label: k,
    value: v
  }));
  return _jsxs6("details", { className: "pc-json-viewer__details", open, onToggle: (e) => setOpen(e.currentTarget.open), children: [_jsxs6("summary", { className: "pc-json-viewer__summary", style: { paddingLeft: indentPx }, children: [prefix, _jsx7("span", { className: "pc-json-viewer__caret", "aria-hidden": "true", children: open ? "\u25BE" : "\u25B8" }), _jsx7("span", { className: "pc-json-viewer__punct", children: summaryValue }), !open && trailingComma ? _jsx7("span", { className: "pc-json-viewer__punct", children: "," }) : null] }), open ? _jsx7("div", { className: "pc-json-viewer__children", children: entries.length === 0 ? _jsxs6("div", { className: "pc-json-viewer__line", style: { paddingLeft: indentPx }, children: [_jsx7("span", { className: "pc-json-viewer__punct", children: containerClose }), trailingComma ? "," : ""] }) : _jsxs6(_Fragment3, { children: [entries.map((e, idx) => {
    const isLast = idx === entries.length - 1;
    return _jsx7(JsonNode, { label: e.label, value: e.value, depth: depth + 1, collapseAfterDepth, expansionMode, expansionVersion, trailingComma: !isLast }, `${depth}:${label || "root"}:${e.key}`);
  }), _jsxs6("div", { className: "pc-json-viewer__line", style: { paddingLeft: indentPx }, children: [_jsx7("span", { className: "pc-json-viewer__punct", children: containerClose }), trailingComma ? "," : ""] })] }) }) : null] });
}
function tryParseJsonString(value) {
  const trimmed = value.trim();
  if (!trimmed)
    return value;
  if (trimmed.startsWith("{") && trimmed.endsWith("}") || trimmed.startsWith("[") && trimmed.endsWith("]")) {
    try {
      return JSON.parse(trimmed);
    } catch {
      return value;
    }
  }
  return value;
}
function JsonViewer(props) {
  const { value, className, showCopy = true } = props;
  const [expansion, setExpansion] = useState6({ mode: "folded", version: 0 });
  const [copyState, setCopyState] = useState6("idle");
  const foldedDepth = typeof props.collapseAfterDepth === "number" && (Number.isFinite(props.collapseAfterDepth) || props.collapseAfterDepth === Infinity) && props.collapseAfterDepth >= 0 ? props.collapseAfterDepth === Infinity ? Number.MAX_SAFE_INTEGER : Math.trunc(props.collapseAfterDepth) : FOLDED_DEPTH;
  const collapseAfterDepth = expansion.mode === "unfolded" ? UNFOLDED_DEPTH : foldedDepth;
  const displayValue = useMemo3(() => typeof value === "string" ? tryParseJsonString(value) : value, [value]);
  const copyValue = useMemo3(() => copyStringForJson(value), [value]);
  const cls = ["pc-json-viewer", className].filter(Boolean).join(" ");
  useEffect6(() => {
    setExpansion((prev) => ({ mode: "folded", version: prev.version + 1 }));
  }, [displayValue]);
  const toggleExpansion = () => {
    setExpansion((prev) => ({
      mode: prev.mode === "unfolded" ? "folded" : "unfolded",
      version: prev.version + 1
    }));
  };
  return _jsxs6("div", { className: cls, children: [_jsxs6("div", { className: "pc-json-viewer__toolbar", children: [_jsx7("button", { type: "button", className: "pc-btn pc-json-viewer__toggle-all", onClick: toggleExpansion, "aria-expanded": expansion.mode === "unfolded", children: expansion.mode === "unfolded" ? "Fold all" : "Unfold all" }), showCopy ? _jsx7("button", { type: "button", className: "pc-btn pc-json-viewer__copy", onClick: () => void copyText(copyValue).then((ok) => {
    setCopyState(ok ? "copied" : "failed");
    window.setTimeout(() => setCopyState("idle"), 2e3);
  }), children: copyState === "copied" ? "Copied" : copyState === "failed" ? "Copy failed \u2014 select and copy" : "Copy JSON" }) : null] }), _jsx7("div", { className: "pc-json-viewer__tree", role: "tree", "aria-label": "JSON viewer", children: _jsx7(JsonNode, { value: displayValue, depth: 0, collapseAfterDepth, expansionMode: expansion.mode, expansionVersion: expansion.version, trailingComma: false }) })] });
}

// dist/message_content.js
function ChatMessageContent(props) {
  const text = String(props.text ?? "");
  const parsed = useMemo4(() => tryParseJson(text), [text]);
  const cls = ["pc-chat-content", props.className].filter(Boolean).join(" ");
  if (parsed !== null) {
    return _jsx8("div", { className: cls, children: _jsx8(JsonViewer, { value: parsed, collapseAfterDepth: props.jsonCollapseAfterDepth }) });
  }
  if (props.renderMarkdown) {
    return _jsx8("div", { className: cls, children: props.renderMarkdown(text) });
  }
  return _jsx8("div", { className: cls, children: _jsx8(Markdown, { text, images: props.images, inlineImage: props.inlineImage }) });
}

// dist/tool_activity.js
import { jsx as _jsx11, Fragment as _Fragment5, jsxs as _jsxs9 } from "react/jsx-runtime";
import React5, { useState as useState8 } from "react";
import { Icon as Icon4 } from "@abstractframework/ui-kit";

// dist/sandbox_line.js
import { jsx as _jsx9, jsxs as _jsxs7 } from "react/jsx-runtime";
function ToolSandboxLine({ sandbox, className }) {
  if (!sandbox)
    return null;
  return _jsxs7("div", { className: `pc-tool-sandbox is-${sandbox.state}${className ? ` ${className}` : ""}`, "data-sandbox-kind": sandbox.kind, children: [_jsx9("div", { className: "pc-tool-sandbox__line", children: sandbox.line }), sandbox.rows.length ? _jsxs7("ul", { className: "pc-tool-sandbox__rows", "aria-label": "Workspaces the sandbox enforced", children: [sandbox.rows.map((row, i) => _jsxs7("li", { children: [_jsx9("code", { children: row.path }), _jsx9("span", { className: "pc-tool-sandbox__mode", children: row.private ? `${row.mode} \xB7 this run's folder` : row.mode })] }, `${row.mode}:${row.path}:${i}`)), sandbox.builtinRefused ? _jsxs7("li", { className: "pc-tool-sandbox__builtin", children: [sandbox.builtinRefused, " built-in protected ", sandbox.builtinRefused === 1 ? "folder" : "folders", " refused"] }) : null] }) : null] });
}

// dist/tool_policy.js
import { formatExactTime as formatExactTime2 } from "@abstractframework/ui-kit";
function toolPolicyDecisionText(provenance) {
  if (provenance.decision === "denied")
    return "Denied by this chat's policy";
  const at = provenance.setAt ? formatExactTime2(provenance.setAt) : "";
  const by = provenance.setBy ? `set by ${provenance.setBy}` : "";
  const detail = [by, at ? `at ${at}` : ""].filter(Boolean).join(" ");
  return `Allowed by this chat's policy${detail ? ` (${detail})` : ""}`;
}

// dist/stat_detail.js
import { jsx as _jsx10, jsxs as _jsxs8, Fragment as _Fragment4 } from "react/jsx-runtime";
import React4, { useCallback as useCallback2, useEffect as useEffect7, useId, useLayoutEffect, useRef as useRef4, useState as useState7 } from "react";
import { createPortal } from "react-dom";
var NR = "not reported";
var n0 = (n) => n === void 0 ? NR : Math.round(n).toLocaleString();
var formatDuration = (ms) => {
  if (ms === void 0)
    return NR;
  if (ms < 6e4)
    return `${(ms / 1e3).toFixed(1)}s`;
  const total = Math.round(ms / 1e3);
  return `${Math.floor(total / 60)}m ${String(total % 60).padStart(2, "0")}s`;
};
var rate = (n) => n === void 0 ? NR : `${Math.round(n).toLocaleString()} tok/s`;
var pct = (part, whole) => whole > 0 ? `${Math.round(part / whole * 100)}%` : "";
var plural = (n, one, many = `${one}s`) => `${n.toLocaleString()} ${n === 1 ? one : many}`;
var shortModel = (model) => {
  const clean = model.split("#")[0].replace(/\/+$/, "");
  return clean.slice(clean.lastIndexOf("/") + 1) || model;
};
function tally(values) {
  const counts = /* @__PURE__ */ new Map();
  for (const v of values)
    if (v)
      counts.set(v, (counts.get(v) || 0) + 1);
  return [...counts].map(([v, c]) => c > 1 ? `${v} \xD7${c}` : v).join(" \xB7 ");
}
function footer(s) {
  const lines = [];
  const models = (s.models || []).map(shortModel);
  const providers = s.providers || [];
  if (models.length || providers.length)
    lines.push([models.join(", ") || "model not reported", providers.join(", ")].filter(Boolean).join(" \xB7 "));
  lines.push("From the run ledger; summed across this turn and its child runs.");
  return lines;
}
function tokenDetail(s) {
  const calls = s.modelCalls || [];
  const sections = [];
  const usage = [
    { label: "Input", value: n0(s.inputTokens) },
    { label: "Output", value: n0(s.outputTokens) }
  ];
  if (s.reasoningTokens !== void 0)
    usage.push({ label: "Reasoning", value: n0(s.reasoningTokens), hint: "part of output" });
  usage.push({ label: "Total", value: n0(s.totalTokens) });
  sections.push({ heading: `Usage \xB7 ${plural(s.llmCalls, "model call")}`, rows: usage });
  if (s.measuredCacheCalls) {
    const cached = s.cachedTokens || 0, fed = s.fedTokens || 0;
    const rows = [
      { label: "Reused from cache", value: `${n0(cached)}${cached + fed ? ` (${pct(cached, cached + fed)})` : ""}` },
      { label: "Newly processed", value: n0(s.fedTokens) },
      { label: "Outcome", value: tally(calls.map((c) => c.cacheOutcome)) || (s.cacheOutcomes || []).join(" \xB7 ") || NR },
      { label: "Backend", value: (s.cacheBackends || []).join(", ") || NR }
    ];
    if (s.measuredCacheCalls !== s.llmCalls)
      rows.push({ label: "Measured on", value: `${s.measuredCacheCalls} of ${s.llmCalls} calls` });
    sections.push({ heading: "Prompt cache", rows });
  } else if (s.llmCalls) {
    sections.push({ heading: "Prompt cache", rows: [{ label: "Cache reuse", value: NR }] });
  }
  const sized = calls.filter((c) => c.inputTokens !== void 0);
  if (sized.length === 1 && calls.length === 1)
    sections.push({ heading: "Context", rows: [{ label: "Prompt size", value: `${n0(sized[0].inputTokens)} tokens` }] });
  else if (sized.length > 1)
    sections.push({
      heading: "Context",
      rows: [
        {
          label: "First \u2192 last call",
          value: `${n0(sized[0].inputTokens)} \u2192 ${n0(sized[sized.length - 1].inputTokens)} tokens`
        }
      ],
      note: "Each call re-sends the conversation, so the input total counts the context once per call."
    });
  if (calls.length > 1)
    sections.push({
      heading: "Per call",
      table: {
        columns: ["#", "Input", "Cached", "New", "Output", "Cache"],
        rows: calls.map((c, i) => [
          String(i + 1),
          n0(c.inputTokens),
          c.cachedTokens === void 0 ? "\u2014" : n0(c.cachedTokens),
          c.fedTokens === void 0 ? "\u2014" : n0(c.fedTokens),
          n0(c.outputTokens),
          c.cacheOutcome || "\u2014"
        ])
      }
    });
  return {
    kind: "tokens",
    title: "Tokens",
    headline: s.totalTokens === void 0 ? NR : `${s.totalTokens.toLocaleString()} total`,
    sections,
    footer: footer(s)
  };
}
function phase(ms, tokens, tps, unit) {
  if (ms === void 0)
    return NR;
  const parts = [formatDuration(ms)];
  if (tokens !== void 0)
    parts.push(`${tokens.toLocaleString()} ${unit}${tps !== void 0 ? ` at ${rate(tps)}` : ""}`);
  return parts.join(" \xB7 ");
}
function timeDetail(s) {
  const calls = s.modelCalls || [];
  const sections = [];
  const wall = s.durationMs;
  const turn = [{ label: "Wall clock", value: formatDuration(wall) }];
  turn.push({
    label: "Model",
    value: s.genTimeMs === void 0 ? NR : `${formatDuration(s.genTimeMs)} \xB7 ${plural(s.timedCalls || 0, "call")}${s.timedCalls !== s.llmCalls ? ` (of ${s.llmCalls})` : ""}`
  });
  turn.push({
    label: "Tools",
    value: s.toolTimeMs !== void 0 ? `${formatDuration(s.toolTimeMs)} \xB7 ${plural(s.toolBatches || 0, "batch", "batches")}` : s.toolCalls ? NR : "none",
    hint: s.toolTimeIncludesApproval ? "includes approval wait" : void 0
  });
  if (wall !== void 0 && s.genTimeMs !== void 0) {
    const rest = wall - s.genTimeMs - (s.toolTimeMs || 0);
    turn.push({
      label: "Orchestration",
      value: rest >= 0 ? formatDuration(rest) : "overlaps (parallel runs)",
      hint: "wall \u2212 model \u2212 tools: routing, hand-offs, model load"
    });
  }
  sections.push({ heading: "Turn", rows: turn });
  const model = [];
  const measured = s.ttftCalls || 0, phased = s.promptPhaseCalls || 0;
  if (s.promptPhaseMs !== void 0)
    model.push({
      label: measured && measured === phased ? "Prefill (TTFT)" : "Prefill",
      value: phase(s.promptPhaseMs, s.promptPhaseNewTokens, s.promptPhaseTokensPerSecond, "new tok"),
      hint: measured === phased ? "measured time to first token" : measured ? `TTFT measured on ${measured} of ${phased}; rest from provider rate` : "derived: prompt \xF7 provider rate"
    });
  else if (s.prefillMs !== void 0 && s.prefillNewTokensPerSecond !== void 0)
    model.push({
      label: "Prefill",
      value: phase(s.prefillMs, s.prefillNewTokens, s.prefillNewTokensPerSecond, "new tok"),
      hint: "derived: prompt \xF7 provider rate"
    });
  else if (s.prefillMs !== void 0)
    model.push({
      label: "Prefill",
      value: `${formatDuration(s.prefillMs)}${s.promptTokensPerSecond !== void 0 ? ` at ${rate(s.promptTokensPerSecond)}` : ""}`,
      hint: "provider rate over all prompt tokens, restored included"
    });
  else
    model.push({ label: "Prefill", value: NR });
  if (s.cachedTokens && (s.promptPhaseMs ?? s.prefillMs) !== void 0)
    model.push({ label: "Restored", value: `${s.cachedTokens.toLocaleString()} tok from cache`, hint: "not recomputed" });
  model.push({
    label: "Generation",
    value: s.generationPhaseMs !== void 0 ? phase(s.generationPhaseMs, s.generationPhaseTokens, s.generationPhaseTokensPerSecond, "tok") : phase(s.decodeMs, s.outputTokens, s.generationTokensPerSecond, "tok")
  });
  if (s.measuredSpeedCalls && s.measuredSpeedCalls !== s.llmCalls)
    model.push({ label: "Speeds from", value: `${s.measuredSpeedCalls} of ${s.llmCalls} calls` });
  sections.push({ heading: "Model", rows: model });
  const spec = s.speculation;
  if (spec) {
    const kinds = (spec.draftKinds || []).map((k) => k.toUpperCase()).join(", ");
    const rows = [
      {
        label: "Mode",
        value: `${spec.used ? "on" : "off"}${kinds ? ` \xB7 ${kinds}` : ""}${spec.modes?.length ? ` (${spec.modes.join(", ")})` : ""}`,
        hint: spec.calls !== s.llmCalls || spec.used !== spec.calls ? `used on ${spec.used} of ${s.llmCalls} calls` : void 0
      },
      {
        label: "Acceptance",
        value: spec.acceptanceRate === void 0 ? NR : `${Math.round(spec.acceptanceRate * 100)}% \xB7 ${n0(spec.acceptedTokens)} of ${n0(spec.draftedTokens)} drafted`
      }
    ];
    if (spec.draftLengths?.length || spec.rounds !== void 0)
      rows.push({
        label: "Draft length",
        value: `${spec.draftLengths?.length ? `${spec.draftLengths.join("/")} tok/round` : NR}${spec.rounds !== void 0 ? ` \xB7 ${spec.rounds.toLocaleString()} rounds` : ""}`
      });
    sections.push({ heading: "Speculation", rows });
  }
  if (s.slowestToolBatch)
    sections.push({
      heading: "Tools",
      rows: [
        { label: "Total", value: `${formatDuration(s.toolTimeMs)} \xB7 ${plural(s.toolBatches || 0, "batch", "batches")}` },
        { label: "Slowest", value: `${formatDuration(s.slowestToolBatch.ms)} \xB7 ${batchLabel(s.slowestToolBatch)}` }
      ],
      note: s.toolTimeIncludesApproval ? "Gated calls are timed from request to result, so this includes waiting for your approval." : void 0
    });
  if (calls.length > 1)
    sections.push({
      heading: "Per call",
      table: {
        columns: ["#", "Prefill", "New tok/s", "Gen", "Gen tok/s", "Cache"],
        rows: calls.map((c, i) => [
          String(i + 1),
          c.promptMs === void 0 ? "\u2014" : `${formatDuration(c.promptMs)}${c.promptSource === "rate" ? "*" : ""}`,
          c.promptNewTokensPerSecond === void 0 ? "\u2014" : Math.round(c.promptNewTokensPerSecond).toLocaleString(),
          c.generationMs === void 0 ? "\u2014" : formatDuration(c.generationMs),
          c.generationTokensPerSecond === void 0 ? "\u2014" : Math.round(c.generationTokensPerSecond).toLocaleString(),
          c.cacheOutcome || "\u2014"
        ])
      },
      note: calls.some((c) => c.promptSource === "rate") ? "* derived from the provider's prompt rate (no TTFT event)." : void 0
    });
  return {
    kind: "time",
    title: "Time",
    headline: wall === void 0 ? NR : `${formatDuration(wall)} wall clock`,
    sections,
    footer: footer(s)
  };
}
function batchLabel(batch) {
  return batch.tools.length === 1 ? `${batch.tools[0]} \xD7${batch.calls}` : `${plural(batch.calls, "call")} (${batch.tools.join(", ")})`;
}
function toolDetail(s) {
  const sections = [];
  const pending = (s.toolsWaiting || 0) + (s.toolsRunning || 0);
  if (!s.toolCalls && !pending) {
    sections.push({ heading: "Outcome", rows: [{ label: "Tools called", value: "none" }] });
    return { kind: "tools", title: "Tools", headline: "none", sections, footer: footer(s) };
  }
  const outcome = [
    { label: "Succeeded", value: (s.toolCalls - (s.toolsFailed || 0)).toLocaleString() },
    { label: "Failed", value: (s.toolsFailed || 0).toLocaleString() }
  ];
  if (s.toolsRunning)
    outcome.push({ label: "Running", value: s.toolsRunning.toLocaleString() });
  if (s.toolsWaiting)
    outcome.push({ label: "Awaiting approval", value: s.toolsWaiting.toLocaleString(), hint: "not run yet \u2014 not a failure" });
  sections.push({ heading: "Outcome", rows: outcome });
  const breakdown = Object.entries(s.toolBreakdown || {}).sort((a, b) => b[1].calls - a[1].calls || a[0].localeCompare(b[0]));
  if (breakdown.length)
    sections.push({
      heading: "By tool",
      table: {
        columns: ["Tool", "Calls", "Failed", "Time"],
        rows: breakdown.map(([name, row]) => [
          name,
          row.calls.toLocaleString(),
          row.failed.toLocaleString(),
          row.ms !== void 0 ? `${formatDuration(row.ms)}${row.sharedBatches ? " +shared" : ""}` : row.sharedBatches ? "shared" : NR
        ])
      },
      note: breakdown.some(([, row]) => row.sharedBatches) ? "A batch that mixed tools ran them together; its time is not split between them." : void 0
    });
  const failures = breakdown.filter(([, row]) => row.errors && Object.keys(row.errors).length);
  if (failures.length)
    sections.push({
      heading: "Failures",
      rows: failures.map(([name, row]) => ({
        label: name,
        value: Object.entries(row.errors).sort((a, b) => b[1] - a[1]).map(([cls, n]) => n > 1 ? `${cls} \xD7${n}` : cls).join(" \xB7 ")
      }))
    });
  const timing = [
    {
      label: "Tool time",
      value: s.toolTimeMs === void 0 ? NR : `${formatDuration(s.toolTimeMs)} \xB7 ${plural(s.toolBatches || 0, "batch", "batches")}`
    }
  ];
  if (s.slowestToolBatch)
    timing.push({ label: "Slowest batch", value: `${formatDuration(s.slowestToolBatch.ms)} \xB7 ${batchLabel(s.slowestToolBatch)}` });
  sections.push({
    heading: "Timing",
    rows: timing,
    note: s.toolTimeIncludesApproval ? "Gated calls are timed from request to result, so this includes waiting for your approval." : void 0
  });
  return {
    kind: "tools",
    title: "Tools",
    headline: `${plural(s.toolCalls, "call")}${s.toolsFailed ? ` \xB7 ${s.toolsFailed} failed` : ""}`,
    sections,
    footer: footer(s)
  };
}
var FILES_SHOWN = 30;
function filesDetail(s) {
  const files2 = s.changedFiles || [];
  const rows = files2.slice(0, FILES_SHOWN).map((path) => {
    const clean = path.replace(/[\\/]+$/, "");
    const cut = Math.max(clean.lastIndexOf("/"), clean.lastIndexOf("\\"));
    return { label: cut >= 0 ? clean.slice(cut + 1) || clean : clean, value: cut > 0 ? clean.slice(0, cut) : cut === 0 ? "/" : "workspace folder" };
  });
  return {
    kind: "files",
    title: "Files changed",
    headline: plural(files2.length, "file"),
    sections: [
      {
        heading: "Written by this turn's tools",
        rows,
        note: files2.length > FILES_SHOWN ? `and ${plural(files2.length - FILES_SHOWN, "more file")}` : void 0
      }
    ],
    footer: ["From the run ledger: the paths of this turn's completed file-writing tool calls."]
  };
}
function statDetail(kind, statistics) {
  if (kind === "tokens")
    return tokenDetail(statistics);
  if (kind === "time")
    return timeDetail(statistics);
  if (kind === "files")
    return filesDetail(statistics);
  return toolDetail(statistics);
}
function StatDetailPanel(props) {
  const d = props.detail;
  return _jsxs8("div", { ref: props.panelRef, id: props.id, role: "tooltip", className: `pc-stat-detail pc-stat-detail--${d.kind}`, style: props.style, onMouseEnter: props.onMouseEnter, onMouseLeave: props.onMouseLeave, children: [_jsxs8("div", { className: "pc-stat-detail-head", children: [_jsx10("span", { className: "pc-stat-detail-title", children: d.title }), _jsx10("span", { className: "pc-stat-detail-headline", children: d.headline })] }), d.sections.map((section) => _jsxs8("div", { className: "pc-stat-detail-section", children: [_jsx10("div", { className: "pc-stat-detail-heading", children: section.heading }), section.rows?.length ? _jsx10("dl", { className: "pc-stat-detail-rows", children: section.rows.map((row, i) => _jsxs8(React4.Fragment, { children: [_jsx10("dt", { children: row.label }), _jsxs8("dd", { children: [_jsx10("span", { className: row.value === NR ? "pc-stat-detail-value pc-stat-detail-value--absent" : "pc-stat-detail-value", children: row.value }), row.hint ? _jsx10("span", { className: "pc-stat-detail-hint", children: row.hint }) : null] })] }, `${row.label}:${i}`)) }) : null, section.table ? _jsxs8("table", { className: "pc-stat-detail-table", children: [_jsx10("thead", { children: _jsx10("tr", { children: section.table.columns.map((c) => _jsx10("th", { scope: "col", children: c }, c)) }) }), _jsx10("tbody", { children: section.table.rows.map((r, i) => _jsx10("tr", { children: r.map((cell, j) => _jsx10("td", { children: cell }, j)) }, i)) })] }) : null, section.note ? _jsx10("p", { className: "pc-stat-detail-note", children: section.note }) : null] }, section.heading)), _jsx10("div", { className: "pc-stat-detail-foot", children: d.footer.map((line) => _jsx10("div", { children: line }, line)) })] });
}
var GAP = 8;
function StatChip(props) {
  const [open, setOpen] = useState7(Boolean(props.defaultOpen));
  const [pos, setPos] = useState7(null);
  const chipRef = useRef4(null);
  const panelRef = useRef4(null);
  const closeTimer = useRef4(null);
  const id = `pc-stat-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const cancelClose = useCallback2(() => {
    if (closeTimer.current !== null)
      window.clearTimeout(closeTimer.current);
    closeTimer.current = null;
  }, []);
  const show = useCallback2(() => {
    cancelClose();
    setOpen(true);
  }, [cancelClose]);
  const hideSoon = useCallback2(() => {
    cancelClose();
    closeTimer.current = window.setTimeout(() => setOpen(false), 120);
  }, [cancelClose]);
  useEffect7(() => cancelClose, [cancelClose]);
  useLayoutEffect(() => {
    if (!open) {
      setPos(null);
      return;
    }
    const place = () => {
      const chip = chipRef.current, panel2 = panelRef.current;
      if (!chip || !panel2)
        return;
      const r = chip.getBoundingClientRect();
      const w = panel2.offsetWidth, h = panel2.offsetHeight;
      const vw = window.innerWidth, vh = window.innerHeight;
      const above = r.top - GAP - h;
      const below = r.bottom + GAP;
      const top = above >= GAP ? above : below + h <= vh - GAP ? below : Math.max(GAP, vh - GAP - h);
      const left = Math.min(Math.max(GAP, r.left), Math.max(GAP, vw - GAP - w));
      setPos({ top, left });
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open]);
  useEffect7(() => {
    if (!open)
      return;
    const onKey = (e) => {
      if (e.key === "Escape")
        setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);
  const clickable = typeof props.onClick === "function";
  const Element = clickable ? "button" : "span";
  const panel = open ? _jsx10(StatDetailPanel, { detail: props.detail, id, panelRef, onMouseEnter: cancelClose, onMouseLeave: hideSoon, style: { position: "fixed", top: pos?.top ?? 0, left: pos?.left ?? 0, visibility: pos ? "visible" : "hidden" } }) : null;
  return _jsxs8(_Fragment4, { children: [_jsxs8(Element, { ref: chipRef, ...clickable ? { type: "button" } : { tabIndex: 0 }, className: ["pc-chat-stat", "pc-chat-stat--detail", clickable ? "pc-chat-stat--clickable" : "", props.className].filter(Boolean).join(" "), "aria-label": `${props.label} \u2014 ${props.detail.title.toLowerCase()} details`, "aria-describedby": open ? id : void 0, "data-stat-kind": props.detail.kind, onMouseEnter: show, onMouseLeave: hideSoon, onFocus: show, onBlur: () => setOpen(false), onKeyDown: (e) => {
    if (e.key === "Escape")
      setOpen(false);
  }, onClick: clickable ? () => props.onClick?.() : void 0, children: [props.icon ? _jsx10("span", { className: "pc-chat-stat-icon", "aria-hidden": "true", children: props.icon }) : null, _jsx10("span", { className: "pc-chat-stat-label", children: props.label })] }), panel && typeof document !== "undefined" ? createPortal(panel, document.body) : panel] });
}

// dist/tool_activity.js
function toolArguments(value) {
  if (typeof value !== "string")
    return value;
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}
function toolPreview(value) {
  const args = toolArguments(value);
  if (!args || typeof args !== "object" || Array.isArray(args))
    return { label: "input", value: args == null ? "" : String(args) };
  const entries = Object.entries(args);
  const preferred = [
    "command",
    "query",
    "url",
    "file_path",
    "path",
    "pattern",
    "name"
  ];
  const entry = preferred.map((key) => entries.find(([name]) => name === key)).find(Boolean) || entries[0];
  return entry ? {
    label: entry[0].replace(/_/g, " "),
    value: typeof entry[1] === "string" ? entry[1] : JSON.stringify(entry[1]) ?? ""
  } : { label: "", value: "" };
}
function ToolActivity({ tool, showCopy = true }) {
  const [copied, setCopied] = useState8(false);
  const args = toolArguments(tool.arguments);
  const preview = toolPreview(tool.arguments);
  const output = toolArguments(tool.output);
  const previewText = ["file path", "path"].includes(preview.label) && preview.value.length > 60 ? `${preview.value.split(/[\\/]/).pop()} \xB7 ${preview.value.slice(0, 24)}\u2026` : preview.value;
  const errorPreview = tool.error && /^File ['"].+['"] does not exist\.?$/.test(tool.error) ? "File not found. Expand for the exact path." : tool.error && tool.error.length > 180 ? `${tool.error.slice(0, 100)}\u2026${tool.error.slice(-70)}` : tool.error;
  const labels = {
    running: "Running",
    waiting: "Approval needed",
    completed: "Done",
    failed: "Failed"
  };
  const duration = tool.startedAt && tool.endedAt ? Date.parse(tool.endedAt) - Date.parse(tool.startedAt) : NaN;
  const fields = args && typeof args === "object" && !Array.isArray(args) ? Object.entries(args) : null;
  return _jsxs9("details", { className: `pc-tool-activity pc-tool-activity--${tool.status}`, children: [_jsxs9("summary", { className: "pc-tool-activity__summary", children: [_jsx11("span", { className: "pc-tool-activity__state-icon", "aria-hidden": "true", children: _jsx11(Icon4, { name: tool.status === "completed" ? "check" : tool.status === "failed" ? "x" : tool.status === "waiting" ? "warning" : "loader", size: 15 }) }), _jsx11("strong", { children: tool.name }), _jsx11("span", { className: "pc-tool-activity__preview", title: preview.value, children: preview.value ? _jsxs9(_Fragment5, { children: [_jsx11("span", { className: "pc-tool-activity__key", children: preview.label }), _jsx11(TextLinks, { text: previewText })] }) : "No parameters" }), _jsx11("span", { className: "pc-tool-activity__status", children: labels[tool.status] }), tool.policy ? _jsx11("span", { className: "pc-tool-activity__policy", "data-policy": tool.policy.decision, title: toolPolicyDecisionText(tool.policy), children: tool.policy.decision === "denied" ? "Denied by this chat's policy" : "Allowed by this chat's policy" }) : null, Number.isFinite(duration) && duration >= 0 ? _jsxs9("span", { className: "pc-tool-activity__duration", "data-approval-wait": tool.approvalWait ? "" : void 0, title: tool.approvalWait ? "Timed from request to result: includes the wait for your decision." : void 0, children: [formatDuration(duration), tool.approvalWait ? " incl. approval wait" : ""] }) : null, _jsx11("span", { className: "pc-tool-activity__chevron", "aria-hidden": "true", children: _jsx11(Icon4, { name: "chevronRight", size: 13 }) }), tool.error ? _jsx11("span", { className: "pc-tool-activity__error", title: tool.error, children: errorPreview }) : null] }), _jsxs9("div", { className: "pc-tool-activity__detail", children: [tool.policy ? _jsxs9("p", { className: "pc-tool-activity__policy-line", "data-policy": tool.policy.decision, children: [toolPolicyDecisionText(tool.policy), tool.policy.matched ? ` \xB7 matched ${tool.policy.matched}` : ""] }) : null, _jsx11(ToolSandboxLine, { sandbox: tool.sandbox }), tool.error ? _jsxs9(_Fragment5, { children: [_jsx11("h4", { children: "Error" }), _jsx11("pre", { className: "pc-tool-activity__output", children: _jsx11(TextLinks, { text: tool.error }) })] }) : null, _jsxs9("div", { className: "pc-tool-activity__detail-heading", children: [_jsx11("h4", { children: "Parameters" }), showCopy ? _jsxs9("button", { type: "button", onClick: async () => setCopied(await copyText(JSON.stringify(tool, null, 2))), children: [_jsx11(Icon4, { name: "copy", size: 13 }), copied ? "Copied" : "Copy details"] }) : null] }), fields ? _jsx11("dl", { className: "pc-tool-activity__parameters", children: fields.map(([key, value]) => _jsxs9(React5.Fragment, { children: [_jsx11("dt", { children: key }), _jsx11("dd", { children: value && typeof value === "object" ? _jsx11(JsonViewer, { value }) : _jsx11("code", { children: typeof value === "string" ? _jsx11(TextLinks, { text: value }) : JSON.stringify(value) }) })] }, key)) }) : tool.arguments === void 0 ? _jsx11("p", { children: "Arguments are unavailable in this ledger." }) : _jsx11(JsonViewer, { value: args }), tool.output !== void 0 ? _jsxs9(_Fragment5, { children: [_jsx11("h4", { children: "Result" }), typeof output === "string" ? _jsx11("pre", { className: "pc-tool-activity__output", children: _jsx11(TextLinks, { text: output }) }) : _jsx11("div", { className: "pc-tool-activity__output", children: _jsx11(JsonViewer, { value: output }) })] }) : null] })] });
}
function ToolActivityGroup({ tools, showCopy }) {
  const count = (status) => tools.filter((tool) => tool.status === status).length;
  return _jsxs9("section", { className: "pc-tool-group", "aria-label": "Tool activity", children: [_jsxs9("div", { className: "pc-tool-group__heading", children: [_jsx11(Icon4, { name: "terminal", size: 14 }), _jsx11("strong", { children: "Tools" }), _jsxs9("span", { children: [tools.length, " ", tools.length === 1 ? "call" : "calls"] }), _jsx11("div", {}), count("running") ? _jsxs9("span", { className: "pc-tool-group__running", children: [count("running"), " running"] }) : null, count("waiting") ? _jsxs9("span", { className: "pc-tool-group__waiting", children: [count("waiting"), " need approval"] }) : null, count("failed") ? _jsxs9("span", { className: "pc-tool-group__failed", children: [count("failed"), " failed"] }) : null, count("completed") ? _jsxs9("span", { className: "pc-tool-group__completed", children: [count("completed"), " done"] }) : null] }), tools.map((tool) => _jsx11(ToolActivity, { tool, showCopy }, tool.id))] });
}

// dist/message_footer.js
import { useEffect as useEffect8, useState as useState9 } from "react";
var startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
var BARE_DAY = /^(\d{4})-(\d{2})-(\d{2})$/;
var isBareDay = (ts) => typeof ts === "string" && BARE_DAY.test(ts.trim());
function toDate(ts) {
  if (ts === null || ts === void 0)
    return null;
  if (typeof ts === "string" && !ts.trim())
    return null;
  if (typeof ts === "string") {
    const day = BARE_DAY.exec(ts.trim());
    if (day)
      return new Date(Number(day[1]), Number(day[2]) - 1, Number(day[3]));
  }
  const d = ts instanceof Date ? new Date(ts.getTime()) : new Date(typeof ts === "string" ? ts.trim() : ts);
  return Number.isFinite(d.getTime()) ? d : null;
}
function formatMessageStamp(ts, now = /* @__PURE__ */ new Date(), locales) {
  const d = toDate(ts);
  if (!d)
    return "";
  const time = isBareDay(ts) ? "" : d.toLocaleTimeString(locales, { hour: "2-digit", minute: "2-digit" });
  const day = startOfDay(d);
  const today = startOfDay(now);
  if (day === today)
    return time || "Today";
  const yesterday = startOfDay(new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1));
  if (day === yesterday)
    return time ? `Yesterday \xB7 ${time}` : "Yesterday";
  const sameYear = d.getFullYear() === now.getFullYear();
  const date = d.toLocaleDateString(locales, sameYear ? { month: "short", day: "numeric" } : { month: "short", day: "numeric", year: "numeric" });
  return time ? `${date} \xB7 ${time}` : date;
}
function messageStampTitle(ts, locales) {
  const d = toDate(ts);
  if (!d)
    return "";
  if (isBareDay(ts))
    return d.toLocaleDateString(locales, { weekday: "long", year: "numeric", month: "long", day: "numeric" });
  return d.toLocaleString(locales, { weekday: "long", year: "numeric", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit" });
}
function messageStampIso(ts) {
  if (isBareDay(ts))
    return ts.trim();
  const d = toDate(ts);
  return d ? d.toISOString() : "";
}
function localDayKey(now = /* @__PURE__ */ new Date()) {
  return `${now.getFullYear()}-${now.getMonth()}-${now.getDate()}`;
}
var dayListeners = /* @__PURE__ */ new Set();
var dayTimer = null;
function armDayTimer() {
  if (dayTimer !== null || !dayListeners.size || typeof setTimeout !== "function")
    return;
  const now = /* @__PURE__ */ new Date();
  const next = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 0, 0, 1);
  dayTimer = setTimeout(() => {
    dayTimer = null;
    for (const listener of [...dayListeners])
      listener();
    armDayTimer();
  }, Math.min(Math.max(1e3, next.getTime() - now.getTime()), 36e5));
  dayTimer.unref?.();
}
function subscribeLocalDay(listener) {
  dayListeners.add(listener);
  armDayTimer();
  return () => {
    dayListeners.delete(listener);
    if (!dayListeners.size && dayTimer !== null) {
      clearTimeout(dayTimer);
      dayTimer = null;
    }
  };
}
function useLocalDay() {
  const [day, setDay] = useState9(() => localDayKey());
  useEffect8(() => {
    setDay(localDayKey());
    return subscribeLocalDay(() => setDay(localDayKey()));
  }, []);
  return day;
}

// dist/chat_message_card.js
function workflowStats(metrics) {
  const tokens = metrics.totalTokens !== void 0 ? statDetail("tokens", metrics) : null;
  const tools = statDetail("tools", metrics);
  const time = metrics.durationMs !== void 0 ? statDetail("time", metrics) : null;
  return [
    ...tokens ? [{ label: `${metrics.totalTokens.toLocaleString()} tokens`, detail: tokens }] : [],
    { label: `${metrics.toolCalls} ${metrics.toolCalls === 1 ? "tool" : "tools"}`, detail: tools },
    ...metrics.changedFiles.length ? [{ label: `${metrics.changedFiles.length} ${metrics.changedFiles.length === 1 ? "file" : "files"} changed`, detail: statDetail("files", metrics) }] : [],
    // One duration format across the chat (the stat panel, the tool rows, this chip): "4.2s", "3m 35s".
    ...time ? [{ label: formatDuration(metrics.durationMs), detail: time }] : []
  ];
}
function _role_ui(m) {
  const role = String(m.role || "").trim().toLowerCase() || "system";
  const kind = String(m.kind || "").trim().toLowerCase();
  const lvl = String(m.level || "").trim().toLowerCase();
  if (role === "system" && kind === "report_bug") {
    return { label: String(m.title || "").trim() || "Bug report", icon: "warning", variant: "report_bug" };
  }
  if (role === "system" && kind === "report_feature") {
    return { label: String(m.title || "").trim() || "Feature request", icon: "check", variant: "report_feature" };
  }
  if (role === "user")
    return { label: String(m.title || "").trim() || "You", icon: "user", variant: "user" };
  if (role === "assistant")
    return { label: String(m.title || "").trim() || "Agent", icon: "bot", variant: "assistant" };
  const sys_label = String(m.title || "").trim() || (lvl === "error" ? "Error" : lvl === "warn" ? "Warning" : "System");
  const sys_icon = lvl === "error" ? "error" : lvl === "warn" ? "warning" : "info";
  const sys_variant = lvl === "error" ? "error" : lvl === "warn" ? "warn" : "status";
  return { label: sys_label, icon: sys_icon, variant: sys_variant };
}
var MEDIA_SCHEMES = /* @__PURE__ */ new Set(["blob:", "data:", "http:", "https:"]);
function mediaSource(src) {
  const value = String(src || "").trim();
  if (!value)
    return void 0;
  try {
    const base = typeof window !== "undefined" && window.location ? window.location.href : "http://same-origin.invalid/";
    return MEDIA_SCHEMES.has(new URL(value, base).protocol) ? value : void 0;
  } catch {
    return void 0;
  }
}
function rawLinkProps(href, name) {
  return isLocalObjectUrl(href) ? { href, download: name || "file" } : { href, target: "_blank", rel: "noopener noreferrer" };
}
function ChatMediaFile({ item, onOpen, markdown }) {
  const [open, setOpen] = useState10(false);
  const src = mediaSource(item.src);
  const name = String(item.name || item.label || "").trim() || "File";
  const href = fileRawLink({ href: item.href ? mediaSource(item.href) : void 0, src, contentType: item.contentType, name: item.name || item.label });
  const kind = fileViewerKind3(name, item.contentType);
  const needsText = fileViewerNeedsText2(kind);
  const hasText = typeof item.text === "string";
  if (!src && !href && !hasText)
    return null;
  const size = formatFileSize2(item.size);
  const label = String(item.label || "").trim() || name;
  return _jsxs10("figure", { className: "pc-chat-media__item pc-chat-media__item--file", "data-file-kind": kind, children: [_jsxs10("div", { className: "pc-chat-media__file-row", children: [_jsx12(Icon5, { name: "file", size: 14 }), _jsx12("span", { className: "pc-chat-media__file-name", title: name, children: label }), size ? _jsx12("span", { className: "pc-chat-media__file-size", children: size }) : null, onOpen ? _jsx12("button", {
    type: "button",
    className: "pc-chat-media__file-open",
    "data-action": "open-file",
    // The opener gets the item as the kit would render it: sanitized sources only.
    onClick: () => onOpen({ ...item, src: src || "", ...href ? { href } : { href: void 0 } }),
    children: "Open"
  }) : _jsx12("button", { type: "button", className: "pc-chat-media__file-open", "data-action": "toggle-file", "aria-expanded": open, onClick: () => setOpen((v) => !v), children: open ? "Close" : "Open" }), href ? _jsx12("a", { className: "pc-chat-media__link", ...rawLinkProps(href, String(item.name || "").trim() || label), children: "Raw file" }) : null] }), open && !onOpen ? _jsx12(FileViewer, {
    className: "pc-chat-media__viewer",
    name,
    kind,
    contentType: item.contentType,
    sizeBytes: item.size,
    status: needsText && !hasText ? "error" : "ready",
    error: needsText && !hasText ? href ? "No preview text was supplied for this file; open the raw file." : "No preview text was supplied for this file." : void 0,
    // The chat's image policy reaches a Markdown file too (default "link":
    // a generated document must not make the browser fetch remote images).
    markdownImages: markdown.images || "link",
    ...markdown.inlineImage ? { inlineImage: markdown.inlineImage } : {},
    ...markdown.renderMarkdown ? { renderMarkdown: markdown.renderMarkdown } : {},
    ...hasText ? { text: item.text } : {},
    ...src && !needsText ? { url: src } : {},
    onClose: () => setOpen(false)
  }) : null] });
}
function ChatMediaItem({ item, onOpenFile, markdown }) {
  const [failed, setFailed] = useState10(false);
  if (item.kind === "file")
    return _jsx12(ChatMediaFile, { item, onOpen: onOpenFile, markdown: markdown || {} });
  const src = mediaSource(item.src);
  const href = item.href ? mediaSource(item.href) : void 0;
  const kind = item.kind === "image" || item.kind === "audio" || item.kind === "video" ? item.kind : null;
  if (!kind || !src && !href)
    return null;
  const noun = kind === "image" ? "Image" : kind === "video" ? "Video" : "Audio";
  const label = String(item.label || "").trim() || `Generated ${noun.toLowerCase()}`;
  const onError = () => setFailed(true);
  return _jsxs10("figure", { className: `pc-chat-media__item pc-chat-media__item--${kind}`, children: [src && kind === "image" ? _jsx12("img", { className: "pc-chat-media__image", src, alt: label, loading: "lazy", onError }) : null, src && kind === "video" ? _jsx12("video", { className: "pc-chat-media__video", src, controls: true, playsInline: true, preload: "metadata", "aria-label": label, onError }) : null, src && kind === "audio" ? _jsx12(AfAudioPlayer, { className: "pc-chat-media__audio", src, name: label }) : null, kind === "audio" && String(item.transcript || "").trim() ? _jsxs10("details", { className: "pc-chat-media__transcript", children: [_jsx12("summary", { children: "Transcript" }), _jsx12("p", { className: "pc-chat-media__transcript-text", children: String(item.transcript).trim() })] }) : null, failed ? _jsxs10("div", { className: "pc-chat-media__error", role: "note", children: [noun, " could not be decoded by this browser", href ? "; open the raw file with the link." : "."] }) : null, href ? _jsx12("figcaption", { className: "pc-chat-media__caption", children: _jsx12("a", { className: "pc-chat-media__link", ...rawLinkProps(href, String(item.name || "").trim() || label), children: label }) }) : null] });
}
function speakButtonView(state) {
  if (state === "loading")
    return { icon: "loader", title: "Generating audio\u2026", spinning: true };
  if (state === "playing")
    return { icon: "pause", title: "Pause", spinning: false };
  if (state === "paused")
    return { icon: "play", title: "Resume", spinning: false };
  return { icon: "speaker", title: "Speak (TTS)", spinning: false };
}
function ChatMessageCard(props) {
  const m = props.message;
  const role_ui = useMemo5(() => _role_ui(m), [m.kind, m.level, m.role, m.title]);
  const raw_ts = m.ts;
  const day_key = useLocalDay();
  const time_label = useMemo5(() => formatMessageStamp(raw_ts), [raw_ts, day_key]);
  const time_title = useMemo5(() => messageStampTitle(raw_ts), [raw_ts]);
  const time_iso = useMemo5(() => messageStampIso(raw_ts), [raw_ts]);
  const [copy_state, set_copy_state] = useState10("idle");
  const copy_timer = useRef5(null);
  useEffect9(() => {
    return () => {
      if (copy_timer.current !== null)
        window.clearTimeout(copy_timer.current);
    };
  }, []);
  const live = m.live;
  const show_speaker = typeof props.onSpeakToggle === "function" && role_ui.variant === "assistant";
  const speak_blocked = !show_speaker ? "" : live ? "Read aloud when the reply is finished" : !String(m.content || "").trim() ? "No text to read aloud" : "";
  const can_speak = show_speaker && !speak_blocked;
  const speak_state = can_speak ? props.getSpeakState?.(m) || "idle" : "idle";
  const speak = speakButtonView(speak_state);
  const show_copy = props.showCopy !== false;
  const attachments = Array.isArray(props.attachments) ? props.attachments : Array.isArray(m.attachments) ? m.attachments : [];
  const metrics = m.statistics;
  const own_stats = m.stats;
  const stats = useMemo5(() => Array.isArray(props.stats) ? props.stats : Array.isArray(own_stats) ? own_stats : metrics ? workflowStats(metrics) : [], [props.stats, own_stats, metrics]);
  const media = Array.isArray(m.media) ? m.media : [];
  const reasoning = live ? String(live.reasoning || "") : String(m.reasoning || "");
  const has_text = Boolean(String(m.content || "").trim());
  if (m.toolActivity)
    return _jsx12(ToolActivity, { tool: m.toolActivity, showCopy: props.showCopy });
  const footer2 = props.renderFooter ? props.renderFooter(m) : null;
  if (props.variant?.(m) === "hint" || m.kind === "tool_policy_decision") {
    const level = String(m.level || "").trim().toLowerCase();
    return _jsxs10("div", { className: ["pc-chat-hint", level === "warn" || level === "error" ? `pc-chat-hint--${level}` : "", props.className].filter(Boolean).join(" "), role: "note", "data-variant": "hint", children: [_jsx12("span", { className: "pc-chat-hint__text", children: String(m.content || "") }), footer2 != null && footer2 !== false ? _jsx12("div", { className: "pc-chat-footer", children: footer2 }) : null] });
  }
  return _jsxs10("div", { className: ["pc-chat-item", `pc-chat-item--${role_ui.variant}`, live ? "pc-chat-item--live" : "", props.className].filter(Boolean).join(" "), ...live ? { "aria-busy": true } : {}, children: [_jsxs10("div", { className: "pc-chat-header", children: [_jsx12("div", { className: "pc-chat-avatar", "aria-hidden": "true", children: _jsx12(Icon5, { name: role_ui.icon, size: 14 }) }), _jsx12("span", { className: "pc-chat-role", children: role_ui.label }), live ? _jsxs10("span", { className: "pc-chat-live-indicator", title: live.label ? `Pending: ${live.label}` : "The reply is still being written", children: [_jsx12("span", { className: "pc-chat-live-dot", "aria-hidden": "true" }), live.label || "streaming"] }) : null, live?.caption ? _jsx12("span", { className: "pc-chat-live-caption", children: live.caption }) : null, _jsx12("span", { className: "pc-chat-header-spacer" }), time_label ? _jsx12("time", { className: "pc-chat-time", dateTime: time_iso || void 0, title: time_title || void 0, children: time_label }) : null, _jsxs10("div", { className: "pc-chat-header-actions", children: [show_speaker ? _jsx12("button", { className: "pc-chat-icon-btn", type: "button", "aria-label": speak_blocked || speak.title, title: speak_blocked || speak.title, "data-speak-state": speak_blocked ? "unavailable" : speak_state, ...speak_blocked ? { "aria-disabled": true } : {}, onClick: can_speak ? () => props.onSpeakToggle?.(m) : void 0, children: _jsx12(Icon5, { name: speak.icon, size: 22, className: speak.spinning ? "pc-chat-speak-spinner" : void 0 }, speak.icon) }) : null, show_copy ? _jsx12("button", { className: `pc-chat-icon-btn ${copy_state !== "idle" ? `pc-chat-icon-btn--${copy_state}` : ""}`.trim(), type: "button", "aria-label": "Copy message", title: copy_state === "idle" ? "Copy" : copy_state === "copied" ? "Copied" : "Copy failed", onClick: async () => {
    const ok = await copyText(String(m.content || ""));
    set_copy_state(ok ? "copied" : "failed");
    if (copy_timer.current !== null)
      window.clearTimeout(copy_timer.current);
    copy_timer.current = window.setTimeout(() => set_copy_state("idle"), 900);
  }, children: _jsx12(Icon5, { name: "copy", size: 22 }) }) : null] })] }), reasoning.trim() ? _jsxs10("details", { className: "pc-chat-thinking", children: [_jsx12("summary", { children: "Thinking" }), _jsx12("div", { className: "pc-chat-thinking-body", children: reasoning })] }) : null, has_text || !live && !media.length ? _jsx12("div", { className: "pc-chat-body", children: _jsx12(ChatMessageContent, { text: String(m.content || ""), renderMarkdown: props.renderMarkdown, jsonCollapseAfterDepth: props.jsonCollapseAfterDepth, images: props.images || (role_ui.variant === "user" ? "inline" : "link"), inlineImage: props.inlineImage }) }) : null, media.length ? _jsx12("div", { className: "pc-chat-media", children: media.map((item, idx) => _jsx12(ChatMediaItem, { item, onOpenFile: props.onOpenMedia, markdown: { renderMarkdown: props.renderMarkdown, images: props.images, inlineImage: props.inlineImage } }, item.id || `${item.kind}:${item.src}:${idx}`)) }) : null, m.artifactRefs?.length || m.artifactIds?.length ? _jsx12("div", { className: "pc-chat-attachments", "aria-label": "Attached files", children: (m.artifactRefs || m.artifactIds?.map((id) => ({ id, runId: m.runId || "" })) || []).map((a) => _jsx12(MessageArtifactChip, { artifact: a }, `${a.runId}:${a.id}`)) }) : null, attachments.length ? _jsx12("div", { className: "pc-chat-attachments", "aria-label": "Attachments", children: attachments.map((a, idx) => {
    const label = String(a.label || "").trim() || "attachment";
    const target = String(a.target || "").trim();
    const title = String(a.title || "").trim();
    const disabled = Boolean(a.disabled) || typeof a.onClick !== "function";
    return _jsxs10("button", { type: "button", className: "pc-chat-attachment-chip", title: title || label, onClick: disabled ? void 0 : a.onClick, disabled, children: [_jsx12(Icon5, { name: "paperclip", size: 14 }), target ? _jsx12("span", { className: `pc-chat-attachment-target pc-chat-attachment-target--${target}`, children: target }) : null, _jsx12("span", { className: "pc-chat-attachment-name", children: label })] }, a.id || `${label}:${idx}`);
  }) }) : null, stats.length ? _jsx12("div", { className: "pc-chat-stats", "aria-label": "Stats", children: stats.slice(0, 12).map((s, idx) => {
    const label = String(s.label || "").trim();
    if (!label)
      return null;
    if (s.detail)
      return _jsx12(StatChip, { label, detail: s.detail, icon: s.icon, onClick: s.onClick }, s.id || `${label}:${idx}`);
    const title = String(s.title || "").trim();
    const clickable = typeof s.onClick === "function";
    const StatElement = clickable ? "button" : "span";
    return _jsxs10(StatElement, { ...clickable ? { type: "button" } : {}, className: ["pc-chat-stat", clickable ? "pc-chat-stat--clickable" : ""].filter(Boolean).join(" "), title: title || void 0, onClick: clickable ? () => s.onClick?.() : void 0, children: [s.icon ? _jsx12("span", { className: "pc-chat-stat-icon", "aria-hidden": "true", children: s.icon }) : null, _jsx12("span", { className: "pc-chat-stat-label", children: label })] }, s.id || `${label}:${idx}`);
  }) }) : null, footer2 != null && footer2 !== false ? _jsx12("div", { className: "pc-chat-footer", children: footer2 }) : null] });
}

// dist/chat_thread.js
function is_near_bottom(el, thresholdPx) {
  const thr = Math.max(0, Math.trunc(thresholdPx));
  const remaining = el.scrollHeight - el.scrollTop - el.clientHeight;
  return remaining <= thr;
}
function ChatThread(props) {
  const threshold = typeof props.autoScrollThresholdPx === "number" && Number.isFinite(props.autoScrollThresholdPx) ? props.autoScrollThresholdPx : 120;
  const auto = props.autoScroll !== false;
  const list_ref = useRef6(null);
  const bottom_ref = useRef6(null);
  const [stick, set_stick] = useState11(true);
  const msgs = useMemo6(() => Array.isArray(props.messages) ? props.messages : [], [props.messages]);
  const groups = useMemo6(() => {
    const out = [];
    for (const message of msgs) {
      const last = out[out.length - 1];
      if (message.toolActivity && last?.[0]?.toolActivity && last[0].runId === message.runId)
        last.push(message);
      else
        out.push([message]);
    }
    return out;
  }, [msgs]);
  useEffect10(() => {
    if (!auto)
      return;
    const el = list_ref.current;
    if (!el)
      return;
    const on_scroll = () => {
      set_stick(is_near_bottom(el, threshold));
    };
    el.addEventListener("scroll", on_scroll, { passive: true });
    on_scroll();
    return () => el.removeEventListener("scroll", on_scroll);
  }, [auto, threshold]);
  const content_signature = useMemo6(() => {
    let total = 0;
    for (const m of msgs) {
      total += String(m.content ?? "").length;
      for (const file of m.artifactRefs || [])
        total += file.id.length + (file.name?.length || 0) + 1;
      total += (m.artifactIds?.length || 0) + (m.attachments?.length || 0);
      if (Array.isArray(m.media))
        for (const item of m.media)
          total += String(item?.src ?? "").length + 1;
    }
    return `${msgs.length}:${total}:${String(props.afterKey ?? "")}`;
  }, [msgs, props.afterKey]);
  useEffect10(() => {
    if (!auto)
      return;
    if (!stick)
      return;
    const list = list_ref.current;
    if (list)
      list.scrollTop = list.scrollHeight;
  }, [auto, stick, content_signature]);
  useEffect10(() => {
    if (!auto)
      return;
    const list = list_ref.current;
    if (!list)
      return;
    const follow = () => {
      if (stick)
        list.scrollTop = list.scrollHeight;
    };
    list.addEventListener("load", follow, true);
    list.addEventListener("loadedmetadata", follow, true);
    return () => {
      list.removeEventListener("load", follow, true);
      list.removeEventListener("loadedmetadata", follow, true);
    };
  }, [auto, stick]);
  return _jsxs11("div", { ref: list_ref, className: ["pc-chat-thread", props.className].filter(Boolean).join(" "), children: [!msgs.length ? props.empty || null : null, groups.map((group, idx) => {
    const m = group[0];
    const key = String(m.id || "") || String(m.ts || "") + ":" + String(m.role || "") + ":" + idx;
    return m.toolActivity ? _jsx13(ToolActivityGroup, { tools: group.map((message) => message.toolActivity), showCopy: props.messageProps?.showCopy }, key) : _jsx13(ChatMessageCard, { message: m, ...props.messageProps || {} }, key);
  }), props.after, _jsx13("div", { ref: bottom_ref })] });
}

// dist/composer_attachments.js
import { jsx as _jsx14, jsxs as _jsxs12 } from "react/jsx-runtime";
import { Icon as Icon6 } from "@abstractframework/ui-kit";
var PREVIEW_SCHEMES = /* @__PURE__ */ new Set(["blob:", "data:", "http:", "https:"]);
function previewSource(src) {
  const value = String(src || "").trim();
  if (!value)
    return void 0;
  try {
    const base = typeof window !== "undefined" && window.location ? window.location.href : "http://same-origin.invalid/";
    return PREVIEW_SCHEMES.has(new URL(value, base).protocol) ? value : void 0;
  } catch {
    return void 0;
  }
}
function chipMeta(item) {
  const size = typeof item.size === "number" ? formatBytes(item.size) : "";
  if (item.state === "queued")
    return { meta: `Waiting${size ? ` \xB7 ${size}` : ""}`, state: "waiting to upload" };
  if (item.state === "uploading")
    return { meta: `Uploading${size ? ` \xB7 ${size}` : ""}`, state: "uploading" };
  if (item.state === "attached")
    return { meta: size, state: "attached" };
  const reason = String(item.error || "").trim() || (item.state === "refused" ? "Refused" : "Upload failed");
  return { meta: reason, state: `not attached: ${reason}` };
}
function ComposerAttachmentChips(props) {
  const items = Array.isArray(props.items) ? props.items : [];
  if (!items.length)
    return null;
  return _jsx14("div", { className: "pc-attachment-chips", role: "list", "aria-label": "Attached files", children: items.map((item) => {
    const pending = item.state === "queued" || item.state === "uploading";
    const { meta, state } = chipMeta(item);
    const thumb = previewSource(item.thumbnailUrl);
    return _jsxs12("div", { role: "listitem", tabIndex: 0, className: `pc-attachment-chip is-${item.state}`, "data-state": item.state, "aria-label": `${item.name}, ${state}`, "aria-busy": pending || void 0, children: [_jsx14("span", { className: "pc-attachment-chip__icon", "aria-hidden": "true", children: thumb ? _jsx14("img", { className: "pc-attachment-chip__thumb", src: thumb, alt: "", loading: "lazy" }) : pending ? _jsx14("span", { className: "pc-attachment-chip__spinner" }) : item.state === "attached" ? _jsx14(Icon6, { name: "paperclip", size: 13 }) : _jsx14(Icon6, { name: "warning", size: 13 }) }), _jsxs12("span", { className: "pc-attachment-chip__body", children: [_jsx14("span", { className: "pc-attachment-chip__name", title: item.name, children: item.name }), meta ? _jsx14("span", { className: "pc-attachment-chip__meta", children: meta }) : null] }), item.state === "failed" && props.onRetry ? _jsxs12("button", { type: "button", className: "pc-attachment-chip__action pc-attachment-chip__retry", "data-action": "retry", "aria-label": `Retry ${item.name}`, title: "Retry upload", disabled: props.disabled, onClick: () => props.onRetry?.(item.id), children: [_jsx14(Icon6, { name: "refresh", size: 12 }), _jsx14("span", { children: "Retry" })] }) : null, props.onRemove ? _jsx14("button", { type: "button", className: "pc-attachment-chip__action", "data-action": "remove", "aria-label": `Remove ${item.name}`, title: `Remove ${item.name}`, disabled: props.disabled, onClick: () => props.onRemove?.(item.id), children: _jsx14(Icon6, { name: "x", size: 12 }) }) : null] }, item.id);
  }) });
}

// dist/file_drop.js
function dragCarriesFiles(types) {
  if (!types)
    return false;
  for (let index = 0; index < types.length; index += 1)
    if (types[index] === "Files")
      return true;
  return false;
}
function draggedFileCount(transfer) {
  const items = transfer?.items;
  if (!items || !items.length)
    return null;
  let count = 0;
  for (let index = 0; index < items.length; index += 1)
    if (items[index]?.kind === "file")
      count += 1;
  return count > 0 ? count : null;
}
function dropZoneLabel(count) {
  if (count === 1)
    return "Drop file to attach";
  if (typeof count === "number" && count > 1)
    return `Drop ${count} files to attach`;
  return "Drop files to attach";
}
function droppedFiles(transfer) {
  const files2 = [];
  const folders = [];
  const items = transfer?.items;
  if (items && items.length) {
    for (let index = 0; index < items.length; index += 1) {
      const item = items[index];
      if (!item || item.kind !== "file")
        continue;
      const entry = typeof item.webkitGetAsEntry === "function" ? item.webkitGetAsEntry() : null;
      const file = typeof item.getAsFile === "function" ? item.getAsFile() : null;
      if (entry?.isDirectory)
        folders.push(entry.name || file?.name || "folder");
      else if (file)
        files2.push(file);
    }
    return { files: files2, folders };
  }
  const list = transfer?.files;
  if (list) {
    for (let index = 0; index < list.length; index += 1)
      if (list[index])
        files2.push(list[index]);
  }
  return { files: files2, folders };
}
function folderRefusal(folders) {
  if (!folders.length)
    return "";
  if (folders.length === 1)
    return `"${folders[0]}" is a folder. Folders are not supported: drop the files inside it instead.`;
  return `${folders.length} folders were dropped. Folders are not supported: drop the files inside them instead.`;
}
var IMAGE_EXTENSIONS = {
  "image/png": "png",
  "image/jpeg": "jpg",
  "image/gif": "gif",
  "image/webp": "webp",
  "image/heic": "heic",
  "image/tiff": "tiff",
  "image/bmp": "bmp"
};
function pad(value) {
  return String(value).padStart(2, "0");
}
function pastedFileName(name, type, now) {
  const trimmed = String(name || "").trim();
  if (trimmed && !/^image\.(png|jpe?g|gif|webp|heic|tiff?|bmp)$/i.test(trimmed))
    return trimmed;
  const extension = IMAGE_EXTENSIONS[String(type || "").toLowerCase()] || trimmed.split(".").pop() || "bin";
  const stamp = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} at ${pad(now.getHours())}.${pad(now.getMinutes())}.${pad(now.getSeconds())}`;
  return `${String(type || "").startsWith("image/") || !trimmed ? "Pasted image" : "Pasted file"} ${stamp}.${extension}`;
}
function pastedFiles(clipboard, now = /* @__PURE__ */ new Date()) {
  if (!clipboard)
    return [];
  const types = clipboard.types ? Array.from(clipboard.types) : [];
  if (types.includes("text/plain") && types.includes("text/html"))
    return [];
  const { files: files2 } = droppedFiles(clipboard);
  return files2.map((file) => {
    const name = pastedFileName(file.name, file.type, now);
    if (name === file.name)
      return file;
    return new File([file], name, { type: file.type, lastModified: file.lastModified });
  });
}
var DragPresence = class {
  constructor(staleMs = 1200) {
    this.staleMs = staleMs;
    this.depth = 0;
    this.lastSeen = 0;
  }
  enter(now) {
    this.depth += 1;
    this.lastSeen = now;
  }
  over(now) {
    if (this.depth === 0)
      this.depth = 1;
    this.lastSeen = now;
  }
  /** Returns true while the drag is still somewhere over the window. */
  leave(now) {
    this.depth = Math.max(0, this.depth - 1);
    this.lastSeen = now;
    return this.depth > 0;
  }
  reset() {
    this.depth = 0;
  }
  active(now) {
    return this.depth > 0 && now - this.lastSeen < this.staleMs;
  }
};

// dist/workflow_interaction.js
import { jsxs as _jsxs13, jsx as _jsx15 } from "react/jsx-runtime";
import { useEffect as useEffect11, useRef as useRef7, useState as useState12 } from "react";
import { Icon as Icon7 } from "@abstractframework/ui-kit";

// dist/workflow_interaction_core.js
function submitWorkflowInteraction(interaction, submission) {
  if (interaction.kind === "ask-user") {
    if (submission.kind === "choice" || submission.kind === "free-text")
      return interaction.onSubmit(submission.answer);
    if (submission.kind === "skip" && interaction.onSkip)
      return interaction.onSkip();
    throw new Error("Invalid submission for ask-user interaction");
  }
  if (interaction.kind === "tool-approval") {
    if (submission.kind === "approve")
      return interaction.onApprove();
    if (submission.kind === "deny")
      return interaction.onDeny();
    if (submission.kind === "approve-all" && interaction.onApproveAll)
      return interaction.onApproveAll();
    if (submission.kind === "approve-session" && interaction.onApproveForSession)
      return interaction.onApproveForSession();
    if (submission.kind === "deny-chat") {
      const option = interaction.denyOptions?.find((item) => item.key === submission.key);
      if (option)
        return option.onDeny();
    }
    if (submission.kind === "approve-kind") {
      const entry = interaction.approveKinds?.find((item) => item.kind === submission.toolset);
      if (entry)
        return entry.onApprove();
    }
    throw new Error("Invalid submission for tool-approval interaction");
  }
  if (submission.kind === "event")
    return interaction.onSend(submission.payload);
  throw new Error("Invalid submission for event-wait interaction");
}

// dist/workflow_interaction.js
var WORKFLOW_INTERACTION_LABELS = {
  deny: "Deny",
  allowOnce: "Allow once",
  allowForChat: "Allow for this chat",
  allowAll: "Allow all enabled tools",
  /** Approve one toolset (a `GET discovery/tools` row's `toolset`) for the conversation. */
  allowKindForChat: (toolset) => `Allow all ${toolset} tools for this chat`,
  /** The labeled line when the gateway cannot store conversation policies (no silent hedge). */
  /** The local, run-scoped grant (no gateway chat policy): says what it does. */
  allowForRun: "Allow for this run",
  localChatPolicyNote: "Allowed for this chat in this browser only \u2014 the gateway cannot store chat policies.",
  localRunPolicyNote: "Allowed until this run ends, in this browser only \u2014 the gateway cannot store chat policies.",
  /** Deny for the chat (session policy, gateway mode); offered under "More". */
  denyToolForChat: (tool) => `Always deny ${tool} in this chat`,
  denyKindForChat: (toolset) => `Always deny ${toolset} tools in this chat`,
  /** What a deny reaches, stated before the click and in its confirmation (contract §4.3). */
  denyForChatNote: "Always deny applies to every run of this chat, automations and runs that read other people's text included, until the policy is reset; a request shown before it is refused even if approved later.",
  /** No `scope` was served: said so, never composed. */
  noScopeNote: "The gateway did not say where this grant applies.",
  /** The capability read failed: no chat grant is offered. */
  unavailablePolicyNote: (reason) => `Allow for this chat is unavailable: ${reason || "the gateway's capabilities could not be read."} Allow once still works.`,
  decideLater: "Decide later",
  submit: "Submit",
  skip: "Continue without answering",
  keepWaiting: "Keep waiting",
  sendEvent: "Send event"
};
function errorMessage(error) {
  const message = error instanceof Error ? error.message : String(error || "Unknown error");
  return message.trim() || "Unknown error";
}
function ActionError(props) {
  return _jsxs13("div", { className: "pc-workflow-interaction__error", role: "alert", children: [_jsxs13("span", { children: ["Could not complete that action: ", props.message] }), _jsx15("button", { type: "button", className: "pc-workflow-interaction__retry", onClick: props.onRetry, disabled: props.disabled, children: "Try again" })] });
}
var L = WORKFLOW_INTERACTION_LABELS;
function WorkflowInteractionPanel(props) {
  const interaction = props.interaction;
  const card = props.variant === "card";
  const [freeText, setFreeText] = useState12("");
  const [payload, setPayload] = useState12(() => interaction.kind === "event-wait" ? interaction.initialPayload || "" : "");
  const [pending, setPending] = useState12(null);
  const [settled, setSettled] = useState12(false);
  const [outcome, setOutcome] = useState12("");
  const [failure, setFailure] = useState12(null);
  const interactionKey = `${interaction.kind}:${interaction.id}`;
  const activeKeyRef = useRef7(interactionKey);
  const inFlightRef = useRef7(false);
  const settledRef = useRef7(false);
  const mountedRef = useRef7(true);
  const sequenceRef = useRef7(0);
  if (activeKeyRef.current !== interactionKey) {
    activeKeyRef.current = interactionKey;
    inFlightRef.current = false;
    settledRef.current = false;
    sequenceRef.current += 1;
  }
  const disabled = Boolean(props.disabled) || pending !== null || settled || inFlightRef.current || settledRef.current;
  const run = async (submission, callback) => {
    if (Boolean(props.disabled) || inFlightRef.current || settledRef.current)
      return;
    const requestKey = interactionKey;
    const sequence = ++sequenceRef.current;
    inFlightRef.current = true;
    setFailure(null);
    setOutcome("");
    setPending(submission);
    try {
      const result = await callback();
      if (!mountedRef.current || activeKeyRef.current !== requestKey || sequenceRef.current !== sequence)
        return;
      settledRef.current = true;
      setSettled(true);
      const note = result && typeof result === "object" && typeof result.outcomeNote === "string" ? String(result.outcomeNote) : "";
      setOutcome(`Response sent. Waiting for the workflow to continue.${note ? ` ${note}` : ""}`);
    } catch (error) {
      if (!mountedRef.current || activeKeyRef.current !== requestKey || sequenceRef.current !== sequence)
        return;
      setFailure({ submission, message: errorMessage(error) });
      setOutcome("The action failed. You can try again.");
      props.onError?.(error);
    } finally {
      if (!mountedRef.current || activeKeyRef.current !== requestKey || sequenceRef.current !== sequence)
        return;
      inFlightRef.current = false;
      setPending(null);
    }
  };
  const defer = async (callback) => {
    if (Boolean(props.disabled) || inFlightRef.current || settledRef.current)
      return;
    const requestKey = interactionKey;
    try {
      await callback();
      if (!mountedRef.current || activeKeyRef.current !== requestKey)
        return;
      setFailure(null);
      setOutcome(interaction.kind === "tool-approval" ? "Left for later. Nothing was sent; the run keeps waiting for this decision." : "Left for later. Nothing was sent; the run keeps waiting for your answer.");
    } catch (error) {
      if (!mountedRef.current || activeKeyRef.current !== requestKey)
        return;
      setOutcome(`Could not leave this for later: ${errorMessage(error)}`);
      props.onError?.(error);
    }
  };
  useEffect11(() => {
    setFreeText("");
    setPayload(interaction.kind === "event-wait" ? interaction.initialPayload || "" : "");
    setFailure(null);
    setPending(null);
    setSettled(false);
    setOutcome("");
  }, [interactionKey]);
  useEffect11(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      sequenceRef.current += 1;
      inFlightRef.current = false;
    };
  }, []);
  const retry = () => {
    if (!failure)
      return;
    void run(failure.submission, () => submitWorkflowInteraction(interaction, failure.submission));
  };
  const title = interaction.title || (interaction.kind === "tool-approval" ? "Tool approval required" : "Input required");
  const deferButton = (onDefer, label) => onDefer ? _jsx15("button", { type: "button", className: "pc-workflow-interaction__defer", "data-decision": "defer", disabled, onClick: () => void defer(onDefer), children: label }) : null;
  let body;
  if (interaction.kind === "ask-user") {
    body = _jsxs13("div", { className: "pc-workflow-interaction__body", children: [_jsx15("div", { className: "pc-workflow-interaction__prompt", children: interaction.prompt }), interaction.choices?.length ? _jsx15("div", { className: "pc-workflow-interaction__choices", "aria-label": "Choices", children: interaction.choices.map((choice) => _jsxs13("button", { type: "button", className: "pc-workflow-interaction__choice", "data-decision": "choice", disabled: disabled || choice.disabled, onClick: () => void run({ kind: "choice", answer: choice.id }, () => interaction.onSubmit(choice.id)), children: [_jsx15("span", { children: choice.label }), choice.description ? _jsx15("small", { children: choice.description }) : null] }, choice.id)) }) : null, interaction.allowFreeText !== false ? _jsxs13("div", { className: "pc-workflow-interaction__entry", children: [_jsx15("textarea", { "aria-label": "Response", value: freeText, onChange: (event) => setFreeText(event.target.value), placeholder: interaction.freeTextPlaceholder || "Type a response", rows: card ? 1 : 2, disabled, onKeyDown: (event) => {
      if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing || event.keyCode === 229)
        return;
      event.preventDefault();
      if (freeText.trim())
        void run({ kind: "free-text", answer: freeText }, () => interaction.onSubmit(freeText));
    } }, `${interactionKey}:text`), _jsx15("button", { type: "button", className: "pc-btn", "data-decision": "submit", disabled: disabled || !freeText.trim(), onClick: () => void run({ kind: "free-text", answer: freeText }, () => interaction.onSubmit(freeText)), children: pending?.kind === "free-text" ? "Sending\u2026" : interaction.submitLabel || L.submit })] }) : null, interaction.onSkip || interaction.onDefer ? _jsxs13("div", { className: "pc-workflow-interaction__buttons pc-workflow-interaction__buttons--secondary", children: [deferButton(interaction.onDefer, interaction.deferLabel || L.keepWaiting), interaction.onSkip ? _jsx15("button", { type: "button", className: "pc-workflow-interaction__skip", "data-decision": "skip", disabled, onClick: () => void run({ kind: "skip" }, interaction.onSkip), children: pending?.kind === "skip" ? "Continuing\u2026" : interaction.skipLabel || L.skip }) : null] }) : null] });
  } else if (interaction.kind === "tool-approval") {
    const reason = String(interaction.disabledReason || "").trim();
    const broadDisabled = disabled || Boolean(reason);
    const scopes = [
      !reason && interaction.onApproveForSession && interaction.approveForSessionDescription ? interaction.approveForSessionDescription : "",
      !reason && interaction.onApproveAll && interaction.approveAllDescription ? interaction.approveAllDescription : ""
    ].filter(Boolean);
    const scopeSummary = scopes.length ? String(interaction.broadScopeSummary || "").trim() : "";
    body = _jsxs13("div", { className: "pc-workflow-interaction__body", children: [_jsxs13("div", { className: "pc-workflow-interaction__prompt", children: ["Allow ", _jsx15("strong", { children: interaction.toolName }), " to run?"] }), interaction.detail ? card ? _jsxs13("details", { className: "pc-workflow-interaction__review", children: [_jsx15("summary", { children: "Review" }), _jsx15("div", { className: "pc-workflow-interaction__detail", children: interaction.detail })] }) : _jsx15("div", { className: "pc-workflow-interaction__detail", children: interaction.detail }) : null, _jsxs13("div", { className: "pc-workflow-interaction__buttons", children: [deferButton(interaction.onDefer, interaction.deferLabel || L.decideLater), _jsx15("button", { type: "button", className: "pc-workflow-interaction__deny", "data-decision": "deny", disabled, onClick: () => void run({ kind: "deny" }, interaction.onDeny), children: pending?.kind === "deny" ? "Denying\u2026" : interaction.denyLabel || L.deny }), _jsx15("button", { type: "button", className: "pc-btn", "data-decision": "approve", disabled, onClick: () => void run({ kind: "approve" }, interaction.onApprove), children: pending?.kind === "approve" ? "Allowing\u2026" : interaction.approveLabel || L.allowOnce }), interaction.onApproveForSession ? _jsx15("button", { type: "button", className: "pc-workflow-interaction__allow-session", "data-decision": "approve-session", disabled: broadDisabled, title: reason || interaction.approveForSessionDescription || void 0, onClick: () => void run({ kind: "approve-session" }, interaction.onApproveForSession), children: pending?.kind === "approve-session" ? "Allowing\u2026" : interaction.approveForSessionLabel || L.allowForChat }) : null, (interaction.approveKinds || []).map((entry) => _jsx15("button", { type: "button", className: "pc-workflow-interaction__allow-session pc-workflow-interaction__allow-kind", "data-decision": "approve-kind", "data-kind": entry.kind, disabled: broadDisabled, title: reason || interaction.approveForSessionDescription || void 0, onClick: () => void run({ kind: "approve-kind", toolset: entry.kind }, entry.onApprove), children: pending?.kind === "approve-kind" && pending.toolset === entry.kind ? "Allowing\u2026" : entry.label || L.allowKindForChat(entry.kind) }, entry.kind)), interaction.onApproveAll ? _jsx15("button", { type: "button", className: "pc-workflow-interaction__allow-all", "data-decision": "approve-all", disabled: broadDisabled, title: reason || interaction.approveAllDescription || void 0, onClick: () => void run({ kind: "approve-all" }, interaction.onApproveAll), children: pending?.kind === "approve-all" ? "Allowing\u2026" : interaction.approveAllLabel || L.allowAll }) : null] }), scopeSummary ? _jsx15("p", { className: "pc-workflow-interaction__scope", "data-scope-summary": "", children: scopeSummary }) : null, interaction.remember ? _jsxs13("label", { className: "pc-workflow-interaction__remember", children: [_jsx15("input", { type: "checkbox", checked: interaction.remember.checked, disabled, onChange: (event) => interaction.remember.onChange(event.target.checked) }), _jsx15("span", { children: interaction.remember.label })] }) : null, interaction.deniedNote ? _jsx15("p", { className: "pc-workflow-interaction__unavailable", role: "note", "data-denied-note": "", children: interaction.deniedNote }) : null, interaction.denyOptions?.length ? _jsxs13("details", { className: "pc-workflow-interaction__more", "data-more": "", children: [_jsx15("summary", { children: "More" }), _jsx15("p", { className: "pc-workflow-interaction__scope", children: L.denyForChatNote }), _jsx15("div", { className: "pc-workflow-interaction__buttons", children: interaction.denyOptions.map((option) => _jsx15("button", { type: "button", className: "pc-workflow-interaction__deny", "data-decision": "deny-chat", "data-key": option.key, disabled, onClick: () => void run({ kind: "deny-chat", key: option.key }, option.onDeny), children: pending?.kind === "deny-chat" && pending.key === option.key ? "Denying\u2026" : option.label }, option.key)) })] }) : null, interaction.policySummary ? _jsx15("p", { className: "pc-workflow-interaction__scope", "data-policy-summary": "", children: interaction.policySummary }) : null, interaction.scopeNote ? _jsx15("p", { className: "pc-workflow-interaction__scope-note", role: "note", "data-scope-note": "", children: interaction.scopeNote }) : null, interaction.notCovered ? _jsx15("p", { className: "pc-workflow-interaction__unavailable", role: "note", "data-not-covered": "", children: interaction.notCovered }) : null, reason && (interaction.onApproveAll || interaction.onApproveForSession || interaction.approveKinds?.length) ? _jsx15("p", { className: "pc-workflow-interaction__unavailable", role: "note", children: reason }) : null, scopeSummary && scopes.length ? _jsxs13("details", { className: "pc-workflow-interaction__scope-details", "data-scope-details": "", children: [_jsx15("summary", { children: "What the broader choices allow" }), scopes.map((text) => _jsx15("p", { className: "pc-workflow-interaction__scope", children: text }, text))] }) : scopes.map((text) => _jsx15("p", { className: "pc-workflow-interaction__scope", children: text }, text))] });
  } else {
    body = _jsxs13("div", { className: "pc-workflow-interaction__body", children: [_jsx15("div", { className: "pc-workflow-interaction__prompt", children: interaction.prompt }), _jsxs13("label", { className: "pc-workflow-interaction__entry", children: [_jsx15("span", { children: interaction.payloadLabel || (interaction.eventName ? `Payload for ${interaction.eventName}` : "Event payload") }), _jsx15("textarea", { value: payload, onChange: (event) => setPayload(event.target.value), placeholder: interaction.payloadPlaceholder || "Enter payload", rows: card ? 1 : 2, "aria-label": interaction.payloadLabel || (interaction.eventName ? `Payload for ${interaction.eventName}` : "Event payload"), disabled }, `${interactionKey}:payload`)] }), _jsx15("div", { className: "pc-workflow-interaction__buttons", children: _jsx15("button", { type: "button", className: "pc-btn", "data-decision": "send-event", disabled, onClick: () => void run({ kind: "event", payload }, () => interaction.onSend(payload)), children: pending?.kind === "event" ? "Sending\u2026" : interaction.sendLabel || L.sendEvent }) })] });
  }
  return _jsxs13("section", { className: ["pc-workflow-interaction", card ? "pc-workflow-interaction--card" : ""].filter(Boolean).join(" "), "data-variant": card ? "card" : "panel", "aria-labelledby": `pc-workflow-interaction-${interactionKey}`, children: [_jsxs13("div", { className: "pc-workflow-interaction__heading", children: [_jsx15(Icon7, { name: interaction.kind === "tool-approval" ? "warning" : interaction.kind === "event-wait" ? "history" : "info", size: card ? 14 : 16 }), _jsxs13("div", { children: [_jsx15("h3", { tabIndex: -1, id: `pc-workflow-interaction-${interactionKey}`, children: title }), interaction.description ? _jsx15("div", { className: "pc-workflow-interaction__description", children: interaction.description }) : null] })] }), body, failure ? _jsx15(ActionError, { message: failure.message, onRetry: retry, disabled }) : null, _jsx15("div", { className: "pc-workflow-interaction__outcome", "aria-live": "polite", children: outcome })] });
}

// dist/workflow_chat.js
function messageFor(error) {
  const message = error instanceof Error ? error.message : String(error || "Unknown error");
  return message.trim() || "Unknown error";
}
function WorkflowChat(props) {
  useAfTooltips();
  const artifactFetch = useMemo7(() => props.artifactFetch ? boundedArtifactFetch(props.artifactFetch) : void 0, [props.artifactFetch, props.attachmentScope]);
  const transcript = useMessageArtifacts(props.messages, artifactFetch, props.attachmentScope || "", props.attachmentRun);
  const [sendPending, setSendPending] = useState13(false);
  const [cancelPending, setCancelPending] = useState13(false);
  const [attachPending, setAttachPending] = useState13(false);
  const [error, setError] = useState13(null);
  const [steerMode, setSteerMode] = useState13(() => props.steer?.modes?.[0] || "guide");
  const [steerStatus, setSteerStatus] = useState13(null);
  const [copyState, setCopyState] = useState13("idle");
  const sendAbortRef = useRef8(null);
  const mountedRef = useRef8(true);
  const sendInFlightRef = useRef8(false);
  const cancelInFlightRef = useRef8(false);
  const attachInFlightRef = useRef8(false);
  const sendSequenceRef = useRef8(0);
  const cancelSequenceRef = useRef8(0);
  const attachSequenceRef = useRef8(0);
  useEffect12(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      sendSequenceRef.current += 1;
      cancelSequenceRef.current += 1;
      attachSequenceRef.current += 1;
      sendInFlightRef.current = false;
      cancelInFlightRef.current = false;
      attachInFlightRef.current = false;
      sendAbortRef.current?.abort();
      sendAbortRef.current = null;
    };
  }, []);
  const blocked = Boolean(props.blockedNotice);
  const disabled = Boolean(props.disabled) || blocked;
  const sending = Boolean(props.busy) || sendPending;
  const composerBusy = sendPending || Boolean(props.busy) && !props.sendWhileBusy;
  const stopState = props.stopState || null;
  const stopping = stopState?.phase === "stopping";
  const steer = props.steer && typeof props.steer.onSteer === "function" ? props.steer : null;
  const steerModes = steer ? steer.modes?.length ? steer.modes : ["guide"] : [];
  const activeSteerMode = steerModes.includes(steerMode) ? steerMode : steerModes[0] || "guide";
  const steering = Boolean(steer) && Boolean(props.busy);
  const attachmentItems = Array.isArray(props.attachmentItems) ? props.attachmentItems : [];
  useEffect12(() => {
    setSteerStatus(null);
  }, [Boolean(props.busy)]);
  const acceptsFiles = typeof props.onFiles === "function";
  const sectionRef = useRef8(null);
  const [drag, setDrag] = useState13(null);
  const [announcement, setAnnouncement] = useState13("");
  const onFilesRef = useRef8(props.onFiles);
  onFilesRef.current = props.onFiles;
  const disabledRef = useRef8(disabled);
  disabledRef.current = disabled;
  const deliverFiles = async (files2, folders) => {
    const handler = onFilesRef.current;
    if (!handler)
      return;
    if (disabledRef.current) {
      setError({
        action: "attach",
        message: "attachments are unavailable right now."
      });
      return;
    }
    if (folders.length)
      setError({ action: "attach", message: folderRefusal(folders) });
    else if (!files2.length) {
      setError({ action: "attach", message: "the drop contained no files." });
      return;
    } else
      setError(null);
    if (!files2.length)
      return;
    setAnnouncement(`Attaching ${files2.length} ${files2.length === 1 ? "file" : "files"}\u2026`);
    try {
      await handler(files2);
    } catch (reason) {
      if (mountedRef.current)
        setError({ action: "attach", message: messageFor(reason) });
    }
  };
  const deliverRef = useRef8(deliverFiles);
  deliverRef.current = deliverFiles;
  useEffect12(() => {
    if (!acceptsFiles || typeof window === "undefined")
      return;
    const presence = new DragPresence();
    let watchdog = 0;
    const inside = (target) => Boolean(sectionRef.current && target instanceof Node && sectionRef.current.contains(target));
    const hide = () => {
      presence.reset();
      if (watchdog)
        window.clearInterval(watchdog);
      watchdog = 0;
      setDrag(null);
    };
    const arm = () => {
      if (watchdog)
        return;
      watchdog = window.setInterval(() => {
        if (!presence.active(Date.now()))
          hide();
      }, 250);
    };
    const onEnter = (event) => {
      if (!dragCarriesFiles(event.dataTransfer?.types))
        return;
      presence.enter(Date.now());
      const over = inside(event.target);
      const count = draggedFileCount(event.dataTransfer);
      setDrag((previous) => previous && previous.over === over && previous.count === (count ?? previous.count) ? previous : { count: count ?? previous?.count ?? null, over });
      arm();
    };
    const onOver = (event) => {
      if (!dragCarriesFiles(event.dataTransfer?.types))
        return;
      event.preventDefault();
      presence.over(Date.now());
      const over = inside(event.target);
      if (event.dataTransfer)
        event.dataTransfer.dropEffect = over && !disabledRef.current ? "copy" : "none";
      setDrag((previous) => previous && previous.over === over ? previous : {
        count: previous?.count ?? draggedFileCount(event.dataTransfer),
        over
      });
      arm();
    };
    const onLeave = (event) => {
      if (!dragCarriesFiles(event.dataTransfer?.types))
        return;
      if (!presence.leave(Date.now()))
        hide();
    };
    const onDrop = (event) => {
      if (!dragCarriesFiles(event.dataTransfer?.types))
        return;
      const over = inside(event.target);
      const handledElsewhere = event.defaultPrevented && !over;
      event.preventDefault();
      hide();
      if (handledElsewhere)
        return;
      if (!over) {
        setError({
          action: "attach",
          message: "drop files on the conversation to attach them."
        });
        return;
      }
      const { files: files2, folders } = droppedFiles(event.dataTransfer);
      void deliverRef.current(files2, folders);
    };
    const onKey = (event) => {
      if (event.key === "Escape" && presence.depth > 0)
        hide();
    };
    window.addEventListener("dragenter", onEnter);
    window.addEventListener("dragover", onOver);
    window.addEventListener("dragleave", onLeave);
    window.addEventListener("drop", onDrop);
    window.addEventListener("dragend", hide);
    window.addEventListener("blur", hide);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("dragenter", onEnter);
      window.removeEventListener("dragover", onOver);
      window.removeEventListener("dragleave", onLeave);
      window.removeEventListener("drop", onDrop);
      window.removeEventListener("dragend", hide);
      window.removeEventListener("blur", hide);
      window.removeEventListener("keydown", onKey);
      if (watchdog)
        window.clearInterval(watchdog);
    };
  }, [acceptsFiles]);
  const onPaste = (event) => {
    if (!acceptsFiles || disabled)
      return;
    const files2 = pastedFiles(event.clipboardData);
    if (!files2.length)
      return;
    event.preventDefault();
    void deliverFiles(files2, []);
  };
  const dropZone = drag ? _jsxs14("div", { className: [
    "pc-workflow-chat__dropzone",
    drag.over ? "is-over" : "",
    disabled ? "is-disabled" : ""
  ].filter(Boolean).join(" "), "aria-hidden": "true", children: [_jsx16("span", { className: "pc-workflow-chat__dropzone-icon", children: _jsx16(Icon8, { name: "paperclip", size: 18 }) }), _jsxs14("span", { className: "pc-workflow-chat__dropzone-text", children: [_jsx16("strong", { children: disabled ? "Attachments are unavailable right now" : dropZoneLabel(drag.count) }), disabled ? null : _jsx16("span", { children: drag.over ? "Release to upload to this conversation" : "Drop anywhere on the conversation" })] })] }) : null;
  const liveMessage = drag ? disabled ? "Attachments are unavailable right now" : dropZoneLabel(drag.count) : announcement;
  const submitSteer = async (draft) => {
    if (!steer)
      return;
    const mode = activeSteerMode;
    const sequence = ++sendSequenceRef.current;
    sendInFlightRef.current = true;
    setError(null);
    setSteerStatus(null);
    setSendPending(true);
    try {
      const result = await steer.onSteer(draft, mode);
      if (!mountedRef.current || sendSequenceRef.current !== sequence)
        return;
      if (!result?.accepted && !result?.duplicate) {
        setError({
          action: "steer",
          message: "the gateway did not accept this message (accepted=false)."
        });
        return;
      }
      setSteerStatus({
        mode,
        ...typeof result.seq === "number" ? { seq: result.seq } : {},
        duplicate: Boolean(result.duplicate)
      });
      props.onDraftChange("");
    } catch (reason) {
      if (mountedRef.current && sendSequenceRef.current === sequence)
        setError({ action: "steer", message: messageFor(reason) });
    } finally {
      if (mountedRef.current && sendSequenceRef.current === sequence) {
        sendInFlightRef.current = false;
        setSendPending(false);
      }
    }
  };
  const submit = async () => {
    const draft = String(props.draft || "");
    if (disabled || sendInFlightRef.current || !draft.trim())
      return;
    if (steering)
      return void submitSteer(draft);
    if (!props.sendWhileBusy && props.busy)
      return;
    const block = attachmentItems.length ? unattachedSendBlock(attachmentItems) : null;
    if (block) {
      setError({ action: "send", message: block });
      return;
    }
    const sequence = ++sendSequenceRef.current;
    const abort = new AbortController();
    sendAbortRef.current = abort;
    sendInFlightRef.current = true;
    setError(null);
    setSteerStatus(null);
    setSendPending(true);
    try {
      await props.onSend(draft, { signal: abort.signal });
    } catch (reason) {
      if (mountedRef.current && sendSequenceRef.current === sequence && !abort.signal.aborted)
        setError({ action: "send", message: messageFor(reason) });
    } finally {
      if (sendAbortRef.current === abort)
        sendAbortRef.current = null;
      if (mountedRef.current && sendSequenceRef.current === sequence) {
        sendInFlightRef.current = false;
        setSendPending(false);
      }
    }
  };
  const cancel = async () => {
    if (disabled || cancelInFlightRef.current || !props.onCancel)
      return;
    const sequence = ++cancelSequenceRef.current;
    cancelInFlightRef.current = true;
    setError(null);
    setCancelPending(true);
    const inFlight = sendAbortRef.current;
    const signalOwner = inFlight || new AbortController();
    signalOwner.abort(new DOMException("Stopped by the user", "AbortError"));
    try {
      await props.onCancel(signalOwner.signal);
    } catch (reason) {
      if (mountedRef.current && cancelSequenceRef.current === sequence)
        setError({ action: "cancel", message: messageFor(reason) });
    } finally {
      if (mountedRef.current && cancelSequenceRef.current === sequence) {
        cancelInFlightRef.current = false;
        setCancelPending(false);
      }
    }
  };
  const attach = async () => {
    if (disabled || attachInFlightRef.current || !props.onAttach)
      return;
    const sequence = ++attachSequenceRef.current;
    attachInFlightRef.current = true;
    setError(null);
    setAttachPending(true);
    try {
      await props.onAttach();
    } catch (reason) {
      if (mountedRef.current && attachSequenceRef.current === sequence)
        setError({ action: "attach", message: messageFor(reason) });
    } finally {
      if (mountedRef.current && attachSequenceRef.current === sequence) {
        attachInFlightRef.current = false;
        setAttachPending(false);
      }
    }
  };
  const retry = () => {
    if (!error)
      return;
    if (error.action === "send" || error.action === "steer")
      void submit();
    if (error.action === "cancel")
      void cancel();
    if (error.action === "attach")
      void attach();
  };
  const toolbar = props.toolbar || null;
  const transcriptMarkdown = (heading) => chatToMarkdown((Array.isArray(props.messages) ? props.messages : []).filter((m) => !m.toolActivity && !m.live && String(m.content || "").trim()), heading ? { heading } : void 0);
  const runToolbar = async (action) => {
    if (disabled)
      return;
    setError(null);
    try {
      await action();
    } catch (reason) {
      if (mountedRef.current)
        setError({ action: "toolbar", message: messageFor(reason) });
    }
  };
  const copyTranscript = async () => {
    const ok = await copyText(transcriptMarkdown());
    if (!mountedRef.current)
      return;
    setCopyState(ok ? "copied" : "failed");
    if (typeof window !== "undefined")
      window.setTimeout(() => mountedRef.current && setCopyState("idle"), 1200);
  };
  const toolbarRow = toolbar ? _jsxs14("div", { className: "pc-workflow-chat__toolbar", role: "toolbar", "aria-label": "Conversation actions", children: [toolbar.onNewSession ? _jsxs14("button", { type: "button", className: "pc-workflow-chat__icon-button", "data-toolbar": "new", disabled, onClick: () => void runToolbar(toolbar.onNewSession), children: [_jsx16(Icon8, { name: "plus", size: 14 }), _jsx16("span", { children: "New chat" })] }) : null, toolbar.onClear ? _jsxs14("button", { type: "button", className: "pc-workflow-chat__icon-button", "data-toolbar": "clear", disabled, onClick: () => void runToolbar(toolbar.onClear), children: [_jsx16(Icon8, { name: "trash", size: 14 }), _jsx16("span", { children: "Clear" })] }) : null, toolbar.copyTranscript ? _jsxs14("button", { type: "button", className: "pc-workflow-chat__icon-button", "data-toolbar": "copy", onClick: () => void copyTranscript(), children: [_jsx16(Icon8, { name: copyState === "copied" ? "check" : "copy", size: 14 }), _jsx16("span", { children: copyState === "copied" ? "Copied" : copyState === "failed" ? "Copy failed" : "Copy" })] }) : null, toolbar.exportTranscript ? _jsxs14("button", { type: "button", className: "pc-workflow-chat__icon-button", "data-toolbar": "export", onClick: () => {
    const spec = toolbar.exportTranscript;
    downloadTextFile({
      filename: spec.filename,
      text: transcriptMarkdown(spec.heading),
      mime: "text/markdown;charset=utf-8"
    });
  }, children: [_jsx16(Icon8, { name: "download", size: 14 }), _jsx16("span", { children: "Export" })] }) : null] }) : null;
  const steerLabel = activeSteerMode === "queue" ? "Queue" : "Steer";
  const steerNote = steerStatus ? steerStatus.mode === "queue" ? `Queued for the next turn${typeof steerStatus.seq === "number" ? ` (seq ${steerStatus.seq})` : ""}.` : `${steerStatus.duplicate ? "Already queued" : "Queued"}${typeof steerStatus.seq === "number" ? ` (seq ${steerStatus.seq})` : ""}. ${steer?.parked ? "The run is waiting: your guidance delivers at its next wake (steers do not wake runs)." : "Delivers at the run's next loop boundary."}` : "";
  return _jsxs14("section", { ref: sectionRef, className: [
    "pc-workflow-chat",
    drag ? "pc-workflow-chat--dragging" : "",
    drag?.over ? "pc-workflow-chat--drag-over" : "",
    props.className
  ].filter(Boolean).join(" "), "aria-label": "Workflow chat", "data-stream-replies": props.streamReplies || "gateway_default", children: [props.header || toolbarRow ? _jsxs14("header", { className: [
    "pc-workflow-chat__header",
    toolbarRow ? "pc-workflow-chat__header--toolbar" : ""
  ].filter(Boolean).join(" "), children: [props.header ? _jsx16("div", { className: "pc-workflow-chat__header-main", children: props.header }) : null, toolbarRow] }) : null, _jsx16("div", { className: "pc-workflow-chat__transcript", children: _jsxs14(ArtifactFetchContext.Provider, { value: artifactFetch, children: [transcript.error && _jsxs14("p", { role: "status", className: "pc-workflow-chat__error", children: [transcript.error, " ", _jsx16("button", { type: "button", onClick: transcript.retry, children: "Retry attachment check" })] }), _jsx16(ChatThread, { messages: transcript.messages, empty: props.emptyState, autoScroll: true, messageProps: {
    ...props.messageProps,
    ...props.messageProps?.renderFooter ? {
      renderFooter: (m) => props.messageProps.renderFooter(props.messages.find((original) => original === m || original.id && original.id === m.id) || m)
    } : {},
    ...props.renderMarkdown ? { renderMarkdown: props.renderMarkdown } : {}
  }, after: _jsxs14(_Fragment6, { children: [props.interaction ? _jsx16(WorkflowInteractionPanel, { interaction: props.interaction, disabled }) : null, blocked ? _jsx16("div", { className: "pc-workflow-chat__blocked", role: "status", children: props.blockedNotice }) : null] }), afterKey: `${props.interaction ? `${props.interaction.kind}:${props.interaction.id}` : ""}:${blocked ? "blocked" : ""}` })] }, props.attachmentScope) }), error ? _jsxs14("div", { className: "pc-workflow-chat__error", role: "alert", children: [_jsxs14("span", { children: ["Could not", " ", error.action === "send" ? "send this message" : error.action === "steer" ? activeSteerMode === "queue" ? "queue this message" : "steer the run" : error.action === "attach" ? "attach a file" : error.action === "toolbar" ? "complete that action" : "stop the run", ": ", error.message] }), error.action !== "toolbar" ? _jsx16("button", { type: "button", onClick: retry, disabled, children: "Try again" }) : null] }) : null, _jsxs14("div", { className: "pc-workflow-chat__composer", children: [_jsx16(ChatComposer, { value: props.draft, onChange: props.onDraftChange, onSubmit: () => void submit(), placeholder: props.placeholder || "Send a message", ariaLabel: "Message", disabled, busy: steering ? sendPending : composerBusy, sendLabel: steering ? steerLabel : props.sendLabel, busyLabel: steering ? activeSteerMode === "queue" ? "Queueing\u2026" : "Steering\u2026" : props.busyLabel, rows: 2, leading: props.attachments || attachmentItems.length ? _jsxs14("div", { className: "pc-workflow-chat__attachments", children: [attachmentItems.length ? _jsx16(ComposerAttachmentChips, { items: attachmentItems, onRemove: props.onRemoveAttachment, onRetry: props.onRetryAttachment, disabled }) : null, props.attachments] }) : null, overlay: dropZone, onPaste: acceptsFiles ? onPaste : void 0, actions: _jsxs14(_Fragment6, { children: [props.onAttach ? _jsxs14("button", { type: "button", className: "pc-workflow-chat__icon-button", "aria-label": "Attach file", "data-af-tip": "Attach a file", disabled: disabled || attachPending, onClick: () => void attach(), children: [_jsx16(Icon8, { name: "paperclip", size: 16 }), _jsx16("span", { children: attachPending ? "Attaching\u2026" : "Attach" })] }) : null, props.composerExtras, steering && steerModes.length > 1 ? _jsx16("span", { className: "pc-workflow-chat__steer-modes", role: "group", "aria-label": "While the run is busy", children: steerModes.map((mode) => _jsx16("button", { type: "button", className: "pc-workflow-chat__steer-mode", "data-steer-mode": mode, "aria-pressed": activeSteerMode === mode, disabled: disabled || sendPending, onClick: () => setSteerMode(mode), children: mode === "queue" ? "Queue next turn" : "Guide this run" }, mode)) }) : null, sending && props.onCancel ? _jsxs14("button", { type: "button", className: "pc-workflow-chat__stop", disabled: disabled || cancelPending || stopping, onClick: () => void cancel(), children: [_jsx16(Icon8, { name: "x", size: 14 }), _jsx16("span", { children: cancelPending || stopping ? "Stopping\u2026" : "Stop" })] }) : stopState ? _jsx16("span", { className: `pc-workflow-chat__stop-state pc-workflow-chat__stop-state--${stopState.phase}`, role: "status", "aria-live": "polite", children: stopState.label }) : null] }) }), steer ? _jsx16("div", { className: "pc-workflow-chat__steer-status", role: "status", "aria-live": "polite", children: steerNote }) : null, acceptsFiles ? _jsx16("div", { className: "pc-sr-only", role: "status", "aria-live": "polite", children: liveMessage }) : null] }), props.footer ? _jsx16("footer", { className: "pc-workflow-chat__footer", children: props.footer }) : null] });
}
export {
  ChatMessageCard,
  ChatThread,
  ToolActivity,
  ToolActivityGroup,
  WorkflowChat,
  outputArtifacts,
  submittedArtifacts
};
