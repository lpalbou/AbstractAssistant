// dist/workflow_chat.js
import { jsx as _jsx18, jsxs as _jsxs15, Fragment as _Fragment8 } from "react/jsx-runtime";

// dist/message_artifacts.js
import { Fragment as _Fragment3, jsx as _jsx6, jsxs as _jsxs4 } from "react/jsx-runtime";

// dist/artifact_preview.js
import { jsx as _jsx5 } from "react/jsx-runtime";
import { useEffect as useEffect4, useRef as useRef2, useState as useState4 } from "react";
import { AfModal, fileViewerKind as fileViewerKind2, fileViewerNeedsText as fileViewerNeedsText2 } from "@abstractframework/ui-kit";

// dist/file_viewer.js
import { jsx as _jsx3 } from "react/jsx-runtime";
import { useEffect as useEffect2, useState as useState2 } from "react";
import { AfFileViewer, fileViewerKind, fileViewerNeedsText, formatFileSize, gatewayApiPath } from "@abstractframework/ui-kit";

// dist/markdown.js
import { jsx as _jsx2, jsxs as _jsxs2 } from "react/jsx-runtime";
import React, { useEffect, useRef, useState } from "react";
import { codeLanguage, highlightCode, Icon } from "@abstractframework/ui-kit";

// dist/utils.js
function tryParseJson(text5) {
  const trimmed = String(text5 ?? "").trim();
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
async function copyText(text5) {
  const value = String(text5 || "");
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
  const text5 = String(opts.text || "");
  const mime = String(opts.mime || "text/plain;charset=utf-8");
  const blob = new Blob([text5], { type: mime });
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
function splitTextLinks(text5) {
  const out = [];
  const pattern = /(?:https?:\/\/|www\.)[^\s<>"'`\\]+/gi;
  let end = 0;
  for (const m of text5.matchAll(pattern)) {
    const start = m.index;
    if (start > 0 && /[\w@]/.test(text5[start - 1]))
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
      out.push({ text: text5.slice(end, start) });
    out.push({ text: label, href });
    end = start + label.length;
  }
  if (end < text5.length)
    out.push({ text: text5.slice(end) });
  return out;
}
function textLinks(text5) {
  return splitTextLinks(text5).map((p, i) => p.href ? _jsx("a", { className: "pc-md_link", href: p.href, target: "_blank", rel: "noopener noreferrer", children: p.text }, i) : p.text);
}
function TextLinks({ text: text5 }) {
  return _jsx(_Fragment, { children: textLinks(String(text5 ?? "")) });
}
function JsonTextLinks({ text: text5 }) {
  return _jsxs(_Fragment, { children: ['"', splitTextLinks(text5).map((p, i) => p.href ? _jsx("a", { className: "pc-md_link", href: p.href, target: "_blank", rel: "noopener noreferrer", children: p.text }, i) : JSON.stringify(p.text).slice(1, -1)), '"'] });
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
function highlightInline(text5, state, linkify = true) {
  const s = String(text5 ?? "");
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
function renderInline(text5, highlight) {
  const out = [];
  const s = String(text5 ?? "");
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
function normalizeLines(text5) {
  const s = String(text5 ?? "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
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
function renderMarkdown({ text: text5, className, highlight, highlights, highlightClassName, highlightId }) {
  const lines = normalizeLines(text5);
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
      const rows2 = [];
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
        rows2.push(normalized);
        i += 1;
      }
      blocks.push(_jsx2("div", { className: "pc-md_table_wrap", children: _jsxs2("table", { className: "pc-md_table", children: [_jsx2("thead", { children: _jsx2("tr", { children: headers.slice(0, colCount).map((h, idx) => _jsx2("th", { children: renderInline(h, highlightState) }, `th:${i}:${idx}`)) }) }), _jsx2("tbody", { children: rows2.map((r, rIdx) => _jsx2("tr", { children: r.map((cell, cIdx) => _jsx2("td", { children: renderInline(cell, highlightState) }, `td:${i}:${rIdx}:${cIdx}`)) }, `tr:${i}:${rIdx}`)) })] }) }, `table:${i}`));
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
var PREVIEW_LIMIT_LABEL = "1 MiB";
var PREVIEW_BLOB_LIMIT = 25 * 1024 * 1024;
function responseTotal(response) {
  const range = response.headers.get("content-range");
  const total = range ? Number(range.split("/")[1]) : NaN;
  if (Number.isFinite(total))
    return total;
  const length = Number(response.headers.get("content-length"));
  return response.status === 200 && Number.isFinite(length) && response.headers.has("content-length") ? length : void 0;
}
async function readBoundedText(response, limit, knownSize) {
  const decoder = new TextDecoder();
  let text5 = "";
  let received = 0;
  const reader = response.body?.getReader();
  if (reader) {
    while (received < limit) {
      const { done, value } = await reader.read();
      if (done)
        break;
      const chunk = value.subarray(0, limit - received);
      received += chunk.length;
      text5 += decoder.decode(chunk, { stream: true });
    }
    await reader.cancel().catch(() => {
    });
  } else {
    text5 = (await response.text()).slice(0, limit);
    received = text5.length;
  }
  const total = responseTotal(response) ?? knownSize;
  const partial = total !== void 0 ? total > received : received >= limit;
  return { text: text5, received, total, partial };
}
function partialPreviewNote(total) {
  return `Showing the first ${PREVIEW_LIMIT_LABEL} of ${total !== void 0 ? formatFileSize(total) : "a file of unknown size"}; download for the rest.`;
}
function FileViewer(props) {
  const { markdownImages, inlineImage, renderMarkdown: renderMarkdown2, ...rest } = props;
  return _jsx3(AfFileViewer, { ...rest, nowMs: props.nowMs ?? Date.now(), renderMarkdown: renderMarkdown2 || ((text5) => _jsx3(Markdown, { text: text5, ...markdownImages ? { images: markdownImages } : {}, ...inlineImage ? { inlineImage } : {} })) });
}

// dist/workspace_browser.js
import { jsx as _jsx4, jsxs as _jsxs3, Fragment as _Fragment2 } from "react/jsx-runtime";
import React2, { useCallback, useEffect as useEffect3, useState as useState3 } from "react";
import { Icon as Icon2, formatExactTime, formatRelativeTime, gatewayApiPath as gatewayApiPath2, gatewayResourcePath } from "@abstractframework/ui-kit";
async function gatewayResponseError(response, what) {
  let reason = "";
  try {
    const text5 = await response.text();
    try {
      const body = JSON.parse(text5);
      const detail = body?.detail ?? body?.error ?? body?.message;
      reason = typeof detail === "string" ? detail : detail && typeof detail.message === "string" ? detail.message : text5;
    } catch {
      reason = text5;
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

// dist/artifact_preview.js
async function boundedPreviewBlob(response, limit = PREVIEW_BLOB_LIMIT) {
  const total = responseTotal(response);
  if (total !== void 0 && total > limit) {
    await response.body?.cancel();
    throw Error("This file is too large to preview. Use Download.");
  }
  const reader = response.body?.getReader();
  if (!reader)
    return new Blob([], { type: response.headers.get("content-type") || "" });
  const chunks = [];
  let bytes = 0;
  try {
    for (; ; ) {
      const part = await reader.read();
      if (part.done)
        break;
      bytes += part.value.byteLength;
      if (bytes > limit)
        throw Error("This file is too large to preview. Use Download.");
      chunks.push(part.value);
    }
  } finally {
    await reader.cancel().catch(() => {
    });
  }
  return new Blob(chunks, {
    type: response.headers.get("content-type") || ""
  });
}
function artifactPreviewKind(name, type) {
  const mime = type.split(";", 1)[0].trim().toLowerCase();
  if (mime.includes("html") || mime.includes("xml") || mime === "image/svg+xml")
    return "text";
  const byMime = fileViewerKind2("", mime), byName = fileViewerKind2(name, "");
  if (byMime === "text")
    return ["code", "json", "markdown"].includes(byName) ? byName : "text";
  return byMime !== "binary" ? byMime : byName;
}
function ArtifactPreviewModal(p) {
  const [state, setState] = useState4({
    status: "loading",
    kind: "binary"
  }), [attempt, retry] = useState4(0), [mediaSize, setMediaSize] = useState4(null), [downloading, setDownloading] = useState4(false), [downloadError, setDownloadError] = useState4("");
  const previewAbort = useRef2(null), download = useRef2(null), alive = useRef2(true);
  useEffect4(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      download.current?.abort();
    };
  }, []);
  useEffect4(() => {
    const abort = new AbortController();
    previewAbort.current = abort;
    let objectUrl = "";
    setState({ status: "loading", kind: "binary" });
    void (async () => {
      try {
        const r = await p.fetchGateway(`${p.path}/content`, {
          signal: abort.signal,
          headers: { Range: `bytes=0-${PREVIEW_TEXT_LIMIT - 1}` }
        });
        if (!r.ok)
          throw await gatewayResponseError(r, "Attachment preview failed");
        const contentType = r.headers.get("content-type") || "", kind = artifactPreviewKind(p.name, contentType);
        if (fileViewerNeedsText2(kind)) {
          const read2 = await readBoundedText(r, PREVIEW_TEXT_LIMIT);
          if (abort.signal.aborted)
            return;
          setState({
            status: "ready",
            kind,
            contentType,
            text: read2.text,
            ...read2.partial ? { partialNote: partialPreviewNote(read2.total) } : {}
          });
        } else if (["image", "audio", "video", "pdf"].includes(kind)) {
          let media = r;
          const range = /^bytes 0-(\d+)\/(\d+)$/.exec(r.headers.get("content-range") || "");
          if (r.status === 206 && (!range || Number(range[1]) + 1 < Number(range[2]))) {
            await r.body?.cancel();
            media = await p.fetchGateway(`${p.path}/content`, {
              signal: abort.signal
            });
            if (!media.ok)
              throw await gatewayResponseError(media, "Attachment preview failed");
          }
          const actualType = media.headers.get("content-type") || contentType, actualKind = artifactPreviewKind(p.name, actualType);
          if (fileViewerNeedsText2(actualKind)) {
            const read2 = await readBoundedText(media, PREVIEW_TEXT_LIMIT);
            if (!abort.signal.aborted)
              setState({
                status: "ready",
                kind: actualKind,
                contentType: actualType,
                text: read2.text,
                ...read2.partial ? { partialNote: partialPreviewNote(read2.total) } : {}
              });
            return;
          }
          const blob = await boundedPreviewBlob(media);
          if (abort.signal.aborted)
            return;
          objectUrl = URL.createObjectURL(actualKind === "pdf" ? new Blob([blob], { type: "application/pdf" }) : blob);
          setState({
            status: "ready",
            kind: actualKind,
            contentType: actualType,
            url: objectUrl
          });
        } else {
          await r.body?.cancel();
          if (!abort.signal.aborted)
            setState({ status: "ready", kind: "binary", contentType });
        }
      } catch (e) {
        if (!abort.signal.aborted)
          setState({
            status: "error",
            kind: "binary",
            error: e instanceof Error ? e.message : String(e)
          });
      }
    })();
    return () => {
      abort.abort();
      if (objectUrl)
        URL.revokeObjectURL(objectUrl);
    };
  }, [p.fetchGateway, p.path, p.name, attempt]);
  const save = async () => {
    if (downloading)
      return;
    const abort = new AbortController();
    download.current = abort;
    setDownloading(true);
    setDownloadError("");
    try {
      const r = await p.fetchGateway(`${p.path}/content`, {
        signal: abort.signal
      });
      if (!r.ok)
        throw await gatewayResponseError(r, "Attachment download failed");
      const blob = await r.blob();
      if (!abort.signal.aborted && alive.current)
        deliverBlob(blob, p.name, "download");
    } catch (e) {
      if (!abort.signal.aborted && alive.current)
        setDownloadError(e instanceof Error ? e.message : String(e));
    } finally {
      if (!abort.signal.aborted && alive.current)
        setDownloading(false);
    }
  };
  return _jsx5(AfModal, { open: true, title: p.name, onClose: () => {
    alive.current = false;
    previewAbort.current?.abort();
    download.current?.abort();
    p.onClose();
  }, className: `pc-artifact-preview pc-artifact-preview--${state.kind}`, footerNote: downloading ? "Downloading\u2026" : downloadError || void 0, footer: state.status === "error" ? _jsx5("button", { type: "button", className: "pc-artifact-preview__retry", onClick: () => retry((n) => n + 1), children: "Retry preview" }) : void 0, children: _jsx5("div", { className: "pc-artifact-preview__content", style: mediaSize && mediaSize.url === state.url ? { "--pc-media-width": `${mediaSize.width}px`, "--pc-media-aspect": mediaSize.width / mediaSize.height } : void 0, onLoadCapture: (e) => {
    const image = e.target;
    if (image instanceof HTMLImageElement && image.naturalWidth && image.naturalHeight && image.src === state.url)
      setMediaSize({ url: image.src, width: image.naturalWidth, height: image.naturalHeight });
  }, onLoadedMetadataCapture: (e) => {
    const video = e.target;
    if (video instanceof HTMLVideoElement && video.videoWidth && video.videoHeight && video.src === state.url)
      setMediaSize({ url: video.src, width: video.videoWidth, height: video.videoHeight });
  }, children: _jsx5(FileViewer, { name: p.name, onDownload: () => void save(), status: state.status, kind: state.kind, contentType: state.contentType, text: state.text, url: state.url, error: state.error, partialNote: state.partialNote, markdownImages: "link", inlineImage: () => false }) }) });
}

// dist/message_artifacts.js
import { createContext, useContext, useEffect as useEffect6, useMemo as useMemo2, useRef as useRef4, useState as useState6 } from "react";
import { gatewayApiPath as gatewayApiPath3, Icon as Icon3 } from "@abstractframework/ui-kit";

// dist/attachment_uploads.js
import { useEffect as useEffect5, useMemo, useRef as useRef3, useState as useState5 } from "react";
import { randomId } from "@abstractframework/ui-kit";
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
var files = (count2) => `${count2} ${count2 === 1 ? "file" : "files"}`;
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

// dist/artifact_provenance.js
var INTERNAL_ARTIFACT_PARTS = /* @__PURE__ */ new Set([
  "scratchpad",
  "node_traces",
  "node_trace",
  "trace",
  "traces",
  "bookkeeping"
]);
function internalArtifactPart(part) {
  return part.startsWith("_") || INTERNAL_ARTIFACT_PARTS.has(part);
}
function displayArtifactPath(path) {
  const parts = String(path || "").split(/[.\[\]]/).filter(Boolean);
  if (parts.some(internalArtifactPart))
    return false;
  const slot = parts.findIndex((p) => [
    "attachments",
    "files",
    "artifacts",
    "media",
    "artifact",
    "artifact_ref",
    "image_artifact",
    "audio_artifact",
    "video_artifact",
    "music_artifact"
  ].includes(p));
  if (slot < 0)
    return false;
  return !parts.slice(0, slot).some((p) => [
    "session",
    "sessions",
    "history",
    "conversation",
    "transcript",
    "messages",
    "context"
  ].includes(p));
}
function replayMessageArtifacts(message, entries) {
  const byId = entries;
  let unresolved = false;
  const refs = [];
  for (const id of message.artifact_ids || []) {
    const entry = byId.get(id);
    if (!entry) {
      unresolved = true;
      continue;
    }
    if (!displayArtifactPath(String(entry.path || "")))
      continue;
    refs.push({
      id,
      runId: typeof entry.run_id === "string" && entry.run_id ? entry.run_id : message.run_id
    });
  }
  return { refs, unresolved };
}
function internalArtifactMetadata(meta) {
  const tags = meta.tags && typeof meta.tags === "object" ? meta.tags : {};
  const envelope = meta.artifact_envelope_v1 && typeof meta.artifact_envelope_v1 === "object" ? meta.artifact_envelope_v1 : {};
  return [
    "node_trace_offload",
    "run_output_offload",
    "run_input_offload",
    "conversation_offload",
    "session_offload",
    "state_offload"
  ].includes(String(tags.source || meta.source || "")) || ["internal", "bookkeeping"].includes(String(tags.role || envelope.role || meta.role || ""));
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
    Object.entries(r).forEach(([key, x]) => {
      if (internalArtifactPart(key))
        return;
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
  const root = obj(output), result = obj(root.result);
  const fields = [
    "attachments",
    "artifacts",
    "files",
    "media",
    "artifact",
    "artifact_ref",
    "image_artifact",
    "audio_artifact",
    "video_artifact",
    "music_artifact"
  ];
  return messageArtifactRefs([root, obj(root.meta), result, obj(result.meta)].flatMap((container) => fields.map((key) => container[key])), runId);
}
function useMessageArtifacts(messages, fetchGateway, scope2, run) {
  const [attempt, setAttempt] = useState6(0);
  const cache = useRef4({ owner: scope2, refs: /* @__PURE__ */ new Map(), outputs: /* @__PURE__ */ new Map() });
  if (cache.current.owner !== scope2)
    cache.current = { owner: scope2, refs: /* @__PURE__ */ new Map(), outputs: /* @__PURE__ */ new Map() };
  const signature = JSON.stringify([
    ...new Set(messages.filter((m) => m.role === "user" && m.runId).map((m) => m.runId))
  ]);
  const [inputs, setInputs] = useState6({ owner: scope2, refs: {}, error: "" });
  useEffect6(() => {
    const abort = new AbortController(), ids = JSON.parse(signature).filter((id) => !cache.current.refs.has(id));
    const currentIds = new Set(JSON.parse(signature));
    for (const key of cache.current.refs.keys())
      if (!currentIds.has(key))
        cache.current.refs.delete(key);
    for (const key of cache.current.outputs.keys())
      if (!currentIds.has(key))
        cache.current.outputs.delete(key);
    setInputs({
      owner: scope2,
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
        if (!abort.signal.aborted && cache.current.owner === scope2) {
          cache.current.refs.set(id, refs);
          setInputs((old) => ({ ...old, refs: { ...old.refs, [id]: refs } }));
        }
      } catch (e) {
        if (!abort.signal.aborted && cache.current.owner === scope2)
          setInputs((old) => ({
            ...old,
            error: e instanceof Error ? e.message : String(e)
          }));
      }
    });
    return () => abort.abort();
  }, [fetchGateway, scope2, signature, attempt]);
  const missing = JSON.stringify(JSON.parse(signature).filter((id) => !messages.some((m) => m.runId === id && m.role === "assistant") || messages.some((m) => m.runId === id && m.artifactReferencesUnresolved)));
  const [restored, setRestored] = useState6({ owner: scope2, files: {}, error: "" });
  useEffect6(() => {
    const abort = new AbortController();
    setRestored((old) => old.owner === scope2 ? { ...old, error: "" } : { owner: scope2, files: {}, error: "" });
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
          if (!abort.signal.aborted && cache.current.owner === scope2) {
            if (["completed", "failed", "cancelled"].includes(String(body.status)))
              cache.current.outputs.set(id, files2);
            setRestored((old) => old.owner === scope2 ? { ...old, files: { ...old.files, [id]: files2 } } : old);
          }
        } catch (e) {
          if (!abort.signal.aborted)
            setRestored((old) => old.owner === scope2 ? {
              ...old,
              error: e instanceof Error ? e.message : String(e)
            } : old);
        }
      });
    return () => abort.abort();
  }, [fetchGateway, scope2, missing, run?.runId, run?.output, attempt]);
  const shown = useMemo2(() => {
    const inputShown = /* @__PURE__ */ new Set();
    const list = messages.map((m) => {
      const originalPrompt = m.role === "user" && Boolean(m.runId) && !inputShown.has(m.runId);
      if (originalPrompt)
        inputShown.add(m.runId);
      const submitted = originalPrompt && inputs.owner === scope2 ? inputs.refs[m.runId || ""] || [] : [];
      const refs = [...m.artifactRefs || [], ...submitted];
      const unique = [
        ...new Map(refs.filter((r) => r.id && r.runId).map((r) => [r.id, r])).values()
      ];
      return unique.length ? { ...m, artifactRefs: unique } : m;
    });
    const visibleRuns = new Set(messages.map((message) => message.runId));
    const outcomes = [
      ...restored.owner === scope2 ? Object.entries(restored.files).filter(([id]) => visibleRuns.has(id)) : [],
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
              ...new Map([...refs, ...list[i].artifactRefs || []].map((r) => [
                r.id,
                r
              ])).values()
            ]
          };
      }
    }
    return list;
  }, [messages, inputs, restored, scope2, run?.runId, run?.output]);
  return {
    messages: shown,
    error: [
      inputs.owner === scope2 ? inputs.error : "",
      restored.owner === scope2 ? restored.error : ""
    ].filter(Boolean).join(" "),
    retry: () => setAttempt((n) => n + 1)
  };
}
var ArtifactFetchContext = createContext(void 0);
function MessageArtifactChip({ artifact }) {
  const fetchGateway = useContext(ArtifactFetchContext), [name, setName] = useState6(artifact.name || "Attached file"), [error, setError] = useState6(""), [previewOpen, setPreviewOpen] = useState6(false), [internal, setInternal] = useState6(false), [metadataStatus, setMetadataStatus] = useState6("loading"), [metadataAttempt, retryMetadata] = useState6(0);
  const path = gatewayApiPath3(`runs/${encodeURIComponent(artifact.runId)}/artifacts/${encodeURIComponent(artifact.id)}`);
  useEffect6(() => {
    const abort = new AbortController();
    setName(artifact.name || "Attached file");
    setError("");
    setInternal(false);
    setMetadataStatus("loading");
    if (fetchGateway)
      void fetchGateway(path, { signal: abort.signal }).then(async (r) => {
        if (!r.ok)
          throw await gatewayResponseError(r, "Attachment unavailable");
        const meta = await r.json(), tags = obj(meta.tags), descriptor = obj(meta.descriptor), envelope = obj(meta.artifact_envelope_v1);
        const hidden = internalArtifactMetadata(meta);
        if (!abort.signal.aborted) {
          setInternal(hidden);
          setMetadataStatus("ready");
        }
        const value = meta.filename || meta.name || tags.filename || descriptor.name || envelope.name;
        if (!abort.signal.aborted && typeof value === "string")
          setName(value);
      }).catch((e) => {
        if (!abort.signal.aborted) {
          setMetadataStatus("error");
          setError(e instanceof Error ? e.message : String(e));
        }
      });
    return () => {
      abort.abort();
    };
  }, [fetchGateway, path, metadataAttempt]);
  useEffect6(() => {
    if (artifact.name)
      setName(artifact.name);
  }, [artifact.name]);
  if (internal)
    return _jsx6(_Fragment3, {});
  return _jsxs4("span", { className: "pc-message-artifact", children: [_jsxs4("button", { type: "button", className: "pc-chat-attachment-chip", "aria-haspopup": "dialog", disabled: !fetchGateway || metadataStatus !== "ready", onClick: () => setPreviewOpen(true), children: [_jsx6(Icon3, { name: "paperclip", size: 14 }), _jsx6("span", { className: "pc-chat-attachment-name", children: name })] }), error && _jsxs4("span", { role: "status", className: "pc-message-artifact__error", children: [error, " ", _jsxs4("button", { type: "button", onClick: () => retryMetadata((n) => n + 1), children: ["Retry ", name] })] }), previewOpen && fetchGateway && _jsx6(ArtifactPreviewModal, { name, path, fetchGateway, onClose: () => setPreviewOpen(false) })] });
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
import { useEffect as useEffect15, useMemo as useMemo8, useRef as useRef11, useState as useState15 } from "react";
import { Icon as Icon9, useAfTooltips } from "@abstractframework/ui-kit";

// dist/chat_composer.js
import { jsx as _jsx7, jsxs as _jsxs5 } from "react/jsx-runtime";
import React3, { useCallback as useCallback2, useEffect as useEffect7, useRef as useRef5 } from "react";
import { Icon as Icon4 } from "@abstractframework/ui-kit";
var ChatComposer = React3.forwardRef(function ChatComposer2(props, ref) {
  const compact = props.variant !== "legacy";
  const rows2 = typeof props.rows === "number" && Number.isFinite(props.rows) ? Math.max(1, Math.trunc(props.rows)) : compact ? 2 : 3;
  const disabled = Boolean(props.disabled);
  const busy = Boolean(props.busy);
  const can_submit = !disabled && !busy && (props.canSubmit ?? Boolean(String(props.value || "").trim()));
  const sendLabel = busy ? props.busyLabel || "Thinking\u2026" : props.sendLabel || "Send";
  const textarea = useRef5(null);
  const fallbackSizing = useRef5(false);
  const setTextarea = useCallback2((element) => {
    textarea.current = element;
    if (typeof ref === "function")
      ref(element);
    else if (ref)
      ref.current = element;
  }, [ref]);
  const resizeTextarea = useCallback2(() => {
    const element = textarea.current;
    if (!element || !fallbackSizing.current)
      return;
    element.style.height = "0px";
    const cap = parseFloat(getComputedStyle(element).maxHeight);
    element.style.height = `${Math.min(element.scrollHeight, Number.isFinite(cap) ? cap : Infinity)}px`;
  }, []);
  useEffect7(() => {
    const element = textarea.current;
    if (!compact || !element || typeof CSS !== "undefined" && CSS.supports?.("field-sizing", "content"))
      return;
    fallbackSizing.current = true;
    resizeTextarea();
    window.addEventListener("resize", resizeTextarea);
    let width = element.clientWidth;
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => {
      if (element.clientWidth !== width) {
        width = element.clientWidth;
        resizeTextarea();
      }
    });
    observer?.observe(element);
    return () => {
      fallbackSizing.current = false;
      observer?.disconnect();
      window.removeEventListener("resize", resizeTextarea);
      element.style.removeProperty("height");
    };
  }, [compact, resizeTextarea]);
  useEffect7(() => {
    resizeTextarea();
  }, [props.value, rows2, resizeTextarea]);
  return _jsxs5("div", { className: ["pc-composer", compact ? "pc-composer--compact" : "", props.className].filter(Boolean).join(" "), children: [props.leading, _jsx7("textarea", {
    id: props.textareaId,
    ref: setTextarea,
    className: ["pc-composer__textarea", props.textareaClassName].filter(Boolean).join(" "),
    value: props.value,
    onChange: (e) => props.onChange(e.target.value),
    rows: rows2,
    // The textarea auto-grows (CSS field-sizing) from `rows` lines up to a
    // viewport-relative cap; the row count reaches the CSS as a variable.
    style: { ["--pc-composer-rows"]: String(rows2) },
    spellCheck: false,
    autoCorrect: "off",
    autoCapitalize: "off",
    autoComplete: "off",
    placeholder: props.placeholder || "",
    "aria-label": props.ariaLabel || props.placeholder || "Message",
    "aria-describedby": props.ariaDescribedBy,
    disabled,
    autoFocus: Boolean(props.autoFocus),
    onPaste: props.onPaste,
    onKeyDown: (e) => {
      if (e.key !== "Enter" || e.shiftKey)
        return;
      if (props.submitKey === "mod-enter" && !e.ctrlKey && !e.metaKey)
        return;
      if (e.nativeEvent.isComposing || e.keyCode === 229)
        return;
      e.preventDefault();
      if (!can_submit)
        return;
      props.onSubmit();
    }
  }), _jsxs5("div", { className: "pc-composer__row", children: [_jsxs5("div", { className: "pc-composer__actions", children: [props.onAttach ? _jsxs5("button", { type: "button", className: compact ? "pc-composer__icon-action" : "pc-composer__icon-action pc-workflow-chat__icon-button", "aria-label": props.attachLabel || "Attach files", "data-af-tip": props.attachLabel || "Attach files", "aria-busy": props.attachPending || void 0, disabled: disabled || props.attachDisabled || props.attachPending, onClick: props.onAttach, children: [_jsx7(Icon4, { name: props.attachPending ? "loader" : compact ? "plus" : "paperclip", size: 16 }), _jsx7("span", { className: compact ? "pc-sr-only" : void 0, children: props.attachPending ? "Attaching\u2026" : props.attachLabel || "Attach" })] }) : null, props.actions] }), props.trailingActions ? _jsx7("div", { className: "pc-composer__trailing", children: props.trailingActions }) : null, _jsx7("button", { type: "button", className: [props.sendButtonClassName || "pc-btn", compact ? "pc-composer__send--compact" : ""].filter(Boolean).join(" "), "aria-label": compact ? sendLabel : void 0, "data-af-tip": compact ? sendLabel : void 0, "aria-busy": compact ? busy : void 0, disabled: !can_submit, onClick: () => props.onSubmit(), children: compact ? _jsx7(Icon4, { name: busy ? "loader" : "send", size: 17 }) : sendLabel })] }), props.overlay] });
});

// dist/chat_thread.js
import { jsx as _jsx14, jsxs as _jsxs11 } from "react/jsx-runtime";
import { useEffect as useEffect12, useMemo as useMemo6, useRef as useRef8, useState as useState12 } from "react";

// dist/chat_message_card.js
import { jsx as _jsx13, jsxs as _jsxs10 } from "react/jsx-runtime";
import { useEffect as useEffect11, useMemo as useMemo5, useRef as useRef7, useState as useState11 } from "react";
import { AfAudioPlayer, Icon as Icon6, fileViewerKind as fileViewerKind4, fileViewerNeedsText as fileViewerNeedsText3, formatFileSize as formatFileSize2 } from "@abstractframework/ui-kit";

// dist/chat_media.js
import { fileViewerKind as fileViewerKind3 } from "@abstractframework/ui-kit";
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
import { jsx as _jsx9 } from "react/jsx-runtime";
import { useMemo as useMemo4 } from "react";

// dist/json_viewer.js
import { jsx as _jsx8, jsxs as _jsxs6, Fragment as _Fragment4 } from "react/jsx-runtime";
import { useEffect as useEffect8, useMemo as useMemo3, useState as useState7 } from "react";
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
  return _jsx8("span", { className: `pc-json-token ${kind}`, children });
}
function JsonStringValue(props) {
  const rendered = JSON.stringify(props.value);
  const isUrl = /^https?:\/\/[^\s]+$/i.test(props.value);
  const collapsible = !isUrl && (rendered.length > 96 || rendered.includes("\\n") || rendered.includes("\\r") || rendered.includes("\\t"));
  const [open, setOpen] = useState7(!collapsible || props.expansionMode === "unfolded");
  useEffect8(() => {
    if (!collapsible)
      return;
    setOpen(props.expansionMode === "unfolded");
  }, [collapsible, props.expansionMode, props.expansionVersion]);
  if (!collapsible)
    return _jsx8("span", { className: "pc-json-token string", children: _jsx8(JsonTextLinks, { text: props.value }) });
  return _jsxs6("span", { className: `pc-json-string ${open ? "open" : "collapsed"}`, children: [_jsx8("button", { type: "button", className: "pc-json-string__toggle", onClick: () => setOpen((v) => !v), "aria-label": open ? "Collapse string value" : "Expand string value", "aria-expanded": open, children: open ? "\u25BE" : "\u25B8" }), open ? _jsx8("span", { className: "pc-json-token string pc-json-string__value", children: _jsx8(JsonTextLinks, { text: props.value }) }) : _jsxs6("span", { className: "pc-json-string__preview", children: [_jsx8("span", { className: "pc-json-token string pc-json-string__preview_text", children: _jsx8(JsonTextLinks, { text: props.value }) }), _jsx8("button", { type: "button", className: "pc-json-string__suffix", onClick: () => setOpen(true), "aria-label": "Expand string value", children: "(...)" })] })] });
}
function renderPrimitive(value, expansionMode, expansionVersion) {
  if (value === null)
    return _jsx8(Token, { kind: "null", children: "null" });
  if (typeof value === "string")
    return _jsx8(JsonStringValue, { value, expansionMode, expansionVersion });
  if (typeof value === "number")
    return _jsx8(Token, { kind: "number", children: String(value) });
  if (typeof value === "boolean")
    return _jsx8(Token, { kind: "boolean", children: value ? "true" : "false" });
  return _jsx8(Token, { kind: "string", children: JSON.stringify(String(value)) });
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
  const [open, setOpen] = useState7(defaultOpen);
  useEffect8(() => {
    setOpen(defaultOpen);
  }, [defaultOpen, expansionVersion]);
  const prefix = label ? _jsxs6(_Fragment4, { children: [_jsx8(Token, { kind: "key", children: JSON.stringify(label) }), ": "] }) : null;
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
  return _jsxs6("details", { className: "pc-json-viewer__details", open, onToggle: (e) => setOpen(e.currentTarget.open), children: [_jsxs6("summary", { className: "pc-json-viewer__summary", style: { paddingLeft: indentPx }, children: [prefix, _jsx8("span", { className: "pc-json-viewer__caret", "aria-hidden": "true", children: open ? "\u25BE" : "\u25B8" }), _jsx8("span", { className: "pc-json-viewer__punct", children: summaryValue }), !open && trailingComma ? _jsx8("span", { className: "pc-json-viewer__punct", children: "," }) : null] }), open ? _jsx8("div", { className: "pc-json-viewer__children", children: entries.length === 0 ? _jsxs6("div", { className: "pc-json-viewer__line", style: { paddingLeft: indentPx }, children: [_jsx8("span", { className: "pc-json-viewer__punct", children: containerClose }), trailingComma ? "," : ""] }) : _jsxs6(_Fragment4, { children: [entries.map((e, idx) => {
    const isLast = idx === entries.length - 1;
    return _jsx8(JsonNode, { label: e.label, value: e.value, depth: depth + 1, collapseAfterDepth, expansionMode, expansionVersion, trailingComma: !isLast }, `${depth}:${label || "root"}:${e.key}`);
  }), _jsxs6("div", { className: "pc-json-viewer__line", style: { paddingLeft: indentPx }, children: [_jsx8("span", { className: "pc-json-viewer__punct", children: containerClose }), trailingComma ? "," : ""] })] }) }) : null] });
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
  const [expansion, setExpansion] = useState7({ mode: "folded", version: 0 });
  const [copyState, setCopyState] = useState7("idle");
  const foldedDepth = typeof props.collapseAfterDepth === "number" && (Number.isFinite(props.collapseAfterDepth) || props.collapseAfterDepth === Infinity) && props.collapseAfterDepth >= 0 ? props.collapseAfterDepth === Infinity ? Number.MAX_SAFE_INTEGER : Math.trunc(props.collapseAfterDepth) : FOLDED_DEPTH;
  const collapseAfterDepth = expansion.mode === "unfolded" ? UNFOLDED_DEPTH : foldedDepth;
  const displayValue2 = useMemo3(() => typeof value === "string" ? tryParseJsonString(value) : value, [value]);
  const copyValue = useMemo3(() => copyStringForJson(value), [value]);
  const cls = ["pc-json-viewer", className].filter(Boolean).join(" ");
  useEffect8(() => {
    setExpansion((prev) => ({ mode: "folded", version: prev.version + 1 }));
  }, [displayValue2]);
  const toggleExpansion = () => {
    setExpansion((prev) => ({
      mode: prev.mode === "unfolded" ? "folded" : "unfolded",
      version: prev.version + 1
    }));
  };
  return _jsxs6("div", { className: cls, children: [_jsxs6("div", { className: "pc-json-viewer__toolbar", children: [_jsx8("button", { type: "button", className: "pc-btn pc-json-viewer__toggle-all", onClick: toggleExpansion, "aria-expanded": expansion.mode === "unfolded", children: expansion.mode === "unfolded" ? "Fold all" : "Unfold all" }), showCopy ? _jsx8("button", { type: "button", className: "pc-btn pc-json-viewer__copy", onClick: () => void copyText(copyValue).then((ok) => {
    setCopyState(ok ? "copied" : "failed");
    window.setTimeout(() => setCopyState("idle"), 2e3);
  }), children: copyState === "copied" ? "Copied" : copyState === "failed" ? "Copy failed \u2014 select and copy" : "Copy JSON" }) : null] }), _jsx8("div", { className: "pc-json-viewer__tree", role: "tree", "aria-label": "JSON viewer", children: _jsx8(JsonNode, { value: displayValue2, depth: 0, collapseAfterDepth, expansionMode: expansion.mode, expansionVersion: expansion.version, trailingComma: false }) })] });
}

// dist/message_content.js
function ChatMessageContent(props) {
  const text5 = String(props.text ?? "");
  const parsed = useMemo4(() => tryParseJson(text5), [text5]);
  const cls = ["pc-chat-content", props.className].filter(Boolean).join(" ");
  if (parsed !== null) {
    return _jsx9("div", { className: cls, children: _jsx9(JsonViewer, { value: parsed, collapseAfterDepth: props.jsonCollapseAfterDepth }) });
  }
  if (props.renderMarkdown) {
    return _jsx9("div", { className: cls, children: props.renderMarkdown(text5) });
  }
  return _jsx9("div", { className: cls, children: _jsx9(Markdown, { text: text5, images: props.images, inlineImage: props.inlineImage }) });
}

// dist/tool_activity.js
import { jsx as _jsx12, Fragment as _Fragment6, jsxs as _jsxs9 } from "react/jsx-runtime";
import React5, { useState as useState9 } from "react";
import { Icon as Icon5 } from "@abstractframework/ui-kit";

// dist/sandbox_line.js
import { jsx as _jsx10, jsxs as _jsxs7 } from "react/jsx-runtime";
function obj2(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : null;
}
function text(value) {
  return typeof value === "string" ? value.trim() : "";
}
function sandboxEvidence(value) {
  const v = obj2(value);
  if (!v)
    return null;
  const direct = obj2(v.sandbox);
  if (direct && text(direct.kind))
    return direct;
  const nested = obj2(obj2(v.output)?.sandbox);
  return nested && text(nested.kind) ? nested : null;
}
function toolSandbox(value) {
  const sb = sandboxEvidence(value);
  if (!sb)
    return null;
  const kind = text(sb.kind);
  const label = text(sb.label) || kind;
  const builtinRefused = Number.isFinite(Number(sb.builtin_refused)) ? Math.max(0, Math.trunc(Number(sb.builtin_refused))) : 0;
  if (kind === "none") {
    return { state: "refused", kind, label, line: `Sandbox: ${label} \u2014 refused`, rows: [], builtinRefused: 0 };
  }
  const rows2 = [];
  const priv = text(sb.private_workspace);
  if (priv)
    rows2.push({ path: priv, mode: "Read & write", private: true });
  for (const item of Array.isArray(sb.allowed) ? sb.allowed : []) {
    const row2 = obj2(item);
    const path = text(row2?.path);
    if (path)
      rows2.push({ path, mode: text(row2?.mode) === "ro" ? "Read-only" : "Read & write" });
  }
  for (const item of Array.isArray(sb.refused) ? sb.refused : []) {
    const path = text(item);
    if (path)
      rows2.push({ path, mode: "Refused" });
  }
  if (kind === "unsandboxed") {
    return { state: "unsandboxed", kind, label, line: `Sandbox: ${label}`, rows: [], builtinRefused: 0 };
  }
  const n = rows2.length;
  return {
    state: "sandboxed",
    kind,
    label,
    line: `Sandbox: ${label} \xB7 ${n} ${n === 1 ? "workspace" : "workspaces"} enforced`,
    rows: rows2,
    builtinRefused
  };
}
function ToolSandboxLine({ sandbox, className }) {
  if (!sandbox)
    return null;
  return _jsxs7("div", { className: `pc-tool-sandbox is-${sandbox.state}${className ? ` ${className}` : ""}`, "data-sandbox-kind": sandbox.kind, children: [_jsx10("div", { className: "pc-tool-sandbox__line", children: sandbox.line }), sandbox.rows.length ? _jsxs7("ul", { className: "pc-tool-sandbox__rows", "aria-label": "Workspaces the sandbox enforced", children: [sandbox.rows.map((row2, i) => _jsxs7("li", { children: [_jsx10("code", { children: row2.path }), _jsx10("span", { className: "pc-tool-sandbox__mode", children: row2.private ? `${row2.mode} \xB7 this run's folder` : row2.mode })] }, `${row2.mode}:${row2.path}:${i}`)), sandbox.builtinRefused ? _jsxs7("li", { className: "pc-tool-sandbox__builtin", children: [sandbox.builtinRefused, " built-in protected ", sandbox.builtinRefused === 1 ? "folder" : "folders", " refused"] }) : null] }) : null] });
}

// dist/tool_policy.js
import { formatExactTime as formatExactTime2 } from "@abstractframework/ui-kit";
var obj3 = (value) => value && typeof value === "object" && !Array.isArray(value) ? value : null;
var str = (value) => typeof value === "string" ? value.trim() : typeof value === "number" ? String(value) : "";
function toolPolicyDecision(payload) {
  const decision = str(payload?.decision);
  if (decision !== "auto_approved" && decision !== "denied")
    return null;
  const policy = obj3(payload?.policy);
  const setBy = obj3(policy?.set_by);
  const who = str(setBy?.user_id) || str(setBy?.client);
  const revision = typeof policy?.revision === "number" ? policy.revision : void 0;
  const provenance = {
    decision,
    ...str(payload?.source) ? { source: str(payload?.source) } : {},
    ...revision !== void 0 ? { revision } : {},
    ...who ? { setBy: who } : {},
    ...str(policy?.set_at) ? { setAt: str(policy?.set_at) } : {}
  };
  const calls = (Array.isArray(payload?.tool_calls) ? payload.tool_calls : []).map((row2) => obj3(row2)).filter((row2) => Boolean(row2 && str(row2.call_id))).map((row2) => ({ callId: str(row2.call_id), name: str(row2.name), ...str(row2.matched) ? { matched: str(row2.matched) } : {} }));
  if (!calls.length)
    return null;
  return { provenance, calls };
}
function toolPolicyDecisionText(provenance) {
  if (provenance.decision === "denied")
    return "Denied by this chat's policy";
  const at = provenance.setAt ? formatExactTime2(provenance.setAt) : "";
  const by = provenance.setBy ? `set by ${provenance.setBy}` : "";
  const detail = [by, at ? `at ${at}` : ""].filter(Boolean).join(" ");
  return `Allowed by this chat's policy${detail ? ` (${detail})` : ""}`;
}
function sessionPolicyClampedText(clamped) {
  const groups = /* @__PURE__ */ new Map();
  for (const row2 of clamped || []) {
    const name = str(row2?.name);
    if (!name)
      continue;
    const reason = str(row2?.reason).replace(/_/g, " ") || "not stored";
    groups.set(reason, [...groups.get(reason) || [], name]);
  }
  if (!groups.size)
    return "";
  return `Not covered: ${[...groups].map(([reason, names]) => `${names.join(", ")} (${reason})`).join("; ")}`;
}

// dist/stat_detail.js
import { jsx as _jsx11, jsxs as _jsxs8, Fragment as _Fragment5 } from "react/jsx-runtime";
import React4, { useCallback as useCallback3, useEffect as useEffect9, useId, useLayoutEffect, useRef as useRef6, useState as useState8 } from "react";
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
    const rows2 = [
      { label: "Reused from cache", value: `${n0(cached)}${cached + fed ? ` (${pct(cached, cached + fed)})` : ""}` },
      { label: "Newly processed", value: n0(s.fedTokens) },
      { label: "Outcome", value: tally(calls.map((c) => c.cacheOutcome)) || (s.cacheOutcomes || []).join(" \xB7 ") || NR },
      { label: "Backend", value: (s.cacheBackends || []).join(", ") || NR }
    ];
    if (s.measuredCacheCalls !== s.llmCalls)
      rows2.push({ label: "Measured on", value: `${s.measuredCacheCalls} of ${s.llmCalls} calls` });
    sections.push({ heading: "Prompt cache", rows: rows2 });
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
    const rows2 = [
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
      rows2.push({
        label: "Draft length",
        value: `${spec.draftLengths?.length ? `${spec.draftLengths.join("/")} tok/round` : NR}${spec.rounds !== void 0 ? ` \xB7 ${spec.rounds.toLocaleString()} rounds` : ""}`
      });
    sections.push({ heading: "Speculation", rows: rows2 });
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
        rows: breakdown.map(([name, row2]) => [
          name,
          row2.calls.toLocaleString(),
          row2.failed.toLocaleString(),
          row2.ms !== void 0 ? `${formatDuration(row2.ms)}${row2.sharedBatches ? " +shared" : ""}` : row2.sharedBatches ? "shared" : NR
        ])
      },
      note: breakdown.some(([, row2]) => row2.sharedBatches) ? "A batch that mixed tools ran them together; its time is not split between them." : void 0
    });
  const failures = breakdown.filter(([, row2]) => row2.errors && Object.keys(row2.errors).length);
  if (failures.length)
    sections.push({
      heading: "Failures",
      rows: failures.map(([name, row2]) => ({
        label: name,
        value: Object.entries(row2.errors).sort((a, b) => b[1] - a[1]).map(([cls, n]) => n > 1 ? `${cls} \xD7${n}` : cls).join(" \xB7 ")
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
  const rows2 = files2.slice(0, FILES_SHOWN).map((path) => {
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
        rows: rows2,
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
  return _jsxs8("div", { ref: props.panelRef, id: props.id, role: "tooltip", className: `pc-stat-detail pc-stat-detail--${d.kind}`, style: props.style, onMouseEnter: props.onMouseEnter, onMouseLeave: props.onMouseLeave, children: [_jsxs8("div", { className: "pc-stat-detail-head", children: [_jsx11("span", { className: "pc-stat-detail-title", children: d.title }), _jsx11("span", { className: "pc-stat-detail-headline", children: d.headline })] }), d.sections.map((section) => _jsxs8("div", { className: "pc-stat-detail-section", children: [_jsx11("div", { className: "pc-stat-detail-heading", children: section.heading }), section.rows?.length ? _jsx11("dl", { className: "pc-stat-detail-rows", children: section.rows.map((row2, i) => _jsxs8(React4.Fragment, { children: [_jsx11("dt", { children: row2.label }), _jsxs8("dd", { children: [_jsx11("span", { className: row2.value === NR ? "pc-stat-detail-value pc-stat-detail-value--absent" : "pc-stat-detail-value", children: row2.value }), row2.hint ? _jsx11("span", { className: "pc-stat-detail-hint", children: row2.hint }) : null] })] }, `${row2.label}:${i}`)) }) : null, section.table ? _jsxs8("table", { className: "pc-stat-detail-table", children: [_jsx11("thead", { children: _jsx11("tr", { children: section.table.columns.map((c) => _jsx11("th", { scope: "col", children: c }, c)) }) }), _jsx11("tbody", { children: section.table.rows.map((r, i) => _jsx11("tr", { children: r.map((cell, j) => _jsx11("td", { children: cell }, j)) }, i)) })] }) : null, section.note ? _jsx11("p", { className: "pc-stat-detail-note", children: section.note }) : null] }, section.heading)), _jsx11("div", { className: "pc-stat-detail-foot", children: d.footer.map((line) => _jsx11("div", { children: line }, line)) })] });
}
var GAP = 8;
function StatChip(props) {
  const [open, setOpen] = useState8(Boolean(props.defaultOpen));
  const [pos, setPos] = useState8(null);
  const chipRef = useRef6(null);
  const panelRef = useRef6(null);
  const closeTimer = useRef6(null);
  const id = `pc-stat-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const cancelClose = useCallback3(() => {
    if (closeTimer.current !== null)
      window.clearTimeout(closeTimer.current);
    closeTimer.current = null;
  }, []);
  const show = useCallback3(() => {
    cancelClose();
    setOpen(true);
  }, [cancelClose]);
  const hideSoon = useCallback3(() => {
    cancelClose();
    closeTimer.current = window.setTimeout(() => setOpen(false), 120);
  }, [cancelClose]);
  useEffect9(() => cancelClose, [cancelClose]);
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
  useEffect9(() => {
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
  const panel = open ? _jsx11(StatDetailPanel, { detail: props.detail, id, panelRef, onMouseEnter: cancelClose, onMouseLeave: hideSoon, style: { position: "fixed", top: pos?.top ?? 0, left: pos?.left ?? 0, visibility: pos ? "visible" : "hidden" } }) : null;
  return _jsxs8(_Fragment5, { children: [_jsxs8(Element, { ref: chipRef, ...clickable ? { type: "button" } : { tabIndex: 0 }, className: ["pc-chat-stat", "pc-chat-stat--detail", clickable ? "pc-chat-stat--clickable" : "", props.className].filter(Boolean).join(" "), "aria-label": `${props.label} \u2014 ${props.detail.title.toLowerCase()} details`, "aria-describedby": open ? id : void 0, "data-stat-kind": props.detail.kind, onMouseEnter: show, onMouseLeave: hideSoon, onFocus: show, onBlur: () => setOpen(false), onKeyDown: (e) => {
    if (e.key === "Escape")
      setOpen(false);
  }, onClick: clickable ? () => props.onClick?.() : void 0, children: [props.icon ? _jsx11("span", { className: "pc-chat-stat-icon", "aria-hidden": "true", children: props.icon }) : null, _jsx11("span", { className: "pc-chat-stat-label", children: props.label })] }), panel && typeof document !== "undefined" ? createPortal(panel, document.body) : panel] });
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
  const [copied, setCopied] = useState9(false);
  const args = toolArguments(tool.arguments);
  const preview = toolPreview(tool.arguments);
  const output = toolArguments(tool.output);
  const previewText = ["file path", "path"].includes(preview.label) && preview.value.length > 60 ? `${preview.value.split(/[\\/]/).pop()} \xB7 ${preview.value.slice(0, 24)}\u2026` : preview.value;
  const errorPreview = tool.error && /^File ['"].+['"] does not exist\.?$/.test(tool.error) ? "File not found. Expand for the exact path." : tool.error && tool.error.length > 180 ? `${tool.error.slice(0, 100)}\u2026${tool.error.slice(-70)}` : tool.error;
  const labels2 = {
    running: "Running",
    waiting: "Approval needed",
    completed: "Done",
    failed: "Failed"
  };
  const duration = tool.startedAt && tool.endedAt ? Date.parse(tool.endedAt) - Date.parse(tool.startedAt) : NaN;
  const fields = args && typeof args === "object" && !Array.isArray(args) ? Object.entries(args) : null;
  return _jsxs9("details", { className: `pc-tool-activity pc-tool-activity--${tool.status}`, children: [_jsxs9("summary", { className: "pc-tool-activity__summary", children: [_jsx12("span", { className: "pc-tool-activity__state-icon", "aria-hidden": "true", children: _jsx12(Icon5, { name: tool.status === "completed" ? "check" : tool.status === "failed" ? "x" : tool.status === "waiting" ? "warning" : "loader", size: 15 }) }), _jsx12("strong", { children: tool.name }), _jsx12("span", { className: "pc-tool-activity__preview", title: preview.value, children: preview.value ? _jsxs9(_Fragment6, { children: [_jsx12("span", { className: "pc-tool-activity__key", children: preview.label }), _jsx12(TextLinks, { text: previewText })] }) : "No parameters" }), _jsx12("span", { className: "pc-tool-activity__status", children: labels2[tool.status] }), tool.policy ? _jsx12("span", { className: "pc-tool-activity__policy", "data-policy": tool.policy.decision, title: toolPolicyDecisionText(tool.policy), children: tool.policy.decision === "denied" ? "Denied by this chat's policy" : "Allowed by this chat's policy" }) : null, Number.isFinite(duration) && duration >= 0 ? _jsxs9("span", { className: "pc-tool-activity__duration", "data-approval-wait": tool.approvalWait ? "" : void 0, title: tool.approvalWait ? "Timed from request to result: includes the wait for your decision." : void 0, children: [formatDuration(duration), tool.approvalWait ? " incl. approval wait" : ""] }) : null, _jsx12("span", { className: "pc-tool-activity__chevron", "aria-hidden": "true", children: _jsx12(Icon5, { name: "chevronRight", size: 13 }) }), tool.error ? _jsx12("span", { className: "pc-tool-activity__error", title: tool.error, children: errorPreview }) : null] }), _jsxs9("div", { className: "pc-tool-activity__detail", children: [tool.policy ? _jsxs9("p", { className: "pc-tool-activity__policy-line", "data-policy": tool.policy.decision, children: [toolPolicyDecisionText(tool.policy), tool.policy.matched ? ` \xB7 matched ${tool.policy.matched}` : ""] }) : null, _jsx12(ToolSandboxLine, { sandbox: tool.sandbox }), tool.error ? _jsxs9(_Fragment6, { children: [_jsx12("h4", { children: "Error" }), _jsx12("pre", { className: "pc-tool-activity__output", children: _jsx12(TextLinks, { text: tool.error }) })] }) : null, _jsxs9("div", { className: "pc-tool-activity__detail-heading", children: [_jsx12("h4", { children: "Parameters" }), showCopy ? _jsxs9("button", { type: "button", onClick: async () => setCopied(await copyText(JSON.stringify(tool, null, 2))), children: [_jsx12(Icon5, { name: "copy", size: 13 }), copied ? "Copied" : "Copy details"] }) : null] }), fields ? _jsx12("dl", { className: "pc-tool-activity__parameters", children: fields.map(([key, value]) => _jsxs9(React5.Fragment, { children: [_jsx12("dt", { children: key }), _jsx12("dd", { children: value && typeof value === "object" ? _jsx12(JsonViewer, { value }) : _jsx12("code", { children: typeof value === "string" ? _jsx12(TextLinks, { text: value }) : JSON.stringify(value) }) })] }, key)) }) : tool.arguments === void 0 ? _jsx12("p", { children: "Arguments are unavailable in this ledger." }) : _jsx12(JsonViewer, { value: args }), tool.output !== void 0 ? _jsxs9(_Fragment6, { children: [_jsx12("h4", { children: "Result" }), typeof output === "string" ? _jsx12("pre", { className: "pc-tool-activity__output", children: _jsx12(TextLinks, { text: output }) }) : _jsx12("div", { className: "pc-tool-activity__output", children: _jsx12(JsonViewer, { value: output }) })] }) : null] })] });
}
function ToolActivityGroup({ tools, showCopy }) {
  const count2 = (status) => tools.filter((tool) => tool.status === status).length;
  return _jsxs9("section", { className: "pc-tool-group", "aria-label": "Tool activity", children: [_jsxs9("div", { className: "pc-tool-group__heading", children: [_jsx12(Icon5, { name: "terminal", size: 14 }), _jsx12("strong", { children: "Tools" }), _jsxs9("span", { children: [tools.length, " ", tools.length === 1 ? "call" : "calls"] }), _jsx12("div", {}), count2("running") ? _jsxs9("span", { className: "pc-tool-group__running", children: [count2("running"), " running"] }) : null, count2("waiting") ? _jsxs9("span", { className: "pc-tool-group__waiting", children: [count2("waiting"), " need approval"] }) : null, count2("failed") ? _jsxs9("span", { className: "pc-tool-group__failed", children: [count2("failed"), " failed"] }) : null, count2("completed") ? _jsxs9("span", { className: "pc-tool-group__completed", children: [count2("completed"), " done"] }) : null] }), tools.map((tool) => _jsx12(ToolActivity, { tool, showCopy }, tool.id))] });
}

// dist/message_footer.js
import { useEffect as useEffect10, useState as useState10 } from "react";
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
  const [day, setDay] = useState10(() => localDayKey());
  useEffect10(() => {
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
  const [open, setOpen] = useState11(false);
  const src = mediaSource(item.src);
  const name = String(item.name || item.label || "").trim() || "File";
  const href = fileRawLink({ href: item.href ? mediaSource(item.href) : void 0, src, contentType: item.contentType, name: item.name || item.label });
  const kind = fileViewerKind4(name, item.contentType);
  const needsText = fileViewerNeedsText3(kind);
  const hasText = typeof item.text === "string";
  if (!src && !href && !hasText)
    return null;
  const size = formatFileSize2(item.size);
  const label = String(item.label || "").trim() || name;
  return _jsxs10("figure", { className: "pc-chat-media__item pc-chat-media__item--file", "data-file-kind": kind, children: [_jsxs10("div", { className: "pc-chat-media__file-row", children: [_jsx13(Icon6, { name: "file", size: 14 }), _jsx13("span", { className: "pc-chat-media__file-name", title: name, children: label }), size ? _jsx13("span", { className: "pc-chat-media__file-size", children: size }) : null, onOpen ? _jsx13("button", {
    type: "button",
    className: "pc-chat-media__file-open",
    "data-action": "open-file",
    // The opener gets the item as the kit would render it: sanitized sources only.
    onClick: () => onOpen({ ...item, src: src || "", ...href ? { href } : { href: void 0 } }),
    children: "Open"
  }) : _jsx13("button", { type: "button", className: "pc-chat-media__file-open", "data-action": "toggle-file", "aria-expanded": open, onClick: () => setOpen((v) => !v), children: open ? "Close" : "Open" }), href ? _jsx13("a", { className: "pc-chat-media__link", ...rawLinkProps(href, String(item.name || "").trim() || label), children: "Raw file" }) : null] }), open && !onOpen ? _jsx13(FileViewer, {
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
  const [failed, setFailed] = useState11(false);
  if (item.kind === "file")
    return _jsx13(ChatMediaFile, { item, onOpen: onOpenFile, markdown: markdown || {} });
  const src = mediaSource(item.src);
  const href = item.href ? mediaSource(item.href) : void 0;
  const kind = item.kind === "image" || item.kind === "audio" || item.kind === "video" ? item.kind : null;
  if (!kind || !src && !href)
    return null;
  const noun = kind === "image" ? "Image" : kind === "video" ? "Video" : "Audio";
  const label = String(item.label || "").trim() || `Generated ${noun.toLowerCase()}`;
  const onError = () => setFailed(true);
  return _jsxs10("figure", { className: `pc-chat-media__item pc-chat-media__item--${kind}`, children: [src && kind === "image" ? _jsx13("img", { className: "pc-chat-media__image", src, alt: label, loading: "lazy", onError }) : null, src && kind === "video" ? _jsx13("video", { className: "pc-chat-media__video", src, controls: true, playsInline: true, preload: "metadata", "aria-label": label, onError }) : null, src && kind === "audio" ? _jsx13(AfAudioPlayer, { className: "pc-chat-media__audio", src, name: label }) : null, kind === "audio" && String(item.transcript || "").trim() ? _jsxs10("details", { className: "pc-chat-media__transcript", children: [_jsx13("summary", { children: "Transcript" }), _jsx13("p", { className: "pc-chat-media__transcript-text", children: String(item.transcript).trim() })] }) : null, failed ? _jsxs10("div", { className: "pc-chat-media__error", role: "note", children: [noun, " could not be decoded by this browser", href ? "; open the raw file with the link." : "."] }) : null, href ? _jsx13("figcaption", { className: "pc-chat-media__caption", children: _jsx13("a", { className: "pc-chat-media__link", ...rawLinkProps(href, String(item.name || "").trim() || label), children: label }) }) : null] });
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
  const [copy_state, set_copy_state] = useState11("idle");
  const copy_timer = useRef7(null);
  useEffect11(() => {
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
    return _jsx13(ToolActivity, { tool: m.toolActivity, showCopy: props.showCopy });
  const footer2 = props.renderFooter ? props.renderFooter(m) : null;
  if (props.variant?.(m) === "hint" || m.kind === "tool_policy_decision") {
    const level = String(m.level || "").trim().toLowerCase();
    return _jsxs10("div", { className: ["pc-chat-hint", level === "warn" || level === "error" ? `pc-chat-hint--${level}` : "", props.className].filter(Boolean).join(" "), role: "note", "data-variant": "hint", children: [_jsx13("span", { className: "pc-chat-hint__text", children: String(m.content || "") }), footer2 != null && footer2 !== false ? _jsx13("div", { className: "pc-chat-footer", children: footer2 }) : null] });
  }
  return _jsxs10("div", { className: ["pc-chat-item", `pc-chat-item--${role_ui.variant}`, live ? "pc-chat-item--live" : "", props.className].filter(Boolean).join(" "), ...live ? { "aria-busy": true } : {}, children: [_jsxs10("div", { className: "pc-chat-header", children: [_jsx13("div", { className: "pc-chat-avatar", "aria-hidden": "true", children: _jsx13(Icon6, { name: role_ui.icon, size: 14 }) }), _jsx13("span", { className: "pc-chat-role", children: role_ui.label }), live ? _jsxs10("span", { className: "pc-chat-live-indicator", title: live.label ? `Pending: ${live.label}` : "The reply is still being written", children: [_jsx13("span", { className: "pc-chat-live-dot", "aria-hidden": "true" }), live.label || "streaming"] }) : null, live?.caption ? _jsx13("span", { className: "pc-chat-live-caption", children: live.caption }) : null, _jsx13("span", { className: "pc-chat-header-spacer" }), time_label ? _jsx13("time", { className: "pc-chat-time", dateTime: time_iso || void 0, title: time_title || void 0, children: time_label }) : null, _jsxs10("div", { className: "pc-chat-header-actions", children: [show_speaker ? _jsx13("button", { className: "pc-chat-icon-btn", type: "button", "aria-label": speak_blocked || speak.title, title: speak_blocked || speak.title, "data-speak-state": speak_blocked ? "unavailable" : speak_state, ...speak_blocked ? { "aria-disabled": true } : {}, onClick: can_speak ? () => props.onSpeakToggle?.(m) : void 0, children: _jsx13(Icon6, { name: speak.icon, size: 22, className: speak.spinning ? "pc-chat-speak-spinner" : void 0 }, speak.icon) }) : null, show_copy ? _jsx13("button", { className: `pc-chat-icon-btn ${copy_state !== "idle" ? `pc-chat-icon-btn--${copy_state}` : ""}`.trim(), type: "button", "aria-label": "Copy message", title: copy_state === "idle" ? "Copy" : copy_state === "copied" ? "Copied" : "Copy failed", onClick: async () => {
    const ok = await copyText(String(m.content || ""));
    set_copy_state(ok ? "copied" : "failed");
    if (copy_timer.current !== null)
      window.clearTimeout(copy_timer.current);
    copy_timer.current = window.setTimeout(() => set_copy_state("idle"), 900);
  }, children: _jsx13(Icon6, { name: "copy", size: 22 }) }) : null] })] }), reasoning.trim() ? _jsxs10("details", { className: "pc-chat-thinking", children: [_jsx13("summary", { children: "Thinking" }), _jsx13("div", { className: "pc-chat-thinking-body", children: reasoning })] }) : null, has_text || !live && !media.length ? _jsx13("div", { className: "pc-chat-body", children: _jsx13(ChatMessageContent, { text: String(m.content || ""), renderMarkdown: props.renderMarkdown, jsonCollapseAfterDepth: props.jsonCollapseAfterDepth, images: props.images || (role_ui.variant === "user" ? "inline" : "link"), inlineImage: props.inlineImage }) }) : null, media.length ? _jsx13("div", { className: "pc-chat-media", children: media.map((item, idx) => _jsx13(ChatMediaItem, { item, onOpenFile: props.onOpenMedia, markdown: { renderMarkdown: props.renderMarkdown, images: props.images, inlineImage: props.inlineImage } }, item.id || `${item.kind}:${item.src}:${idx}`)) }) : null, m.artifactRefs?.length ? _jsx13("div", { className: "pc-chat-attachments", "aria-label": "Attached files", children: m.artifactRefs.map((a) => _jsx13(MessageArtifactChip, { artifact: a }, `${a.runId}:${a.id}`)) }) : null, attachments.length ? _jsx13("div", { className: "pc-chat-attachments", "aria-label": "Attachments", children: attachments.map((a, idx) => {
    const label = String(a.label || "").trim() || "attachment";
    const target2 = String(a.target || "").trim();
    const title = String(a.title || "").trim();
    const disabled = Boolean(a.disabled) || typeof a.onClick !== "function";
    return _jsxs10("button", { type: "button", className: "pc-chat-attachment-chip", title: title || label, onClick: disabled ? void 0 : a.onClick, disabled, children: [_jsx13(Icon6, { name: "paperclip", size: 14 }), target2 ? _jsx13("span", { className: `pc-chat-attachment-target pc-chat-attachment-target--${target2}`, children: target2 }) : null, _jsx13("span", { className: "pc-chat-attachment-name", children: label })] }, a.id || `${label}:${idx}`);
  }) }) : null, stats.length ? _jsx13("div", { className: "pc-chat-stats", "aria-label": "Stats", children: stats.slice(0, 12).map((s, idx) => {
    const label = String(s.label || "").trim();
    if (!label)
      return null;
    if (s.detail)
      return _jsx13(StatChip, { label, detail: s.detail, icon: s.icon, onClick: s.onClick }, s.id || `${label}:${idx}`);
    const title = String(s.title || "").trim();
    const clickable = typeof s.onClick === "function";
    const StatElement = clickable ? "button" : "span";
    return _jsxs10(StatElement, { ...clickable ? { type: "button" } : {}, className: ["pc-chat-stat", clickable ? "pc-chat-stat--clickable" : ""].filter(Boolean).join(" "), title: title || void 0, onClick: clickable ? () => s.onClick?.() : void 0, children: [s.icon ? _jsx13("span", { className: "pc-chat-stat-icon", "aria-hidden": "true", children: s.icon }) : null, _jsx13("span", { className: "pc-chat-stat-label", children: label })] }, s.id || `${label}:${idx}`);
  }) }) : null, footer2 != null && footer2 !== false ? _jsx13("div", { className: "pc-chat-footer", children: footer2 }) : null] });
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
  const list_ref = useRef8(null);
  const bottom_ref = useRef8(null);
  const [stick, set_stick] = useState12(true);
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
  useEffect12(() => {
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
  useEffect12(() => {
    if (!auto)
      return;
    if (!stick)
      return;
    const list = list_ref.current;
    if (list)
      list.scrollTop = list.scrollHeight;
  }, [auto, stick, content_signature]);
  useEffect12(() => {
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
    return m.toolActivity ? _jsx14(ToolActivityGroup, { tools: group.map((message) => message.toolActivity), showCopy: props.messageProps?.showCopy }, key) : _jsx14(ChatMessageCard, { message: m, ...props.messageProps || {} }, key);
  }), props.after, _jsx14("div", { ref: bottom_ref })] });
}

// dist/composer_attachments.js
import { jsx as _jsx15, jsxs as _jsxs12 } from "react/jsx-runtime";
import { Icon as Icon7 } from "@abstractframework/ui-kit";
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
  return _jsx15("div", { className: "pc-attachment-chips", role: "list", "aria-label": "Attached files", children: items.map((item) => {
    const pending = item.state === "queued" || item.state === "uploading";
    const { meta, state } = chipMeta(item);
    const thumb = previewSource(item.thumbnailUrl);
    return _jsxs12("div", { role: "listitem", tabIndex: 0, className: `pc-attachment-chip is-${item.state}`, "data-state": item.state, "aria-label": `${item.name}, ${state}`, "aria-busy": pending || void 0, children: [_jsx15("span", { className: "pc-attachment-chip__icon", "aria-hidden": "true", children: thumb ? _jsx15("img", { className: "pc-attachment-chip__thumb", src: thumb, alt: "", loading: "lazy" }) : pending ? _jsx15("span", { className: "pc-attachment-chip__spinner" }) : item.state === "attached" ? _jsx15(Icon7, { name: "paperclip", size: 13 }) : _jsx15(Icon7, { name: "warning", size: 13 }) }), _jsxs12("span", { className: "pc-attachment-chip__body", children: [_jsx15("span", { className: "pc-attachment-chip__name", title: item.name, children: item.name }), meta ? _jsx15("span", { className: "pc-attachment-chip__meta", children: meta }) : null] }), item.state === "failed" && props.onRetry ? _jsxs12("button", { type: "button", className: "pc-attachment-chip__action pc-attachment-chip__retry", "data-action": "retry", "aria-label": `Retry ${item.name}`, title: "Retry upload", disabled: props.disabled, onClick: () => props.onRetry?.(item.id), children: [_jsx15(Icon7, { name: "refresh", size: 12 }), _jsx15("span", { children: "Retry" })] }) : null, props.onRemove ? _jsx15("button", { type: "button", className: "pc-attachment-chip__action", "data-action": "remove", "aria-label": `Remove ${item.name}`, title: `Remove ${item.name}`, disabled: props.disabled, onClick: () => props.onRemove?.(item.id), children: _jsx15(Icon7, { name: "x", size: 12 }) }) : null] }, item.id);
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
  let count2 = 0;
  for (let index = 0; index < items.length; index += 1)
    if (items[index]?.kind === "file")
      count2 += 1;
  return count2 > 0 ? count2 : null;
}
function dropZoneLabel(count2) {
  if (count2 === 1)
    return "Drop file to attach";
  if (typeof count2 === "number" && count2 > 1)
    return `Drop ${count2} files to attach`;
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
import { jsxs as _jsxs13, jsx as _jsx16 } from "react/jsx-runtime";
import { useEffect as useEffect13, useRef as useRef9, useState as useState13 } from "react";
import { Icon as Icon8 } from "@abstractframework/ui-kit";

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
  return _jsxs13("div", { className: "pc-workflow-interaction__error", role: "alert", children: [_jsxs13("span", { children: ["Could not complete that action: ", props.message] }), _jsx16("button", { type: "button", className: "pc-workflow-interaction__retry", onClick: props.onRetry, disabled: props.disabled, children: "Try again" })] });
}
var L = WORKFLOW_INTERACTION_LABELS;
function WorkflowInteractionPanel(props) {
  const interaction = props.interaction;
  const card = props.variant === "card";
  const conversation = props.variant === "conversation";
  const [freeText, setFreeText] = useState13("");
  const [payload, setPayload] = useState13(() => interaction.kind === "event-wait" ? interaction.initialPayload || "" : "");
  const [pending, setPending] = useState13(null);
  const [settled, setSettled] = useState13(false);
  const [outcome, setOutcome] = useState13("");
  const [failure, setFailure] = useState13(null);
  const interactionKey = `${interaction.kind}:${interaction.id}`;
  const activeKeyRef = useRef9(interactionKey);
  const inFlightRef = useRef9(false);
  const settledRef = useRef9(false);
  const mountedRef = useRef9(true);
  const sequenceRef = useRef9(0);
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
      setOutcome(conversation ? `Your choice was sent. I\u2019m waiting for work to continue.${note ? " Some actions may still be blocked by your saved permissions; review the details if needed." : ""}` : `Response sent. Waiting for the workflow to continue.${note ? ` ${note}` : ""}`);
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
  useEffect13(() => {
    setFreeText("");
    setPayload(interaction.kind === "event-wait" ? interaction.initialPayload || "" : "");
    setFailure(null);
    setPending(null);
    setSettled(false);
    setOutcome("");
  }, [interactionKey]);
  useEffect13(() => {
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
  const title = conversation && interaction.kind === "tool-approval" ? interaction.publicRequest?.question || "May I take this next step?" : interaction.title || (interaction.kind === "tool-approval" ? "Tool approval required" : "Input required");
  const deferButton = (onDefer, label) => onDefer ? _jsx16("button", { type: "button", className: "pc-workflow-interaction__defer", "data-decision": "defer", disabled, onClick: () => void defer(onDefer), children: label }) : null;
  let body;
  if (interaction.kind === "ask-user") {
    body = _jsxs13("div", { className: "pc-workflow-interaction__body", children: [_jsx16("div", { className: "pc-workflow-interaction__prompt", children: interaction.prompt }), interaction.choices?.length ? _jsx16("div", { className: "pc-workflow-interaction__choices", "aria-label": "Choices", children: interaction.choices.map((choice) => _jsxs13("button", { type: "button", className: "pc-workflow-interaction__choice", "data-decision": "choice", disabled: disabled || choice.disabled, onClick: () => void run({ kind: "choice", answer: choice.id }, () => interaction.onSubmit(choice.id)), children: [_jsx16("span", { children: choice.label }), choice.description ? _jsx16("small", { children: choice.description }) : null] }, choice.id)) }) : null, interaction.allowFreeText !== false ? _jsxs13("div", { className: "pc-workflow-interaction__entry", children: [_jsx16("textarea", { "aria-label": "Response", value: freeText, onChange: (event) => setFreeText(event.target.value), placeholder: interaction.freeTextPlaceholder || "Type a response", rows: card ? 1 : 2, disabled, onKeyDown: (event) => {
      if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing || event.keyCode === 229)
        return;
      event.preventDefault();
      if (freeText.trim())
        void run({ kind: "free-text", answer: freeText }, () => interaction.onSubmit(freeText));
    } }, `${interactionKey}:text`), _jsx16("button", { type: "button", className: "pc-btn", "data-decision": "submit", disabled: disabled || !freeText.trim(), onClick: () => void run({ kind: "free-text", answer: freeText }, () => interaction.onSubmit(freeText)), children: pending?.kind === "free-text" ? "Sending\u2026" : interaction.submitLabel || L.submit })] }) : null, interaction.onSkip || interaction.onDefer ? _jsxs13("div", { className: "pc-workflow-interaction__buttons pc-workflow-interaction__buttons--secondary", children: [deferButton(interaction.onDefer, interaction.deferLabel || L.keepWaiting), interaction.onSkip ? _jsx16("button", { type: "button", className: "pc-workflow-interaction__skip", "data-decision": "skip", disabled, onClick: () => void run({ kind: "skip" }, interaction.onSkip), children: pending?.kind === "skip" ? "Continuing\u2026" : interaction.skipLabel || L.skip }) : null] }) : null] });
  } else if (interaction.kind === "tool-approval" && conversation) {
    const request = interaction.publicRequest;
    const needsReview = !request || request.reviewRequired;
    body = _jsxs13("div", { className: "pc-workflow-interaction__body pc-public-approval", children: [_jsxs13("div", { className: "pc-public-approval__context", children: [_jsxs13("div", { className: "pc-public-approval__reason", children: [_jsx16("p", { className: "pc-public-approval__reason-label", children: "Why I\u2019m asking" }), _jsx16("p", { children: request?.explanation?.text || "The reason for this request isn\u2019t available here." })] }), request?.actions.length ? _jsx16("ul", { className: "pc-public-approval__targets", "aria-label": "What this will do", "data-uniform": request.actions.every((a) => a.kind === request.actions[0].kind) && !["write", "edit", "unknown"].includes(request.actions[0].kind) || void 0, children: request.actions.map((action, index) => _jsxs13("li", { children: [_jsx16(Icon8, { name: action.kind === "page" || action.kind === "search" ? "book" : action.kind === "write" || action.kind === "edit" ? "edit" : action.kind === "folder" ? "folder" : action.kind === "unknown" ? "info" : "file", size: 20 }), _jsxs13("span", { children: [_jsx16("span", { className: "pc-public-approval__action", children: action.label }), action.target ? _jsx16("span", { className: "pc-public-approval__target", children: action.target }) : null] })] }, index)) }) : null, needsReview ? _jsx16("p", { className: "pc-public-approval__note", children: "I can\u2019t describe this request clearly here. Review the details before allowing it." }) : _jsx16("p", { className: "pc-public-approval__note", children: "Allow once covers only what is shown here. I\u2019ll ask again for later requests." })] }, interactionKey), _jsxs13("div", { className: "pc-workflow-interaction__buttons pc-public-approval__buttons", children: [deferButton(interaction.onDefer, interaction.deferLabel || L.decideLater), _jsxs13("button", { type: "button", className: "pc-workflow-interaction__deny", "data-decision": "deny", disabled, onClick: () => void run({ kind: "deny" }, interaction.onDeny), children: [_jsx16(Icon8, { name: "x", size: 18 }), pending?.kind === "deny" ? "Declining\u2026" : interaction.denyLabel || L.deny] }), !needsReview ? _jsxs13("button", { type: "button", className: "pc-btn", "data-decision": "approve", disabled, onClick: () => void run({ kind: "approve" }, interaction.onApprove), children: [_jsx16(Icon8, { name: "check", size: 18 }), pending?.kind === "approve" ? "Allowing\u2026" : interaction.approveLabel || L.allowOnce] }) : null, props.onReviewTechnical ? _jsxs13("button", { type: "button", className: "pc-public-approval__review", disabled, onClick: props.onReviewTechnical, children: [_jsx16(Icon8, { name: "list", size: 18 }), "Review details"] }) : null] }), needsReview && !props.onReviewTechnical ? _jsx16("p", { className: "pc-public-approval__note", children: "Switch to the conversation\u2019s detailed view to review this request." }) : null, interaction.deniedNote ? _jsx16("p", { className: "pc-public-approval__note", role: "note", children: "Some of these actions are blocked by your saved permissions. Allow once cannot override that choice. Review details to see what is blocked." }) : null] });
  } else if (interaction.kind === "tool-approval") {
    const reason = String(interaction.disabledReason || "").trim();
    const broadDisabled = disabled || Boolean(reason);
    const scopes = [
      !reason && interaction.onApproveForSession && interaction.approveForSessionDescription ? interaction.approveForSessionDescription : "",
      !reason && interaction.onApproveAll && interaction.approveAllDescription ? interaction.approveAllDescription : ""
    ].filter(Boolean);
    const scopeSummary = scopes.length ? String(interaction.broadScopeSummary || "").trim() : "";
    body = _jsxs13("div", { className: "pc-workflow-interaction__body", children: [_jsxs13("div", { className: "pc-workflow-interaction__prompt", children: ["Allow ", _jsx16("strong", { children: interaction.toolName }), " to run?"] }), interaction.detail ? card ? _jsxs13("details", { className: "pc-workflow-interaction__review", children: [_jsx16("summary", { children: "Review" }), _jsx16("div", { className: "pc-workflow-interaction__detail", children: interaction.detail })] }) : _jsx16("div", { className: "pc-workflow-interaction__detail", children: interaction.detail }) : null, _jsxs13("div", { className: "pc-workflow-interaction__buttons", children: [deferButton(interaction.onDefer, interaction.deferLabel || L.decideLater), _jsx16("button", { type: "button", className: "pc-workflow-interaction__deny", "data-decision": "deny", disabled, onClick: () => void run({ kind: "deny" }, interaction.onDeny), children: pending?.kind === "deny" ? "Denying\u2026" : interaction.denyLabel || L.deny }), _jsx16("button", { type: "button", className: "pc-btn", "data-decision": "approve", disabled, onClick: () => void run({ kind: "approve" }, interaction.onApprove), children: pending?.kind === "approve" ? "Allowing\u2026" : interaction.approveLabel || L.allowOnce }), interaction.onApproveForSession ? _jsx16("button", { type: "button", className: "pc-workflow-interaction__allow-session", "data-decision": "approve-session", disabled: broadDisabled, title: reason || interaction.approveForSessionDescription || void 0, onClick: () => void run({ kind: "approve-session" }, interaction.onApproveForSession), children: pending?.kind === "approve-session" ? "Allowing\u2026" : interaction.approveForSessionLabel || L.allowForChat }) : null, (interaction.approveKinds || []).map((entry) => _jsx16("button", { type: "button", className: "pc-workflow-interaction__allow-session pc-workflow-interaction__allow-kind", "data-decision": "approve-kind", "data-kind": entry.kind, disabled: broadDisabled, title: reason || interaction.approveForSessionDescription || void 0, onClick: () => void run({ kind: "approve-kind", toolset: entry.kind }, entry.onApprove), children: pending?.kind === "approve-kind" && pending.toolset === entry.kind ? "Allowing\u2026" : entry.label || L.allowKindForChat(entry.kind) }, entry.kind)), interaction.onApproveAll ? _jsx16("button", { type: "button", className: "pc-workflow-interaction__allow-all", "data-decision": "approve-all", disabled: broadDisabled, title: reason || interaction.approveAllDescription || void 0, onClick: () => void run({ kind: "approve-all" }, interaction.onApproveAll), children: pending?.kind === "approve-all" ? "Allowing\u2026" : interaction.approveAllLabel || L.allowAll }) : null] }), scopeSummary ? _jsx16("p", { className: "pc-workflow-interaction__scope", "data-scope-summary": "", children: scopeSummary }) : null, interaction.remember ? _jsxs13("label", { className: "pc-workflow-interaction__remember", children: [_jsx16("input", { type: "checkbox", checked: interaction.remember.checked, disabled, onChange: (event) => interaction.remember.onChange(event.target.checked) }), _jsx16("span", { children: interaction.remember.label })] }) : null, interaction.deniedNote ? _jsx16("p", { className: "pc-workflow-interaction__unavailable", role: "note", "data-denied-note": "", children: interaction.deniedNote }) : null, interaction.denyOptions?.length ? _jsxs13("details", { className: "pc-workflow-interaction__more", "data-more": "", children: [_jsx16("summary", { children: "More" }), _jsx16("p", { className: "pc-workflow-interaction__scope", children: L.denyForChatNote }), _jsx16("div", { className: "pc-workflow-interaction__buttons", children: interaction.denyOptions.map((option) => _jsx16("button", { type: "button", className: "pc-workflow-interaction__deny", "data-decision": "deny-chat", "data-key": option.key, disabled, onClick: () => void run({ kind: "deny-chat", key: option.key }, option.onDeny), children: pending?.kind === "deny-chat" && pending.key === option.key ? "Denying\u2026" : option.label }, option.key)) })] }) : null, interaction.policySummary ? _jsx16("p", { className: "pc-workflow-interaction__scope", "data-policy-summary": "", children: interaction.policySummary }) : null, interaction.scopeNote ? _jsx16("p", { className: "pc-workflow-interaction__scope-note", role: "note", "data-scope-note": "", children: interaction.scopeNote }) : null, interaction.notCovered ? _jsx16("p", { className: "pc-workflow-interaction__unavailable", role: "note", "data-not-covered": "", children: interaction.notCovered }) : null, reason && (interaction.onApproveAll || interaction.onApproveForSession || interaction.approveKinds?.length) ? _jsx16("p", { className: "pc-workflow-interaction__unavailable", role: "note", children: reason }) : null, scopeSummary && scopes.length ? _jsxs13("details", { className: "pc-workflow-interaction__scope-details", "data-scope-details": "", children: [_jsx16("summary", { children: "What the broader choices allow" }), scopes.map((text5) => _jsx16("p", { className: "pc-workflow-interaction__scope", children: text5 }, text5))] }) : scopes.map((text5) => _jsx16("p", { className: "pc-workflow-interaction__scope", children: text5 }, text5))] });
  } else {
    body = _jsxs13("div", { className: "pc-workflow-interaction__body", children: [_jsx16("div", { className: "pc-workflow-interaction__prompt", children: interaction.prompt }), _jsxs13("label", { className: "pc-workflow-interaction__entry", children: [_jsx16("span", { children: interaction.payloadLabel || (interaction.eventName ? `Payload for ${interaction.eventName}` : "Event payload") }), _jsx16("textarea", { value: payload, onChange: (event) => setPayload(event.target.value), placeholder: interaction.payloadPlaceholder || "Enter payload", rows: card ? 1 : 2, "aria-label": interaction.payloadLabel || (interaction.eventName ? `Payload for ${interaction.eventName}` : "Event payload"), disabled }, `${interactionKey}:payload`)] }), _jsx16("div", { className: "pc-workflow-interaction__buttons", children: _jsx16("button", { type: "button", className: "pc-btn", "data-decision": "send-event", disabled, onClick: () => void run({ kind: "event", payload }, () => interaction.onSend(payload)), children: pending?.kind === "event" ? "Sending\u2026" : interaction.sendLabel || L.sendEvent }) })] });
  }
  return _jsxs13("section", { className: ["pc-workflow-interaction", card ? "pc-workflow-interaction--card" : "", conversation ? "pc-workflow-interaction--conversation" : ""].filter(Boolean).join(" "), "data-variant": props.variant || "panel", "aria-labelledby": `pc-workflow-interaction-${interactionKey}`, children: [_jsxs13("div", { className: "pc-workflow-interaction__heading", children: [_jsx16(Icon8, { name: interaction.kind === "tool-approval" ? conversation ? "lock" : "warning" : interaction.kind === "event-wait" ? "history" : "info", size: card ? 14 : 16 }), _jsxs13("div", { children: [_jsx16("h3", { className: conversation && interaction.kind === "tool-approval" ? "pc-workflow-interaction__prompt" : void 0, tabIndex: -1, id: `pc-workflow-interaction-${interactionKey}`, children: title }), interaction.description && !(conversation && interaction.kind === "tool-approval") ? _jsx16("div", { className: "pc-workflow-interaction__description", children: interaction.description }) : null] })] }), body, failure ? _jsx16(ActionError, { message: conversation ? "Your choice could not be sent." : failure.message, onRetry: retry, disabled }) : null, _jsx16("div", { className: "pc-workflow-interaction__outcome", "aria-live": "polite", children: outcome })] });
}

// dist/avatar_conversation.js
import { jsx as _jsx17, Fragment as _Fragment7, jsxs as _jsxs14 } from "react/jsx-runtime";
import { useEffect as useEffect14, useMemo as useMemo7, useRef as useRef10, useState as useState14 } from "react";

// dist/conversation_model.js
var DEFAULT_CONVERSATION_CUES = {
  approval: { visual: true, audio: true, haptic: false },
  question: { visual: true, audio: true, haptic: false },
  completion: { visual: true, audio: true, haptic: false }
};
var row = (v) => v && typeof v === "object" && !Array.isArray(v) ? v : null;
function publicUpdate(value, runId) {
  const p = row(value);
  if (!p || typeof p.id !== "string" || !p.id.trim() || typeof p.text !== "string" || !p.text.trim() || p.text.length > 4e3)
    return null;
  if (p.run_id !== void 0 && p.run_id !== runId)
    return null;
  if (!Array.isArray(p.source_call_ids) || p.source_call_ids.some((id) => typeof id !== "string" || !id.trim()))
    return null;
  return { id: p.id, text: p.text, runId, sourceCallIds: [...new Set(p.source_call_ids)], ...typeof p.session_id === "string" ? { sessionId: p.session_id } : {}, ...typeof p.iteration === "number" ? { iteration: p.iteration } : {} };
}
function conversationMessages(messages) {
  const seen = /* @__PURE__ */ new Set();
  return messages.filter((m) => {
    const hasFiles = Boolean(m.attachments?.length || m.artifactRefs?.length || m.media?.length);
    if (m.live || m.toolActivity || !m.content.trim() && !hasFiles)
      return false;
    const allowed = m.role === "user" || m.role === "assistant" && ["public_update", "answer", "final", "question", "attachments"].includes(m.kind || "") || m.role === "system" && m.kind === "question_outcome" && m.source === "emit_event";
    if (!allowed || m.kind === "public_update" && !m.publicUpdate)
      return false;
    const key = `${m.runId || ""}:${m.publicUpdate?.id || m.id || `${m.kind}:${m.content}`}`;
    if (seen.has(key))
      return false;
    seen.add(key);
    return true;
  });
}
function conversationReply(text5, context, currentRunId, allowedSourceRunIds = []) {
  if (!context)
    return text5;
  if (context.kind !== "public_update" || !context.publicUpdate)
    return text5;
  if (!currentRunId || context.publicUpdate.runId !== context.runId || context.runId !== currentRunId && !allowedSourceRunIds.includes(context.publicUpdate.runId))
    throw new Error("The selected public update belongs to another run. Return to the latest exchange before guiding this run.");
  return `The person is replying to this quoted public update (context only):
${JSON.stringify({ message_id: context.id || context.publicUpdate.id, run_id: context.publicUpdate.runId, root_run_id: currentRunId, text: context.content })}

The person's message:
${text5}`;
}
function conversationPages(text5, max = 180) {
  const words = text5.trim().split(/\s+/);
  const pages = [];
  let page = "";
  for (const word of words) {
    if (page && page.length + word.length + 1 > max) {
      pages.push(page);
      page = "";
    }
    page += `${page ? " " : ""}${word}`;
  }
  if (page)
    pages.push(page);
  return pages;
}
function conversationState(input) {
  if (input.status === "completed" || input.status === "failed")
    return input.listening ? "listening" : input.speaking ? "speaking" : input.status;
  if (input.connection === "disconnected")
    return "disconnected";
  if (input.connection === "connecting" || input.connection === "reconnecting")
    return "connecting";
  if (input.status === "paused")
    return "paused";
  if (input.attention?.kind === "approval")
    return "approval";
  if (input.attention?.kind === "question")
    return "question";
  if (input.listening)
    return "listening";
  if (input.speaking)
    return "speaking";
  return input.status || "idle";
}
function conversationSnapshot(snapshot) {
  const interaction = snapshot.toolApprovalGranted ? null : snapshot.interaction;
  const wait = row(interaction?.wait);
  const details = row(wait?.details);
  const question = row(details?.question);
  const approval = interaction?.kind === "tool_approval" || details?.kind === "tool_approval" || details?.mode === "approval_required" || wait?.reason === "tool_approval";
  let attention = null;
  if (interaction && (approval || interaction.kind === "ask_user" || wait?.reason === "user" || wait?.reason === "ask_user")) {
    attention = { id: `${interaction.runId}:${String(question?.id || wait?.wait_key || interaction.stepId || "")}`, kind: approval ? "approval" : "question", ...question?.importance === "essential" || question?.importance === "clarification" ? { importance: question.importance } : {}, ...typeof question?.deadline === "string" ? { deadline: question.deadline } : {}, ...typeof question?.fallback === "string" ? { fallback: question.fallback } : {} };
  } else if (snapshot.status === "completed") {
    attention = { id: `${String(snapshot.run?.run_id || "")}:completed`, kind: "completion" };
  }
  const status = snapshot.status === "completed" ? "completed" : ["failed", "cancelled"].includes(snapshot.status) ? "failed" : snapshot.run?.paused === true || snapshot.status === "paused" ? "paused" : ["running", "waiting", "queued"].includes(snapshot.status) ? "working" : "idle";
  return { status, connection: snapshot.connection, attention, replaying: Boolean(snapshot.loading || snapshot.historyLoading) };
}
function conversationCueStep(previous, input) {
  const key = input.attention ? `${input.attention.kind}:${input.attention.id}` : "";
  const reset = !previous || previous.sessionKey !== input.sessionKey;
  const seen = new Set(reset ? [] : previous.seen);
  const fresh = Boolean(key && !seen.has(key));
  if (key)
    seen.add(key);
  const attentionNeeded = input.attention?.kind === "question" || input.attention?.kind === "approval";
  const canCue = !reset && previous.connected && input.connected && (!input.attended || attentionNeeded) && fresh && input.attention;
  return { cursor: { sessionKey: input.sessionKey, connected: input.connected, seen: [...seen] }, cue: canCue ? { ...input.attention, channels: { ...input.preferences[input.attention.kind] } } : null };
}
function conversationNarrationStep(previous, input) {
  const messages = conversationMessages(input.messages);
  const updates = messages.filter((m) => m.kind === "public_update");
  const reset = !previous || previous.sessionKey !== input.sessionKey;
  const seen = new Set(reset ? [] : previous.seen);
  const key = (m) => `${m.runId || ""}:${m.publicUpdate.id}`;
  const latest = messages[messages.length - 1];
  const fresh = latest?.kind === "public_update" && !seen.has(key(latest));
  for (const m of updates)
    seen.add(key(m));
  const canNarrate = !reset && previous.connected && input.connected && input.enabled && !input.attended && !input.listening && fresh;
  return { cursor: { sessionKey: input.sessionKey, connected: input.connected, seen: [...seen] }, message: canNarrate ? latest : null };
}

// dist/avatar_conversation.js
var labels = {
  idle: "Ready",
  working: "Working",
  paused: "Paused \u2014 work resumes only when you continue",
  listening: "Listening \u2014 your words have not been submitted",
  speaking: "Speaking",
  question: "A question for you",
  approval: "Permission required",
  completed: "Completed",
  failed: "Work stopped",
  connecting: "Connecting\u2026",
  disconnected: "Connection interrupted"
};
function AvatarConversation(props) {
  return _jsx17(AvatarConversationSession, { ...props }, props.sessionKey);
}
function AvatarConversationSession(props) {
  const [history, setHistory] = useState14(false);
  const [paused, setPaused] = useState14(false);
  const [hovered, setHovered] = useState14(false);
  const [focused, setFocused] = useState14(false);
  const [selected, setSelected] = useState14(null);
  const preferences = props.preferences || DEFAULT_CONVERSATION_CUES;
  const messages = useMemo7(() => conversationMessages(props.messages), [props.messages]);
  const latest = [...messages].reverse().find((m) => m.role === "assistant" || m.kind === "question_outcome") || null;
  const attended = Boolean(props.attended || history || paused || hovered || focused || selected);
  useEffect14(() => {
    props.onAttendedChange?.(attended);
    return () => props.onAttendedChange?.(false);
  }, [attended, props.onAttendedChange]);
  const [shown, setShown] = useState14(latest);
  const [page, setPage] = useState14(0);
  const shownText = shown?.content || (shown?.attachments?.length || shown?.artifactRefs?.length || shown?.media?.length ? "A result file is ready. Open conversation history to view it." : "");
  const pages = useMemo7(() => conversationPages(shownText), [shownText]);
  const state = conversationState(props);
  const cursor = useRef10(null);
  const narrationCursor = useRef10(null);
  const callbacks = useRef10(props);
  callbacks.current = props;
  useEffect14(() => {
    return () => {
      callbacks.current.onInterruptSpeech?.();
      callbacks.current.onReplyContext?.(null);
    };
  }, []);
  useEffect14(() => {
    if (props.listening)
      callbacks.current.onInterruptSpeech?.();
  }, [props.listening]);
  useEffect14(() => {
    if (!attended) {
      setShown(latest);
      setPage(0);
    }
  }, [latest, attended]);
  useEffect14(() => {
    if (attended || page >= pages.length - 1)
      return;
    const timer = setTimeout(() => setPage((p) => p + 1), Math.max(6500, (pages[page]?.length || 0) * 55));
    return () => clearTimeout(timer);
  }, [attended, page, pages]);
  useEffect14(() => {
    const connected = !props.replaying && (!props.connection || props.connection === "connected" || props.status === "completed" || props.status === "failed") && (typeof document === "undefined" || document.visibilityState !== "hidden");
    const next = conversationCueStep(cursor.current, { sessionKey: props.sessionKey, connected, attended, attention: props.attention, preferences });
    cursor.current = next.cursor;
    if (next.cue)
      props.onCue?.(next.cue);
  }, [props.sessionKey, props.connection, props.status, props.replaying, props.attention, props.onCue, attended, preferences]);
  useEffect14(() => {
    const connected = !props.replaying && (!props.connection || props.connection === "connected" || props.status === "completed" || props.status === "failed") && (typeof document === "undefined" || document.visibilityState !== "hidden");
    const next = conversationNarrationStep(narrationCursor.current, { sessionKey: props.sessionKey, connected, attended, enabled: Boolean(props.narrate) && props.status !== "paused", listening: props.listening, messages });
    narrationCursor.current = next.cursor;
    if (next.message) {
      props.onInterruptSpeech?.();
      props.onNarrate?.(next.message);
    }
  }, [messages, props.sessionKey, props.connection, props.replaying, props.status, props.narrate, props.listening, props.onNarrate, props.onInterruptSpeech, attended]);
  const interrupt = () => props.onInterruptSpeech?.();
  const follow = () => {
    setHistory(false);
    setPaused(false);
    setSelected(null);
    setShown(latest);
    setPage(0);
    props.onReplyContext?.(null);
  };
  const visibleAttention = props.attention && preferences[props.attention.kind].visual;
  const hasRequest = Boolean(props.interaction) && (props.interactionId === void 0 || Boolean(props.interactionId));
  return _jsxs14("section", { className: "pc-avatar-conversation", "aria-label": "Avatar conversation", "data-state": state, "data-has-request": hasRequest || void 0, children: [_jsx17("div", { className: "pc-avatar-conversation__scene", children: props.avatar }), _jsx17("p", { className: "pc-avatar-conversation__status", role: "status", children: labels[state] }), visibleAttention && !hasRequest ? _jsxs14("p", { className: "pc-avatar-conversation__attention", "data-kind": props.attention.kind, children: [props.attention.kind === "approval" ? "An explicit decision is required. Waiting never grants permission." : props.attention.kind === "completion" ? "The result is ready in conversation history." : props.attention.importance === "essential" ? "Your answer is required. I will keep waiting." : "Your input is welcome.", props.attention.kind === "question" && props.attention.importance === "clarification" ? _jsxs14(_Fragment7, { children: [" ", props.attention.deadline && Number.isFinite(Date.parse(props.attention.deadline)) ? _jsxs14(_Fragment7, { children: ["Answer by ", _jsx17("time", { dateTime: props.attention.deadline, children: new Date(props.attention.deadline).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) }), ". "] }) : null, props.attention.fallback ? `Without an answer: ${props.attention.fallback}` : ""] }) : null] }) : null, hasRequest ? _jsx17("div", { className: "pc-avatar-conversation__request", children: props.interaction }) : null, !hasRequest || shown ? _jsxs14("div", { className: "pc-avatar-conversation__captions", tabIndex: 0, "aria-label": "Public subtitles", "aria-live": attended ? "off" : "polite", onPointerDown: (event) => {
    if (event.pointerType === "touch") {
      interrupt();
      setPaused(true);
    }
  }, onMouseEnter: () => setHovered(true), onMouseLeave: () => setHovered(false), onFocus: () => setFocused(true), onBlur: (event) => {
    if (!event.currentTarget.contains(event.relatedTarget))
      setFocused(false);
  }, children: [_jsx17("p", { children: pages[page] || "Public updates and replies will appear here." }), pages.length > 1 ? _jsxs14("div", { className: "pc-avatar-conversation__pages", children: [_jsx17("button", { type: "button", disabled: page === 0, onClick: () => {
    interrupt();
    setPaused(true);
    setPage((p) => Math.max(0, p - 1));
  }, children: "Previous subtitle" }), _jsxs14("span", { children: [page + 1, " / ", pages.length] }), _jsx17("button", { type: "button", disabled: page === pages.length - 1, onClick: () => {
    interrupt();
    setPaused(true);
    setPage((p) => Math.min(pages.length - 1, p + 1));
  }, children: "Next subtitle" })] }) : null] }) : null, _jsxs14("div", { className: "pc-avatar-conversation__actions", children: [_jsx17("button", { type: "button", "aria-pressed": paused, onClick: () => {
    interrupt();
    setPaused((v) => !v);
  }, children: paused ? "Resume subtitles" : "Pause subtitles" }), _jsx17("button", { type: "button", "aria-expanded": history, onClick: () => {
    interrupt();
    setHistory((v) => !v);
  }, children: "Conversation history" }), attended ? _jsx17("button", { type: "button", onClick: follow, children: "Return to latest" }) : null, props.voiceControl ? _jsx17("span", { onPointerDownCapture: interrupt, onKeyDownCapture: (event) => {
    if (event.key === "Enter" || event.key === " ")
      interrupt();
  }, children: props.voiceControl }) : null, props.playbackControl] }), history ? _jsx17("ol", { className: "pc-avatar-conversation__history", "aria-label": "Public conversation history", children: messages.map((m, i) => _jsxs14("li", { children: [_jsx17("strong", { children: m.role === "user" ? "You" : m.kind === "question_outcome" ? "Question status" : m.kind === "public_update" ? "Public update" : "Reply" }), _jsx17(ChatMessageCard, { ...props.messageProps, message: { ...m, reasoning: void 0, live: void 0, toolActivity: void 0 } }), m.publicUpdate?.sourceCallIds.length ? _jsxs14("details", { children: [_jsx17("summary", { children: "Sources" }), _jsx17("ul", { children: m.publicUpdate.sourceCallIds.map((id) => _jsx17("li", { children: id }, id)) })] }) : null, m.publicUpdate ? _jsx17("button", { type: "button", "aria-pressed": selected === m, onClick: () => {
    interrupt();
    setSelected(m);
    setShown(m);
    setPage(0);
    props.onReplyContext?.(m);
  }, children: "Reply to this" }) : null] }, `${m.runId || ""}:${m.id || i}`)) }) : null, selected ? _jsxs14("p", { className: "pc-avatar-conversation__reply-context", children: ["Replying to the selected exchange. ", _jsx17("button", { type: "button", onClick: follow, children: "Clear reply context" })] }) : null, !hasRequest ? props.interaction : null] });
}

// dist/workflow_chat.js
function messageFor(error) {
  const message = error instanceof Error ? error.message : String(error || "Unknown error");
  return message.trim() || "Unknown error";
}
function WorkflowChat(props) {
  useAfTooltips();
  const artifactFetch = useMemo8(() => props.artifactFetch ? boundedArtifactFetch(props.artifactFetch) : void 0, [props.artifactFetch, props.attachmentScope]);
  const transcript = useMessageArtifacts(props.messages, artifactFetch, props.attachmentScope || "", props.attachmentRun);
  const [sendPending, setSendPending] = useState15(false);
  const [cancelPending, setCancelPending] = useState15(false);
  const [attachPending, setAttachPending] = useState15(false);
  const [error, setError] = useState15(null);
  const [steerMode, setSteerMode] = useState15(() => props.steer?.modes?.[0] || "guide");
  const [steerStatus, setSteerStatus] = useState15(null);
  const [copyState, setCopyState] = useState15("idle");
  const sendAbortRef = useRef11(null);
  const mountedRef = useRef11(true);
  const sendInFlightRef = useRef11(false);
  const cancelInFlightRef = useRef11(false);
  const attachInFlightRef = useRef11(false);
  const sendSequenceRef = useRef11(0);
  const cancelSequenceRef = useRef11(0);
  const attachSequenceRef = useRef11(0);
  useEffect15(() => {
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
  useEffect15(() => {
    setSteerStatus(null);
  }, [Boolean(props.busy)]);
  const acceptsFiles = typeof props.onFiles === "function";
  const sectionRef = useRef11(null);
  const [drag, setDrag] = useState15(null);
  const [announcement, setAnnouncement] = useState15("");
  const onFilesRef = useRef11(props.onFiles);
  onFilesRef.current = props.onFiles;
  const disabledRef = useRef11(disabled);
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
  const deliverRef = useRef11(deliverFiles);
  deliverRef.current = deliverFiles;
  useEffect15(() => {
    if (!acceptsFiles || typeof window === "undefined")
      return;
    const presence = new DragPresence();
    let watchdog = 0;
    const inside = (target2) => Boolean(sectionRef.current && target2 instanceof Node && sectionRef.current.contains(target2));
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
      const count2 = draggedFileCount(event.dataTransfer);
      setDrag((previous) => previous && previous.over === over && previous.count === (count2 ?? previous.count) ? previous : { count: count2 ?? previous?.count ?? null, over });
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
  const dropZone = drag ? _jsxs15("div", { className: [
    "pc-workflow-chat__dropzone",
    drag.over ? "is-over" : "",
    disabled ? "is-disabled" : ""
  ].filter(Boolean).join(" "), "aria-hidden": "true", children: [_jsx18("span", { className: "pc-workflow-chat__dropzone-icon", children: _jsx18(Icon9, { name: "paperclip", size: 18 }) }), _jsxs15("span", { className: "pc-workflow-chat__dropzone-text", children: [_jsx18("strong", { children: disabled ? "Attachments are unavailable right now" : dropZoneLabel(drag.count) }), disabled ? null : _jsx18("span", { children: drag.over ? "Release to upload to this conversation" : "Drop anywhere on the conversation" })] })] }) : null;
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
  const toolbarRow = toolbar ? _jsxs15("div", { className: "pc-workflow-chat__toolbar", role: "toolbar", "aria-label": "Conversation actions", children: [toolbar.onNewSession ? _jsxs15("button", { type: "button", className: "pc-workflow-chat__icon-button", "data-toolbar": "new", disabled, onClick: () => void runToolbar(toolbar.onNewSession), children: [_jsx18(Icon9, { name: "plus", size: 14 }), _jsx18("span", { children: "New chat" })] }) : null, toolbar.onClear ? _jsxs15("button", { type: "button", className: "pc-workflow-chat__icon-button", "data-toolbar": "clear", disabled, onClick: () => void runToolbar(toolbar.onClear), children: [_jsx18(Icon9, { name: "trash", size: 14 }), _jsx18("span", { children: "Clear" })] }) : null, toolbar.copyTranscript ? _jsxs15("button", { type: "button", className: "pc-workflow-chat__icon-button", "data-toolbar": "copy", onClick: () => void copyTranscript(), children: [_jsx18(Icon9, { name: copyState === "copied" ? "check" : "copy", size: 14 }), _jsx18("span", { children: copyState === "copied" ? "Copied" : copyState === "failed" ? "Copy failed" : "Copy" })] }) : null, toolbar.exportTranscript ? _jsxs15("button", { type: "button", className: "pc-workflow-chat__icon-button", "data-toolbar": "export", onClick: () => {
    const spec = toolbar.exportTranscript;
    downloadTextFile({
      filename: spec.filename,
      text: transcriptMarkdown(spec.heading),
      mime: "text/markdown;charset=utf-8"
    });
  }, children: [_jsx18(Icon9, { name: "download", size: 14 }), _jsx18("span", { children: "Export" })] }) : null] }) : null;
  const steerLabel = props.avatarConversation ? "Send" : activeSteerMode === "queue" ? "Queue" : "Steer";
  const steerNote = steerStatus ? props.avatarConversation ? "Sent. Your message is available to the assistant." : steerStatus.mode === "queue" ? `Queued for the next turn${typeof steerStatus.seq === "number" ? ` (seq ${steerStatus.seq})` : ""}.` : `${steerStatus.duplicate ? "Already queued" : "Queued"}${typeof steerStatus.seq === "number" ? ` (seq ${steerStatus.seq})` : ""}. ${steer?.parked ? "The run is waiting: your guidance delivers at its next wake (steers do not wake runs)." : "Delivers at the run's next loop boundary."}` : "";
  return _jsxs15("section", { ref: sectionRef, className: [
    "pc-workflow-chat",
    drag ? "pc-workflow-chat--dragging" : "",
    drag?.over ? "pc-workflow-chat--drag-over" : "",
    props.className
  ].filter(Boolean).join(" "), "aria-label": "Workflow chat", "data-stream-replies": props.streamReplies || "gateway_default", children: [props.header || toolbarRow ? _jsxs15("header", { className: [
    "pc-workflow-chat__header",
    toolbarRow ? "pc-workflow-chat__header--toolbar" : ""
  ].filter(Boolean).join(" "), children: [props.header ? _jsx18("div", { className: "pc-workflow-chat__header-main", children: props.header }) : null, toolbarRow] }) : null, _jsx18("div", { className: "pc-workflow-chat__transcript", children: _jsxs15(ArtifactFetchContext.Provider, { value: artifactFetch, children: [transcript.error && _jsxs15("p", { role: "status", className: "pc-workflow-chat__error", children: [transcript.error, " ", _jsx18("button", { type: "button", onClick: transcript.retry, children: "Retry attachment check" })] }), props.avatarConversation ? _jsx18(AvatarConversation, { ...props.avatarConversation, messages: transcript.messages, messageProps: {
    ...props.messageProps,
    ...props.messageProps?.renderFooter ? { renderFooter: (m) => props.messageProps.renderFooter(props.messages.find((original) => original === m || original.id && original.id === m.id) || m) } : {},
    ...props.renderMarkdown ? { renderMarkdown: props.renderMarkdown } : {}
  }, attended: Boolean(props.draft.trim()), interactionId: props.interaction ? `${props.interaction.kind}:${props.interaction.id}` : "", interaction: _jsxs15(_Fragment8, { children: [props.interaction ? _jsx18(WorkflowInteractionPanel, { interaction: props.interaction, disabled, variant: "conversation", onReviewTechnical: props.avatarConversation.onTechnicalView }) : null, blocked ? _jsx18("div", { className: "pc-workflow-chat__blocked", role: "status", children: props.blockedNotice }) : null] }) }) : _jsx18(ChatThread, { messages: transcript.messages, empty: props.emptyState, autoScroll: true, messageProps: {
    ...props.messageProps,
    ...props.messageProps?.renderFooter ? {
      renderFooter: (m) => props.messageProps.renderFooter(props.messages.find((original) => original === m || original.id && original.id === m.id) || m)
    } : {},
    ...props.renderMarkdown ? { renderMarkdown: props.renderMarkdown } : {}
  }, after: _jsxs15(_Fragment8, { children: [props.interaction ? _jsx18(WorkflowInteractionPanel, { interaction: props.interaction, disabled }) : null, blocked ? _jsx18("div", { className: "pc-workflow-chat__blocked", role: "status", children: props.blockedNotice }) : null] }), afterKey: `${props.interaction ? `${props.interaction.kind}:${props.interaction.id}` : ""}:${blocked ? "blocked" : ""}` })] }, props.attachmentScope) }), error ? _jsxs15("div", { className: "pc-workflow-chat__error", role: "alert", children: [_jsxs15("span", { children: ["Could not", " ", error.action === "send" ? "send this message" : error.action === "steer" ? props.avatarConversation ? "send this message" : activeSteerMode === "queue" ? "queue this message" : "steer the run" : error.action === "attach" ? "attach a file" : error.action === "toolbar" ? "complete that action" : "stop the run", ": ", error.message] }), error.action !== "toolbar" ? _jsx18("button", { type: "button", onClick: retry, disabled, children: "Try again" }) : null] }) : null, _jsxs15("div", { className: "pc-workflow-chat__composer", children: [_jsx18(ChatComposer, { variant: props.composerVariant, value: props.draft, onChange: (draft) => {
    if (props.avatarConversation)
      props.avatarConversation.onInterruptSpeech?.();
    props.onDraftChange(draft);
  }, onSubmit: () => void submit(), placeholder: props.placeholder || "Send a message", ariaLabel: "Message", disabled, busy: steering ? sendPending : composerBusy, sendLabel: steering ? steerLabel : props.sendLabel, busyLabel: steering ? props.avatarConversation ? "Sending\u2026" : activeSteerMode === "queue" ? "Queueing\u2026" : "Steering\u2026" : props.busyLabel, rows: 2, onAttach: props.onAttach ? () => void attach() : void 0, attachLabel: "Attach file", attachPending, leading: props.attachments || attachmentItems.length ? _jsxs15("div", { className: "pc-workflow-chat__attachments", children: [attachmentItems.length ? _jsx18(ComposerAttachmentChips, { items: attachmentItems, onRemove: props.onRemoveAttachment, onRetry: props.onRetryAttachment, disabled }) : null, props.attachments] }) : null, overlay: dropZone, onPaste: acceptsFiles ? onPaste : void 0, actions: _jsxs15(_Fragment8, { children: [props.composerExtras, steering && steerModes.length > 1 ? _jsx18("span", { className: "pc-workflow-chat__steer-modes", role: "group", "aria-label": "While the run is busy", children: steerModes.map((mode) => _jsx18("button", { type: "button", className: "pc-workflow-chat__steer-mode", "data-steer-mode": mode, "aria-pressed": activeSteerMode === mode, disabled: disabled || sendPending, onClick: () => setSteerMode(mode), children: mode === "queue" ? "Queue next turn" : "Guide this run" }, mode)) }) : null] }), trailingActions: props.composerTrailingActions || sending && props.onCancel || stopState ? _jsxs15(_Fragment8, { children: [props.composerTrailingActions, sending && props.onCancel ? _jsxs15("button", { type: "button", className: "pc-workflow-chat__stop", disabled: disabled || cancelPending || stopping, onClick: () => void cancel(), children: [_jsx18(Icon9, { name: "x", size: 14 }), _jsx18("span", { children: cancelPending || stopping ? "Stopping\u2026" : "Stop" })] }) : stopState ? _jsx18("span", { className: `pc-workflow-chat__stop-state pc-workflow-chat__stop-state--${stopState.phase}`, role: "status", "aria-live": "polite", children: stopState.label }) : null] }) : void 0 }), steer ? _jsx18("div", { className: "pc-workflow-chat__steer-status", role: "status", "aria-live": "polite", children: steerNote }) : null, acceptsFiles ? _jsx18("div", { className: "pc-sr-only", role: "status", "aria-live": "polite", children: liveMessage }) : null] }), props.footer ? _jsx18("footer", { className: "pc-workflow-chat__footer", children: props.footer }) : null] });
}

// dist/use_workflow_session.js
import { useEffect as useEffect16, useMemo as useMemo9, useSyncExternalStore } from "react";

// dist/workflow_evidence.js
var obj4 = (value) => value && typeof value === "object" && !Array.isArray(value) ? value : {};
var rows = (value) => Array.isArray(value) ? value.map(obj4) : [];
var str2 = (value) => typeof value === "string" ? value : "";
var uid = (value) => str2(value.runtime_call_id || value.call_uid);
var cid = (value) => str2(value.call_id || value.id);
function approvalWaitRecord(rec) {
  if (rec.status !== "waiting")
    return false;
  const wait = rec.result && typeof rec.result === "object" ? rec.result.wait : null;
  const details = wait && typeof wait.details === "object" ? wait.details : null;
  return details?.mode === "approval_required" || details?.kind === "tool_approval" || String(wait?.wait_key || "").startsWith("tool_approval:");
}
function foldWorkflowTools(state, entry) {
  const rec = entry.record, effect2 = obj4(rec.effect);
  if (effect2.type !== "tool_calls")
    return [];
  const result = obj4(rec.result), payloadCalls = rows(obj4(effect2.payload).tool_calls), calls = payloadCalls.length || rec.status !== "waiting" ? payloadCalls : rows(obj4(obj4(result.wait).details).tool_calls), results = rows(result.results);
  const source = calls.length ? calls : results;
  const changed = [];
  source.forEach((call, index) => {
    let matches = uid(call) ? results.filter((row2) => uid(row2) === uid(call)) : [];
    if (!matches.length && cid(call) && calls.filter((row2) => cid(row2) === cid(call)).length === 1)
      matches = results.filter((row2) => cid(row2) === cid(call));
    const output = !calls.length ? call : matches.length === 1 ? matches[0] : calls.length === results.length ? results[index] : {};
    const identity = uid(call) || uid(output) || `${str2(rec.idempotency_key) || str2(rec.step_id) || entry.cursor}:${index}`;
    const id = `${entry.runId}:${identity}`, previous = state.get(id);
    const name = str2(call.name || output.name) || previous?.name;
    if (!name)
      return;
    const completed = rec.status === "completed" || rec.status === "failed";
    const failed = rec.status === "failed" || output.success === false || Boolean(output.error);
    const args = call.arguments ?? output.arguments ?? previous?.arguments;
    const activity = {
      ...previous,
      id,
      runId: entry.runId,
      name,
      arguments: args,
      status: completed ? failed ? "failed" : "completed" : rec.status === "waiting" ? "waiting" : "running",
      ...typeof output.success === "boolean" ? { success: output.success } : {},
      ...output.output !== void 0 || output.result !== void 0 ? { output: output.output ?? output.result } : {},
      ...output.error ? { error: String(output.error) } : {},
      ...toolSandbox(output) ? { sandbox: toolSandbox(output) } : {},
      ...cid(call) || cid(output) ? { callId: cid(call) || cid(output) } : {},
      // The approval wait is part of startedAt..endedAt: say so (same rule as the replay view).
      ...previous?.approvalWait || approvalWaitRecord(rec) ? { approvalWait: true } : {},
      startedAt: previous?.startedAt || str2(rec.started_at) || void 0,
      endedAt: completed ? str2(rec.ended_at) || previous?.endedAt : previous?.endedAt
    };
    if (previous && ["completed", "failed"].includes(previous.status) && !completed)
      return;
    state.set(id, activity);
    changed.push(activity);
  });
  return changed;
}
function num(raw) {
  if (raw === void 0 || raw === null || raw === "" || typeof raw === "boolean")
    return void 0;
  const n = Number(raw);
  return Number.isFinite(n) && n >= 0 ? n : void 0;
}
function count(value, keys) {
  for (const key of keys) {
    const raw = value?.[key];
    if (raw === void 0 || raw === null || raw === "" || typeof raw === "boolean")
      continue;
    const n = Number(raw);
    if (Number.isFinite(n) && n >= 0)
      return Math.trunc(n);
  }
  return void 0;
}
function argsObject(value) {
  if (typeof value === "string") {
    try {
      return obj4(JSON.parse(value));
    } catch {
      return {};
    }
  }
  return obj4(value);
}
function addDistinct(list, value) {
  if (value === void 0 || value === "")
    return list;
  const out = list || [];
  if (!out.includes(value))
    out.push(value);
  return out;
}
function reasoningCount(usage) {
  return count(usage, ["reasoning_tokens", "thinking_tokens"]) ?? count(obj4(usage.completion_tokens_details), ["reasoning_tokens"]) ?? count(obj4(usage.output_tokens_details), ["reasoning_tokens"]);
}
function errorClass(output) {
  const value = obj4(typeof output === "string" && output.trim().startsWith("{") ? argsObject(output) : output);
  return str2(value.error_class);
}
function progressIndex(records) {
  const index = /* @__PURE__ */ new Map();
  for (const entry of records) {
    const rec = entry.record;
    if (obj4(rec.effect).type !== "emit_event")
      continue;
    const result = obj4(rec.result);
    if (str2(result.name) !== "abstract.progress")
      continue;
    const payload = obj4(result.payload);
    if (str2(payload.kind) !== "llm" || !str2(payload.step_id))
      continue;
    const key = `${str2(payload.run_id) || entry.runId}:${str2(payload.step_id)}`;
    const row2 = index.get(key) || {};
    const ttft = num(payload.ttft_s);
    if (ttft !== void 0)
      row2.ttftS = ttft;
    row2.provider = row2.provider || str2(payload.provider) || void 0;
    row2.model = row2.model || str2(payload.model) || void 0;
    index.set(key, row2);
  }
  return index;
}
function workflowEvidence(records) {
  const tools = /* @__PURE__ */ new Map(), seen = /* @__PURE__ */ new Set(), files2 = /* @__PURE__ */ new Set();
  const statistics = {
    llmCalls: 0,
    toolCalls: 0,
    changedFiles: []
  };
  let start = Infinity, end = -Infinity;
  let incompleteSplit = false;
  let newPrefillTokens = 0, newPrefillMs = 0;
  let promptPhaseNewMs = 0;
  const progress = progressIndex(records);
  const calls = [];
  const waited = /* @__PURE__ */ new Set();
  for (const entry of records) {
    const rec = entry.record;
    const key = `${entry.runId}:${rec.step_id || entry.cursor}:${rec.status}`;
    if (seen.has(key))
      continue;
    seen.add(key);
    for (const raw of [rec.started_at, rec.ended_at]) {
      const at = Date.parse(str2(raw));
      if (Number.isFinite(at)) {
        start = Math.min(start, at);
        end = Math.max(end, at);
      }
    }
    for (const activity of foldWorkflowTools(tools, entry))
      if (activity.status === "waiting")
        waited.add(activity.id);
    if (obj4(rec.effect).type !== "llm_call" || rec.status !== "completed")
      continue;
    statistics.llmCalls += 1;
    const result = obj4(rec.result), nested = obj4(result.output);
    const usage = obj4(result.usage || result.token_usage || result.tokens || nested.usage || nested.token_usage || nested.tokens);
    const input = count(usage, [
      "input_tokens",
      "prompt_tokens",
      "prompt",
      "input",
      "in"
    ]);
    const output = count(usage, [
      "output_tokens",
      "completion_tokens",
      "completion",
      "output",
      "out"
    ]);
    const total = count(usage, ["total_tokens", "total"]) ?? (input !== void 0 || output !== void 0 ? (input || 0) + (output || 0) : void 0);
    if (total !== void 0 && (input === void 0 || output === void 0 || input + output !== total))
      incompleteSplit = true;
    if (input !== void 0)
      statistics.inputTokens = (statistics.inputTokens || 0) + input;
    if (output !== void 0)
      statistics.outputTokens = (statistics.outputTokens || 0) + output;
    if (total !== void 0)
      statistics.totalTokens = (statistics.totalTokens || 0) + total;
    const genTime = num(result.gen_time ?? nested.gen_time);
    if (genTime !== void 0) {
      statistics.genTimeMs = (statistics.genTimeMs || 0) + genTime;
      statistics.timedCalls = (statistics.timedCalls || 0) + 1;
    }
    const metadata = obj4(result.metadata || nested.metadata);
    const performance = obj4(metadata.performance);
    const promptTps = num(performance.prompt_tokens_per_second);
    const generationTps = num(performance.generation_tokens_per_second);
    const promptCache = obj4(metadata.prompt_cache);
    const cached = num(promptCache.cached_tokens);
    const fed = num(promptCache.fed_tokens);
    if (promptTps !== void 0 || generationTps !== void 0) {
      statistics.measuredSpeedCalls = (statistics.measuredSpeedCalls || 0) + 1;
      if (promptTps !== void 0 && promptTps > 0) {
        statistics.promptTokensPerSecond = (statistics.promptTokensPerSecond || 0) + promptTps;
        if (input !== void 0) {
          const promptMs = input / promptTps * 1e3;
          statistics.prefillMs = (statistics.prefillMs || 0) + promptMs;
          if (fed !== void 0) {
            newPrefillTokens += fed;
            newPrefillMs += promptMs;
          }
        }
      }
      if (generationTps !== void 0 && generationTps > 0) {
        statistics.generationTokensPerSecond = (statistics.generationTokensPerSecond || 0) + generationTps;
        if (output !== void 0)
          statistics.decodeMs = (statistics.decodeMs || 0) + output / generationTps * 1e3;
      }
    }
    if (cached !== void 0 || fed !== void 0) {
      statistics.measuredCacheCalls = (statistics.measuredCacheCalls || 0) + 1;
      statistics.cachedTokens = (statistics.cachedTokens || 0) + (cached || 0);
      statistics.fedTokens = (statistics.fedTokens || 0) + (fed || 0);
      const outcome = str2(promptCache.outcome);
      if (outcome) {
        const seenOutcomes = statistics.cacheOutcomes || [];
        if (!seenOutcomes.includes(outcome))
          seenOutcomes.push(outcome);
        statistics.cacheOutcomes = seenOutcomes;
      }
    }
    const stepId = str2(rec.step_id) || void 0;
    const facts = stepId && progress.get(`${entry.runId}:${stepId}`) || {};
    const route = obj4(result.route);
    const call = { runId: entry.runId };
    if (stepId)
      call.stepId = stepId;
    if (str2(rec.started_at))
      call.startedAt = str2(rec.started_at);
    const model = str2(result.model || nested.model) || str2(route.model) || facts.model;
    const provider = str2(route.provider) || str2(obj4(metadata._provider_request).provider) || facts.provider || str2(result.provider);
    if (model)
      call.model = model;
    if (provider)
      call.provider = provider;
    if (model)
      statistics.models = addDistinct(statistics.models, model);
    if (provider)
      statistics.providers = addDistinct(statistics.providers, provider);
    if (total === void 0 || input !== void 0 && output !== void 0 && input + output === total) {
      if (input !== void 0)
        call.inputTokens = input;
      if (output !== void 0)
        call.outputTokens = output;
    }
    if (total !== void 0)
      call.totalTokens = total;
    const reasoning = reasoningCount(usage);
    if (reasoning !== void 0) {
      call.reasoningTokens = reasoning;
      statistics.reasoningTokens = (statistics.reasoningTokens || 0) + reasoning;
    }
    if (cached !== void 0)
      call.cachedTokens = cached;
    if (fed !== void 0)
      call.fedTokens = fed;
    if (str2(promptCache.outcome))
      call.cacheOutcome = str2(promptCache.outcome);
    if (str2(promptCache.backend)) {
      call.cacheBackend = str2(promptCache.backend);
      statistics.cacheBackends = addDistinct(statistics.cacheBackends, call.cacheBackend);
    }
    if (genTime !== void 0)
      call.genTimeMs = genTime;
    if (promptTps !== void 0 && promptTps > 0)
      call.promptTokensPerSecond = promptTps;
    if (generationTps !== void 0 && generationTps > 0)
      call.generationTokensPerSecond = generationTps;
    if (facts.ttftS !== void 0) {
      call.ttftMs = facts.ttftS * 1e3;
      call.promptMs = call.ttftMs;
      call.promptSource = "ttft";
      statistics.ttftMs = (statistics.ttftMs || 0) + call.ttftMs;
      statistics.ttftCalls = (statistics.ttftCalls || 0) + 1;
    } else if (call.promptTokensPerSecond !== void 0 && input !== void 0) {
      call.promptMs = input / call.promptTokensPerSecond * 1e3;
      call.promptSource = "rate";
    }
    if (call.promptMs !== void 0) {
      statistics.promptPhaseMs = (statistics.promptPhaseMs || 0) + call.promptMs;
      statistics.promptPhaseCalls = (statistics.promptPhaseCalls || 0) + 1;
      if (fed !== void 0 && call.promptMs > 0) {
        call.promptNewTokensPerSecond = fed / (call.promptMs / 1e3);
        statistics.promptPhaseNewTokens = (statistics.promptPhaseNewTokens || 0) + fed;
        promptPhaseNewMs += call.promptMs;
      }
    }
    if (call.ttftMs !== void 0 && genTime !== void 0 && genTime >= call.ttftMs)
      call.generationMs = genTime - call.ttftMs;
    else if (call.generationTokensPerSecond !== void 0 && output !== void 0)
      call.generationMs = output / call.generationTokensPerSecond * 1e3;
    if (call.generationMs !== void 0 && output !== void 0) {
      statistics.generationPhaseMs = (statistics.generationPhaseMs || 0) + call.generationMs;
      statistics.generationPhaseTokens = (statistics.generationPhaseTokens || 0) + output;
    }
    const spec = obj4(metadata.speculation);
    if (Object.keys(spec).length) {
      const row2 = {};
      if (str2(spec.mode))
        row2.mode = str2(spec.mode);
      if (typeof spec.used === "boolean")
        row2.used = spec.used;
      if (str2(spec.draft_kind))
        row2.draftKind = str2(spec.draft_kind);
      const accepted = count(spec, ["accepted_tokens"]), drafted = count(spec, ["drafted_tokens"]), rounds = count(spec, ["rounds"]), draftLength = count(spec, ["num_draft_tokens"]);
      if (accepted !== void 0)
        row2.acceptedTokens = accepted;
      if (drafted !== void 0)
        row2.draftedTokens = drafted;
      if (accepted !== void 0 && drafted)
        row2.acceptanceRate = accepted / drafted;
      if (rounds !== void 0)
        row2.rounds = rounds;
      if (draftLength !== void 0)
        row2.draftLength = draftLength;
      call.speculation = row2;
      const agg = statistics.speculation || (statistics.speculation = { calls: 0, used: 0 });
      agg.calls += 1;
      if (row2.used)
        agg.used += 1;
      if (row2.mode)
        agg.modes = addDistinct(agg.modes, row2.mode);
      if (row2.draftKind)
        agg.draftKinds = addDistinct(agg.draftKinds, row2.draftKind);
      if (accepted !== void 0 && drafted !== void 0) {
        agg.acceptedTokens = (agg.acceptedTokens || 0) + accepted;
        agg.draftedTokens = (agg.draftedTokens || 0) + drafted;
      }
      if (rounds !== void 0)
        agg.rounds = (agg.rounds || 0) + rounds;
      if (draftLength !== void 0)
        agg.draftLengths = addDistinct(agg.draftLengths, draftLength);
    }
    calls.push(call);
  }
  if (calls.length) {
    if (calls.every((call) => call.startedAt))
      calls.sort((a, b) => Date.parse(a.startedAt) - Date.parse(b.startedAt));
    statistics.modelCalls = calls;
  }
  if (promptPhaseNewMs > 0 && statistics.promptPhaseNewTokens !== void 0)
    statistics.promptPhaseTokensPerSecond = statistics.promptPhaseNewTokens / (promptPhaseNewMs / 1e3);
  if (statistics.generationPhaseMs && statistics.generationPhaseTokens !== void 0)
    statistics.generationPhaseTokensPerSecond = statistics.generationPhaseTokens / (statistics.generationPhaseMs / 1e3);
  if (statistics.speculation?.draftedTokens)
    statistics.speculation.acceptanceRate = (statistics.speculation.acceptedTokens || 0) / statistics.speculation.draftedTokens;
  if (statistics.measuredSpeedCalls) {
    if (statistics.promptTokensPerSecond !== void 0)
      statistics.promptTokensPerSecond /= statistics.measuredSpeedCalls;
    if (statistics.generationTokensPerSecond !== void 0)
      statistics.generationTokensPerSecond /= statistics.measuredSpeedCalls;
  }
  if (newPrefillMs > 0) {
    statistics.prefillNewTokens = newPrefillTokens;
    statistics.prefillNewTokensPerSecond = newPrefillTokens / (newPrefillMs / 1e3);
  }
  const batches = /* @__PURE__ */ new Map();
  for (const tool of tools.values()) {
    if (tool.status === "waiting") {
      statistics.toolsWaiting = (statistics.toolsWaiting || 0) + 1;
      continue;
    }
    if (tool.status === "running") {
      statistics.toolsRunning = (statistics.toolsRunning || 0) + 1;
      continue;
    }
    if (!["completed", "failed"].includes(tool.status))
      continue;
    statistics.toolCalls += 1;
    const failedCall = tool.status === "failed";
    if (failedCall)
      statistics.toolsFailed = (statistics.toolsFailed || 0) + 1;
    const byName = statistics.toolBreakdown || (statistics.toolBreakdown = {});
    const row2 = byName[tool.name] || (byName[tool.name] = { calls: 0, failed: 0 });
    row2.calls += 1;
    if (failedCall) {
      row2.failed += 1;
      const failure = errorClass(tool.output);
      if (failure)
        (row2.errors || (row2.errors = {}))[failure] = (row2.errors?.[failure] || 0) + 1;
    }
    const began = Date.parse(str2(tool.startedAt)), ended = Date.parse(str2(tool.endedAt));
    if (Number.isFinite(began) && Number.isFinite(ended) && ended >= began) {
      const batchKey = `${tool.runId}|${tool.startedAt}|${tool.endedAt}`;
      const batch = batches.get(batchKey) || { ms: ended - began, calls: 0, names: /* @__PURE__ */ new Map(), waited: false };
      batch.calls += 1;
      batch.names.set(tool.name, (batch.names.get(tool.name) || 0) + 1);
      if (waited.has(tool.id))
        batch.waited = true;
      batches.set(batchKey, batch);
    }
    if (tool.success !== true)
      continue;
    if (![
      "write_file",
      "create_file",
      "save_file",
      "edit_file",
      "update_file",
      "replace_in_file",
      "delete_file",
      "remove_file",
      "move_file",
      "rename_file",
      "copy_file"
    ].includes(tool.name))
      continue;
    const args = argsObject(tool.arguments);
    const path = str2(args.destination || args.destination_path || args.file_path || args.path || args.filename);
    if (path)
      files2.add(path);
  }
  for (const batch of batches.values()) {
    statistics.toolBatches = (statistics.toolBatches || 0) + 1;
    statistics.toolTimeMs = (statistics.toolTimeMs || 0) + batch.ms;
    if (batch.waited)
      statistics.toolTimeIncludesApproval = true;
    const names = [...batch.names.keys()].sort();
    if (!statistics.slowestToolBatch || batch.ms > statistics.slowestToolBatch.ms)
      statistics.slowestToolBatch = { ms: batch.ms, calls: batch.calls, tools: names };
    const row2 = statistics.toolBreakdown?.[names[0]];
    if (names.length === 1 && row2)
      row2.ms = (row2.ms || 0) + batch.ms;
    else
      for (const name of names) {
        const shared = statistics.toolBreakdown?.[name];
        if (shared)
          shared.sharedBatches = (shared.sharedBatches || 0) + 1;
      }
  }
  statistics.changedFiles = [...files2];
  if (incompleteSplit) {
    delete statistics.inputTokens;
    delete statistics.outputTokens;
  }
  if (Number.isFinite(start) && Number.isFinite(end))
    statistics.durationMs = Math.max(0, end - start);
  return { tools: [...tools.values()], statistics };
}
function historyRecords(history) {
  const ledgers = obj4(obj4(history).ledgers);
  return Object.entries(ledgers).flatMap(([runId, ledger]) => rows(obj4(ledger).items).map((item, index) => ({
    runId,
    cursor: Number(item.cursor) || index + 1,
    record: Object.keys(obj4(item.record)).length ? obj4(item.record) : item
  })));
}

// dist/llm_delta.js
var LLM_DELTA_EVENT = "llm.delta";
var LLM_DELTA_END_EVENT = "llm.delta_end";
function record(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : null;
}
function nonEmpty(value) {
  return typeof value === "string" && value.trim() !== "";
}
function seqOf(value) {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}
function isLlmDeltaEnd(event) {
  return "reason" in event;
}
function validateLlmDeltaEvent(value, eventName) {
  const row2 = record(value);
  const kind = row2?.kind;
  const label = eventName || (typeof kind === "string" && kind ? kind : row2 && "reason" in row2 ? LLM_DELTA_END_EVENT : LLM_DELTA_EVENT);
  const bad = (why) => {
    throw new Error(`Malformed ${label} event from the gateway: ${why}`);
  };
  if (eventName !== void 0 && eventName !== LLM_DELTA_EVENT && eventName !== LLM_DELTA_END_EVENT)
    bad(`unknown event name ${JSON.stringify(eventName)}`);
  if (!row2)
    return bad("the payload is not an object");
  if (kind !== void 0 && kind !== LLM_DELTA_EVENT && kind !== LLM_DELTA_END_EVENT)
    bad(`unknown kind ${JSON.stringify(kind)}`);
  if (kind !== void 0 && eventName !== void 0 && kind !== eventName)
    bad(`kind ${JSON.stringify(kind)} does not match the event name`);
  if (!nonEmpty(row2.run_id))
    bad("run_id is missing");
  if (!nonEmpty(row2.call_id))
    bad("call_id is missing");
  if (!seqOf(row2.seq))
    bad("seq is not a non-negative integer");
  const isEnd = eventName || kind ? (eventName || kind) === LLM_DELTA_END_EVENT : "reason" in row2;
  if (row2.root_run_id !== void 0 && !nonEmpty(row2.root_run_id))
    bad("root_run_id is not a run id");
  if (row2.parent_run_id !== void 0 && row2.parent_run_id !== null && !nonEmpty(row2.parent_run_id))
    bad("parent_run_id is neither a run id nor null");
  const common = {
    run_id: row2.run_id,
    ...nonEmpty(row2.root_run_id) ? { root_run_id: row2.root_run_id } : {},
    ...row2.parent_run_id !== void 0 ? { parent_run_id: row2.parent_run_id } : {},
    ...nonEmpty(row2.node_id) ? { node_id: row2.node_id } : {},
    call_id: row2.call_id,
    seq: row2.seq
  };
  if (isEnd) {
    if (!["completed", "failed", "cancelled", "unavailable"].includes(String(row2.reason)))
      bad(`unknown reason ${JSON.stringify(row2.reason)}`);
    if (row2.detail !== void 0 && row2.detail !== null && typeof row2.detail !== "string")
      bad("detail is not a string");
    return { kind: LLM_DELTA_END_EVENT, ...common, reason: row2.reason, ...nonEmpty(row2.detail) ? { detail: row2.detail } : {} };
  }
  if (typeof row2.text !== "string")
    bad("text is not a string");
  if (row2.channel !== "content" && row2.channel !== "reasoning")
    bad(`unknown channel ${JSON.stringify(row2.channel)}`);
  if (typeof row2.snapshot !== "boolean")
    bad("snapshot is not a boolean");
  return {
    kind: LLM_DELTA_EVENT,
    ...common,
    text: row2.text,
    channel: row2.channel,
    snapshot: row2.snapshot
  };
}
var UNAVAILABLE_REASONS = {
  structured_output: "this step asks the model for structured output",
  remote_core: "the model runs on a remote AbstractCore server",
  provider_cannot_stream: "the model provider cannot stream",
  sink_error: "the gateway could not relay the live text",
  usage_unavailable: "the provider does not report token usage while streaming"
};
function describeStreamUnavailable(detail) {
  const why = detail ? UNAVAILABLE_REASONS[detail] || `the gateway reported "${detail}"` : "the gateway gave no reason";
  return `This reply is not streamed: ${why}. It appears when it is complete.`;
}

// dist/replay_view.js
var REPLAY_SCALAR_KEYS = ["version", "root_run_id", "workflow", "session_id", "status", "display_status", "cursor", "interaction", "open_waits", "usage", "warnings"];
var REPLAY_LIST_KEYS = ["runs", "messages", "activities", "artifacts"];
var own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
function pyStr(value) {
  if (value === null || value === void 0)
    return "None";
  if (value === true)
    return "True";
  if (value === false)
    return "False";
  return String(value);
}
function orderPart(value) {
  const n = typeof value === "boolean" ? Number(value) : value;
  if (typeof n === "number" && Number.isInteger(n)) {
    const digits = String(Math.abs(n));
    return n < 0 ? `-${digits.padStart(11, "0")}` : digits.padStart(12, "0");
  }
  return pyStr(value);
}
function comparePy(a, b) {
  if (a === b)
    return 0;
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i += 1) {
    const x = a.charCodeAt(i);
    const y = b.charCodeAt(i);
    if (x === y)
      continue;
    const surrogate = (c) => c >= 55296 && c <= 57343;
    if (surrogate(x) || surrogate(y))
      return (a.codePointAt(i) ?? x) - (b.codePointAt(i) ?? y);
    return x - y;
  }
  return a.length - b.length;
}
function itemId(key, item) {
  return pyStr(key === "runs" ? item.run_id : item.id);
}
function orderKey(key, item) {
  const order = Array.isArray(item.order) && item.order.length ? item.order : [];
  return [order.map(orderPart), itemId(key, item)];
}
function compareKeys(a, b) {
  const n = Math.min(a[0].length, b[0].length);
  for (let i = 0; i < n; i += 1) {
    const c = comparePy(a[0][i], b[0][i]);
    if (c)
      return c;
  }
  if (a[0].length !== b[0].length)
    return a[0].length - b[0].length;
  return comparePy(a[1], b[1]);
}
function compareReplayOrder(a, b) {
  return compareKeys(orderKey("messages", a), orderKey("messages", b));
}
function jsonEqual(a, b) {
  if (a === b)
    return true;
  if (a === void 0 || b === void 0)
    return a === b || a == null && b == null;
  if (Array.isArray(a) || Array.isArray(b)) {
    if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length)
      return false;
    return a.every((x, i) => jsonEqual(x, b[i]));
  }
  if (a && b && typeof a === "object" && typeof b === "object") {
    const ka = Object.keys(a);
    const kb = Object.keys(b);
    return ka.length === kb.length && ka.every((k) => own(b, k) && jsonEqual(a[k], b[k]));
  }
  return false;
}
function applyDelta(view, delta) {
  const out = view && Object.keys(view).length ? { ...view } : Object.fromEntries(REPLAY_LIST_KEYS.map((k) => [k, []]));
  for (const k of REPLAY_SCALAR_KEYS)
    if (own(delta, k))
      out[k] = delta[k];
  for (const k of REPLAY_LIST_KEYS) {
    const items = delta[k];
    const current = Array.isArray(out[k]) && out[k].length ? out[k] : [];
    if (!Array.isArray(items) || !items.length) {
      out[k] = current;
      continue;
    }
    const rows2 = [...current];
    const where = new Map(rows2.map((it, i) => [itemId(k, it), i]));
    let resort = false;
    for (const raw of items) {
      const id = itemId(k, raw);
      const i = where.get(id);
      if (i === void 0) {
        where.set(id, rows2.length);
        rows2.push(raw);
        resort = true;
      } else {
        if (!jsonEqual(rows2[i].order ?? null, raw.order ?? null))
          resort = true;
        rows2[i] = raw;
      }
    }
    if (resort) {
      const keyed = rows2.map((it) => ({ it, key: orderKey(k, it) }));
      keyed.sort((a, b) => compareKeys(a.key, b.key));
      out[k] = keyed.map((x) => x.it);
    } else
      out[k] = rows2;
  }
  return out;
}
var ReplayViewFold = class {
  constructor() {
    this.view = null;
    this.lastEventId = null;
    this.terminal = false;
  }
  /**
   * Start from (or replace with) a view read with `GET /view` (its ETag/`cursor.token` is the
   * stream's `Last-Event-ID`). A read older than the held view (a slow GET overtaken by stream
   * frames) is refused: returns false and keeps the newer view.
   */
  adopt(view, etag) {
    if (this.view && isOlderCursor(view.cursor?.runs, this.view.cursor?.runs))
      return false;
    this.view = view;
    this.lastEventId = unquoteEtag(etag) || view.cursor?.token || null;
    return true;
  }
  apply(frame) {
    if (frame.event === "done") {
      this.terminal = true;
      return "done";
    }
    if (frame.event !== "view" && frame.event !== "delta")
      return "ignored";
    const data = JSON.parse(frame.data);
    if (frame.event === "view") {
      this.view = data;
      this.lastEventId = frame.id || this.view.cursor?.token || null;
      return "view";
    }
    if (!this.view)
      throw new Error("replay view: a delta arrived before any view (reconnect without Last-Event-ID).");
    const id = frame.id || data.cursor?.token || null;
    if (id && id === this.lastEventId)
      return "duplicate";
    if (isOlderCursor(data.cursor?.runs, this.view.cursor?.runs))
      return "stale";
    this.view = applyDelta(this.view, data);
    this.lastEventId = id;
    return "delta";
  }
};
function unquoteEtag(etag) {
  const raw = String(etag || "").trim().replace(/^W\//, "");
  return raw.replace(/^"|"$/g, "");
}
function isOlderCursor(incoming, held) {
  if (!incoming || !held)
    return false;
  let behind = false;
  for (const [run, seq] of Object.entries(held)) {
    const next = incoming[run];
    if (typeof next !== "number") {
      if (seq > 0)
        behind = true;
      continue;
    }
    if (next > seq)
      return false;
    if (next < seq)
      behind = true;
  }
  for (const [run, seq] of Object.entries(incoming))
    if (!(run in held) && seq > 0)
      return false;
  return behind;
}
var REPLAY_SESSION_TURN_LIMIT = 200;

// dist/replay_view_projection.js
var str3 = (value) => typeof value === "string" ? value.trim() : typeof value === "number" ? String(value) : "";
var obj5 = (value) => value && typeof value === "object" && !Array.isArray(value) ? value : null;
var TERMINAL = /* @__PURE__ */ new Set(["completed", "failed", "cancelled"]);
var FILE_TOOLS = /* @__PURE__ */ new Set([
  "write_file",
  "create_file",
  "save_file",
  "edit_file",
  "update_file",
  "replace_in_file",
  "delete_file",
  "remove_file",
  "move_file",
  "rename_file",
  "copy_file"
]);
function replayInteractionWait(interaction) {
  const details = { ...interaction.details || {} };
  if (interaction.kind === "tool_approval") {
    details.kind = "tool_approval";
    details.tool_calls = Array.isArray(interaction.tool_calls) ? interaction.tool_calls : [];
  }
  const reason = interaction.kind === "ask_user" ? "user" : interaction.kind === "event" ? "event" : "tool_approval";
  const wait = {
    wait_key: interaction.wait_key,
    reason,
    details
  };
  if (interaction.prompt != null)
    wait.prompt = interaction.prompt;
  if (Array.isArray(interaction.choices))
    wait.choices = interaction.choices;
  if (typeof interaction.allow_free_text === "boolean")
    wait.allow_free_text = interaction.allow_free_text;
  return {
    runId: interaction.run_id,
    wait,
    ...interaction.step_id ? { stepId: interaction.step_id } : {},
    kind: interaction.kind,
    ...interaction.command ? { command: interaction.command } : {}
  };
}
function toolStatus(call, activity) {
  const s = str3(call.status || activity.status).toLowerCase();
  if (s === "completed")
    return "completed";
  if (s === "waiting")
    return "waiting";
  if (s === "running" || s === "started" || s === "pending")
    return "running";
  return "failed";
}
function callPolicy(call) {
  const decision = obj5(call.policy_decision);
  const kind = str3(decision?.decision);
  if (kind !== "auto_approved" && kind !== "denied")
    return void 0;
  const setBy = obj5(decision?.set_by);
  const who = str3(setBy?.user_id) || str3(setBy?.client);
  return {
    decision: kind,
    ...str3(call.decided_by) ? { source: str3(call.decided_by) } : {},
    ...str3(call.matched) ? { matched: str3(call.matched) } : {},
    ...typeof decision?.revision === "number" ? { revision: decision.revision } : {},
    ...who ? { setBy: who } : {},
    ...str3(decision?.set_at) ? { setAt: str3(decision?.set_at) } : {}
  };
}
function errorText(call, status) {
  if (typeof call.error === "string" && call.error.trim())
    return call.error.trim();
  const e = obj5(call.error);
  if (e)
    return str3(e.message) || str3(e.detail) || JSON.stringify(e);
  if (status === "denied")
    return "Denied";
  if (status === "cancelled")
    return "Cancelled";
  return void 0;
}
function replayToolActivities(activity) {
  const calls = Array.isArray(activity.tool_calls) ? activity.tool_calls : [];
  return calls.map((call, index) => {
    const status = toolStatus(call, activity);
    const served = str3(call.status || activity.status).toLowerCase();
    const policy = callPolicy(call);
    const error = status === "failed" ? errorText(call, served) : void 0;
    return {
      id: `${activity.id}:${str3(call.id) || index}`,
      runId: activity.run_id,
      name: str3(call.name) || "tool",
      ...call.arguments !== void 0 ? { arguments: call.arguments } : {},
      ...call.output !== void 0 ? { output: call.output } : {},
      status,
      ...status === "completed" ? { success: true } : status === "failed" ? { success: false } : {},
      ...error ? { error } : {},
      ...str3(activity.started_at) ? { startedAt: str3(activity.started_at) } : {},
      ...str3(activity.ended_at) ? { endedAt: str3(activity.ended_at) } : {},
      // A person decided (the view sets `outcome` only once every call of the batch is decided,
      // AbstractRuntime replay/view.py:1050-1051); a wait cut short by the run's end has none.
      ...activity.wait?.kind === "tool_approval" && activity.wait.outcome ? { approvalWait: true } : {},
      ...str3(call.id) ? { callId: str3(call.id) } : {},
      ...policy ? { policy } : {}
    };
  });
}
function toolActivityMessage(tool) {
  return {
    id: `tool:${tool.id}`,
    role: "system",
    kind: "tool_activity",
    title: "Tool activity",
    runId: tool.runId,
    toolActivity: tool,
    content: JSON.stringify({
      tool: tool.name,
      status: tool.status,
      arguments: tool.arguments,
      output: tool.output,
      error: tool.error
    }, null, 2),
    ts: tool.endedAt || tool.startedAt
  };
}
function policyLine(activity) {
  const decision = str3(activity.decision);
  if (decision !== "auto_approved" && decision !== "denied")
    return null;
  const policy = obj5(activity.policy);
  const setBy = obj5(policy?.set_by);
  const who = str3(setBy?.user_id) || str3(setBy?.client);
  const provenance = {
    decision,
    ...str3(activity.source) ? { source: str3(activity.source) } : {},
    ...typeof policy?.revision === "number" ? { revision: policy.revision } : {},
    ...who ? { setBy: who } : {},
    ...str3(policy?.set_at) ? { setAt: str3(policy?.set_at) } : {}
  };
  return {
    id: `policy:${activity.id}`,
    role: "system",
    kind: "tool_policy_decision",
    title: "Tool policy",
    runId: activity.run_id,
    content: toolPolicyDecisionText(provenance),
    ts: str3(activity.started_at) || void 0
  };
}
function replayStatistics(view) {
  const usage = obj5(view.usage) || {};
  const files2 = /* @__PURE__ */ new Set();
  let toolCalls = 0;
  let llm = 0;
  let start = Infinity;
  let end = -Infinity;
  for (const a of view.activities || []) {
    const s = Date.parse(str3(a.started_at));
    const e = Date.parse(str3(a.ended_at));
    if (Number.isFinite(s))
      start = Math.min(start, s);
    if (Number.isFinite(e))
      end = Math.max(end, e);
    if (a.kind === "llm")
      llm += 1;
    if (a.kind !== "tool")
      continue;
    for (const call of a.tool_calls || []) {
      toolCalls += 1;
      if (str3(call.status) !== "completed" || !FILE_TOOLS.has(str3(call.name)))
        continue;
      const args = obj5(call.arguments) || {};
      const path = str3(args.destination) || str3(args.destination_path) || str3(args.file_path) || str3(args.path) || str3(args.filename);
      if (path)
        files2.add(path);
    }
  }
  const num2 = (v) => typeof v === "number" && Number.isFinite(v) ? v : void 0;
  const out = {
    llmCalls: num2(usage.llm_calls) ?? llm,
    toolCalls,
    changedFiles: [...files2]
  };
  if (num2(usage.input_tokens) !== void 0)
    out.inputTokens = num2(usage.input_tokens);
  if (num2(usage.output_tokens) !== void 0)
    out.outputTokens = num2(usage.output_tokens);
  if (num2(usage.total_tokens) !== void 0)
    out.totalTokens = num2(usage.total_tokens);
  if (Number.isFinite(start) && Number.isFinite(end))
    out.durationMs = Math.max(0, end - start);
  return out;
}
function messageOf(m, statistics, artifacts) {
  const ts = Array.isArray(m.order) && typeof m.order[0] === "string" && m.order[0] ? m.order[0] : void 0;
  const level = str3(m.level).toLowerCase();
  const files2 = replayMessageArtifacts(m, artifacts);
  return {
    id: m.id,
    role: m.role,
    kind: m.kind,
    content: m.text,
    runId: m.run_id,
    ...m.source ? { source: m.source } : {},
    ...m.kind === "public_update" ? { publicUpdate: publicUpdate({ id: m.public_update_id || m.id, text: m.text, run_id: m.run_id, session_id: m.session_id, iteration: m.iteration, source_call_ids: m.source_call_ids }, m.run_id) || void 0 } : {},
    ...ts ? { ts } : {},
    ...m.role === "system" ? {
      title: "Workflow",
      level: level === "error" ? "error" : level === "warn" || level === "warning" ? "warn" : "info"
    } : {},
    ...Array.isArray(m.artifact_ids) && m.artifact_ids.length ? { artifactIds: [...m.artifact_ids] } : {},
    artifactRefs: files2.refs,
    artifactReferencesUnresolved: files2.unresolved,
    ...statistics ? { statistics } : {}
  };
}
function projectReplayView(view) {
  const root = view.root_run_id;
  const statistics = replayStatistics(view);
  const interaction = view.interaction ? replayInteractionWait(view.interaction) : null;
  const openQuestion = view.interaction ? `${view.interaction.run_id}:${view.interaction.step_id || ""}:question` : "";
  const finalOfRoot = (view.messages || []).find((m) => m.id === `${root}:final`);
  const statsOn = finalOfRoot ? finalOfRoot.repeats || finalOfRoot.id : "";
  const items = [];
  const artifactIndex = new Map((view.artifacts || []).map((entry) => [String(entry.id || ""), entry]));
  const repeatedFiles = /* @__PURE__ */ new Map();
  for (const message of view.messages || [])
    if (message.repeats)
      repeatedFiles.set(message.repeats, [
        ...repeatedFiles.get(message.repeats) || [],
        ...message.artifact_ids || []
      ]);
  for (const m of view.messages || []) {
    if (m.kind === "final" && m.repeats)
      continue;
    if (m.kind === "question" && m.id === openQuestion)
      continue;
    items.push({
      order: m.order,
      id: m.id,
      message: messageOf({
        ...m,
        artifact_ids: [
          .../* @__PURE__ */ new Set([
            ...m.artifact_ids || [],
            ...repeatedFiles.get(m.id) || []
          ])
        ]
      }, m.id === statsOn ? statistics : void 0, artifactIndex)
    });
  }
  const tools = [];
  const openLlmCalls = [];
  const endedLlmCalls = [];
  for (const a of view.activities || []) {
    if (a.kind === "tool") {
      const rows2 = replayToolActivities(a);
      tools.push(...rows2);
      rows2.forEach((tool, i) => items.push({
        order: [...a.order || [], i],
        id: `${a.id}:${i}`,
        message: toolActivityMessage(tool)
      }));
    } else if (a.kind === "tool_policy") {
      const line = policyLine(a);
      if (line)
        items.push({ order: a.order, id: a.id, message: line });
    } else if (a.kind === "llm") {
      for (const step of a.step_ids || [])
        (TERMINAL.has(a.status) ? endedLlmCalls : openLlmCalls).push(`${a.run_id}:${step}`);
    }
  }
  items.sort((x, y) => compareReplayOrder(x, y));
  const runStatus = new Map((view.runs || []).map((r) => [r.run_id, str3(r.status).toLowerCase()]));
  const status = str3(view.status).toLowerCase() || "unknown";
  return {
    messages: items.map((x) => x.message),
    tools,
    interaction: TERMINAL.has(status) ? null : interaction,
    status,
    displayStatus: str3(view.display_status),
    openLlmCalls,
    endedLlmCalls,
    runStatus,
    statistics
  };
}

// dist/workflow_runtime.js
var EMPTY = {
  messages: [],
  records: [],
  run: null,
  interaction: null,
  status: "idle",
  displayStatus: "",
  loading: false,
  historyLoading: false,
  error: null,
  connection: "idle",
  toolApprovalGranted: false,
  stop: null
};
function object(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : null;
}
function text2(value) {
  return typeof value === "string" ? value.trim() : value == null ? "" : typeof value === "number" || typeof value === "boolean" ? String(value) : "";
}
function array(value) {
  return Array.isArray(value) ? value : [];
}
function revisionConflict(error) {
  const e = object(error);
  return Boolean(e && (e.code === "revision_conflict" || e.reason_code === "revision_conflict" || e.status === 409 || e.name === "SessionToolPolicyConflict"));
}
function statusOf(run) {
  return text2(run?.status).toLowerCase() || "unknown";
}
function terminal(status) {
  return ["completed", "failed", "cancelled"].includes(status.toLowerCase());
}
function authError(error) {
  const value = object(error);
  const status = Number(value?.status ?? value?.statusCode);
  return status === 401 || status === 403;
}
function statusCode(error) {
  const value = object(error);
  return Number(value?.status ?? value?.statusCode);
}
function stablePayload(value) {
  const normalize = (item) => {
    if (Array.isArray(item))
      return item.map(normalize);
    const row2 = object(item);
    if (!row2)
      return item;
    const out = {};
    for (const key of Object.keys(row2).sort())
      out[key] = normalize(row2[key]);
    return out;
  };
  try {
    return JSON.stringify(normalize(value));
  } catch {
    return "[unserializable]";
  }
}
function messageText(value) {
  if (typeof value === "string")
    return value.trim();
  const obj6 = object(value);
  if (!obj6)
    return "";
  for (const key of ["answer", "response", "message", "text", "content", "output"]) {
    const candidate = obj6[key];
    if (typeof candidate === "string" && candidate.trim())
      return candidate.trim();
  }
  return "";
}
function displayValue(value) {
  const plain = messageText(value);
  if (plain)
    return plain;
  const obj6 = object(value);
  if (!obj6 && !Array.isArray(value))
    return "";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return "";
  }
}
function promptFromInput(input) {
  if (!input)
    return "";
  for (const key of ["prompt", "request", "task", "message", "query", "input"]) {
    const value = text2(input[key]);
    if (value)
      return value;
  }
  const context = object(input.context);
  for (const key of ["task", "message"]) {
    const value = text2(context?.[key]);
    if (value)
      return value;
  }
  const messages = array(context?.messages);
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = object(messages[index]);
    if (text2(message?.role).toLowerCase() !== "user")
      continue;
    const value = text2(message?.content);
    if (value)
      return value;
  }
  return "";
}
function waitFromRecord(record3) {
  const result = object(record3.result);
  return object(result?.wait);
}
function delegationWait(wait) {
  if (!wait)
    return false;
  return text2(wait.reason) === "subworkflow" || text2(wait.wait_key).startsWith("subworkflow:");
}
function sameWait(a, b) {
  return Boolean(a && a.runId === b.runId && text2(a.wait.wait_key) === text2(b.wait.wait_key));
}
function effect(record3) {
  return object(record3.effect) || {};
}
function runIdFrom(record3, fallback) {
  return text2(record3.run_id) || fallback;
}
function recordTimestamp(record3) {
  return text2(record3.ended_at) || text2(record3.started_at) || void 0;
}
function subRunIds(record3) {
  const out = /* @__PURE__ */ new Set();
  const add = (value) => {
    const id = text2(value);
    if (id)
      out.add(id);
  };
  const result = object(record3.result);
  add(result?.sub_run_id);
  add(result?.subRunId);
  add(result?.child_run_id);
  const eff = effect(record3);
  const payload = object(eff.payload);
  if (text2(eff.type) === "start_subworkflow") {
    add(payload?.sub_run_id);
    add(payload?.subRunId);
    add(payload?.child_run_id);
  }
  const wait = waitFromRecord(record3);
  const details = object(wait?.details);
  add(details?.sub_run_id);
  add(details?.subRunId);
  add(details?.child_run_id);
  const key = text2(wait?.wait_key);
  if (key.startsWith("subworkflow:"))
    add(key.slice("subworkflow:".length));
  return [...out];
}
var REPLAY_VIEW_PROBES = /* @__PURE__ */ new WeakMap();
var LOCAL_MESSAGE = /^(live|live-end|stream-unavailable):/;
function replayViewUnavailable(error) {
  return Boolean(error && typeof error === "object" && error.name === "ReplayViewUnavailableError");
}
function cursorDigest(token) {
  const raw = String(token || "");
  const at = raw.indexOf("~");
  return at < 0 ? "" : raw.slice(at + 1);
}
var emptyTurnCache = () => ({ sessionId: "", transport: null, order: [], created: /* @__PURE__ */ new Map(), turns: /* @__PURE__ */ new Map() });
var WorkflowSessionController = class {
  constructor(transport, options = {}) {
    this.transport = transport;
    this.options = options;
    this.snapshot = { ...EMPTY };
    this.subscribers = /* @__PURE__ */ new Set();
    this.controller = null;
    this.generation = 0;
    this.rootRunId = "";
    this.cursors = /* @__PURE__ */ new Map();
    this.seenRecords = /* @__PURE__ */ new Set();
    this.seenMessages = /* @__PURE__ */ new Set();
    this.watchedRuns = /* @__PURE__ */ new Set();
    this.childCatchUpAttempts = /* @__PURE__ */ new Map();
    this.runStates = /* @__PURE__ */ new Map();
    this.historicalRuns = /* @__PURE__ */ new Map();
    this.historicalRunFailures = /* @__PURE__ */ new Map();
    this.commandIds = /* @__PURE__ */ new Map();
    this.toolActivities = /* @__PURE__ */ new Map();
    this.historicalEvidence = /* @__PURE__ */ new Map();
    this.approvedWaits = /* @__PURE__ */ new Set();
    this.grantedToolWaits = /* @__PURE__ */ new Set();
    this.resolvedWaits = /* @__PURE__ */ new Set();
    this.approvalEpoch = 0;
    this.toolApprovalPolicy = null;
    this.toolApprovalSuspended = false;
    this.toolApprovalStopped = false;
    this.displayStatusAt = -Infinity;
    this.stopRequested = false;
    this.stopFollowing = false;
    this.openLlmSteps = /* @__PURE__ */ new Set();
    this.forcedStop = null;
    this.liveReplies = /* @__PURE__ */ new Map();
    this.closedLiveCalls = /* @__PURE__ */ new Set();
    this.shownLiveCalls = /* @__PURE__ */ new Set();
    this.liveDirty = /* @__PURE__ */ new Set();
    this.liveRenderTimer = null;
    this.lastLiveRender = -Infinity;
    this.sessionToolPolicy = null;
    this.sessionPolicyUnavailableReason = "";
    this.sessionPolicyState = null;
    this.sessionPolicyClamped = [];
    this.toolPolicyByCall = /* @__PURE__ */ new Map();
    this.source = null;
    this.viewFold = null;
    this.viewRun = null;
    this.viewDigest = "";
    this.viewAssistantIds = /* @__PURE__ */ new Set();
    this.viewTerminalRuns = /* @__PURE__ */ new Set();
    this.viewStreamEnded = false;
    this.viewEarlier = { messages: [], tools: [] };
    this.viewTurnCache = emptyTurnCache();
    const interval = options.liveRenderIntervalMs ?? 60;
    if (typeof interval !== "number" || !Number.isFinite(interval) || interval < 0)
      throw new Error(`liveRenderIntervalMs must be a non-negative number of milliseconds, got ${JSON.stringify(options.liveRenderIntervalMs)}`);
    this.liveRenderIntervalMs = interval;
    this.sessionToolPolicy = options.sessionToolPolicy || null;
    if (!this.sessionToolPolicy)
      this.sessionPolicyUnavailableReason = text2(options.sessionToolPolicyUnavailableReason);
    this.snapshot = this.withSessionPolicy({ ...EMPTY });
  }
  // ---- Session tool policy (contract v1) --------------------------------
  /** `"gateway"` only for an injected client whose capability is `supported === true`. */
  sessionPolicyMode() {
    if (this.sessionToolPolicy?.supported === true)
      return "gateway";
    return !this.sessionToolPolicy && this.sessionPolicyUnavailableReason ? "unavailable" : "local-fallback";
  }
  /** Mode, reason, `clamped` and stored policy: what `presentInteraction` reads (never a host prop). */
  sessionPolicyStatus() {
    const mode = this.sessionPolicyMode();
    return { mode, ...mode === "unavailable" ? { reason: this.sessionPolicyUnavailableReason } : {}, clamped: this.sessionPolicyClamped, policy: this.sessionPolicyState };
  }
  /**
   * Inject (or remove) the session policy client, e.g. once discovery has answered or the
   * session changed. `null` with a `reason` means the capability read FAILED (mode
   * `"unavailable"`); `null` alone means the gateway does not offer it (`"local-fallback"`).
   */
  setSessionToolPolicyClient(client, options = {}) {
    const reason = client ? "" : text2(options.reason);
    if (client === this.sessionToolPolicy && reason === this.sessionPolicyUnavailableReason)
      return;
    const sameSession = Boolean(client && this.sessionToolPolicy && client.sessionId === this.sessionToolPolicy.sessionId);
    this.sessionToolPolicy = client;
    this.sessionPolicyUnavailableReason = reason;
    if (!sameSession) {
      this.sessionPolicyState = null;
      this.sessionPolicyClamped = [];
    }
    this.set({ ...this.snapshot });
  }
  gatewayPolicy() {
    const client = this.sessionToolPolicy;
    if (this.sessionPolicyMode() === "unavailable")
      throw new Error(`${this.sessionPolicyUnavailableReason} Allow once still works.`);
    if (!client || client.supported !== true)
      throw new Error("This gateway cannot store chat tool policies (session_tool_policy is not supported).");
    return client;
  }
  adoptSessionPolicy(policy) {
    this.sessionPolicyState = policy;
    this.sessionPolicyClamped = Array.isArray(policy?.clamped) ? policy.clamped.filter((row2) => row2 && typeof row2 === "object") : [];
    this.set({ ...this.snapshot });
    this.options.onSessionPolicy?.(policy, this.sessionPolicyClamped);
  }
  /** Read the conversation's stored policy (gateway mode). */
  async loadSessionPolicy() {
    const policy = await this.gatewayPolicy().get();
    this.adoptSessionPolicy(policy);
    return policy;
  }
  /**
   * The grant is read from the run tree's ROOT session (contract §4.2): the client must be
   * bound to the root run's `session_id`, never a child's. Fails loudly otherwise.
   */
  requireRootSession(client) {
    const root = text2(this.snapshot.run?.session_id) || text2(this.runStates.get(this.rootRunId)?.session_id);
    if (!root)
      throw new Error("This chat's session is not known yet: the policy is written to the root run's session.");
    if (root !== client.sessionId)
      throw new Error(`The tool policy client is bound to session ${client.sessionId}, but this chat's root run belongs to session ${root}: the policy is written to the root run's session.`);
  }
  /** The revision a guarded write uses: the adopted policy's, else read first (the policy's, or the
   * client's latest answer revision, which also covers "no policy yet"). */
  async currentRevision(client) {
    if (typeof this.sessionPolicyState?.revision === "number")
      return this.sessionPolicyState.revision;
    const policy = await this.loadSessionPolicy();
    if (typeof policy?.revision === "number")
      return policy.revision;
    const latest = client.revision;
    return typeof latest === "number" ? latest : void 0;
  }
  /** A failed policy write, labeled: a conflict asks to re-read (and re-reads); the client's own
   * refusal (e.g. ui-kit's `SessionToolPolicyRevisionError`) says the policy was not changed. */
  async policyWriteError(error) {
    if (revisionConflict(error)) {
      await this.loadSessionPolicy().catch(() => null);
      return new Error("Someone changed this chat's policy; re-read it before deciding again (it was refreshed).");
    }
    const message = error instanceof Error ? error.message : String(error);
    return new Error(`This chat's policy was not changed: ${message}`);
  }
  /** The shown approval must still be the current one before any policy is written. */
  requireTarget(target2) {
    const interaction = this.requireInteraction();
    if (terminal(this.snapshot.status))
      throw new Error("This run has already ended.");
    if (interaction.runId !== target2.runId || text2(interaction.wait.wait_key) !== target2.waitKey || target2.stepId !== void 0 && interaction.stepId !== target2.stepId)
      throw new Error("This approval request has changed. Review the current request before deciding.");
    if (!this.isToolApproval(interaction))
      throw new Error("This is not a tool approval request.");
    return interaction;
  }
  /**
   * Write the policy FIRST, then answer the shown wait (contract §4: the policy never
   * answers existing waits). `ask` (the person's explicit Ask tools) travels on every
   * write, so a broad approve never overrides them.
   */
  async writeThenAnswer(target2, body, approved, ask = []) {
    this.requireTarget(target2);
    const client = this.gatewayPolicy();
    this.requireRootSession(client);
    const names = [...new Set(ask.map((name) => text2(name)).filter(Boolean))];
    let guard = {};
    if (body.deny) {
      const revision = await this.currentRevision(client);
      if (typeof revision !== "number")
        throw new Error("This chat's policy was not changed: the gateway did not return a policy revision to guard the deny with.");
      guard = { if_revision: revision };
    }
    let policy;
    try {
      policy = await client.merge({ ...body, ...names.length ? { ask: names } : {}, ...guard, client: body.client || "panel-chat" });
    } catch (error) {
      throw await this.policyWriteError(error);
    }
    if (this.sessionToolPolicy === client)
      this.adoptSessionPolicy(policy);
    try {
      await this.approve(approved, target2);
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error);
      throw new Error(`This chat's tool policy was saved, but this request was not answered: ${reason} The policy does not answer requests that were already waiting.`);
    }
    return policy;
  }
  /**
   * "Allow for this chat". Gateway mode: merge `{approve:{all:true}}` into the
   * conversation's policy, then answer the shown wait `{approved:true}`; later
   * calls of every run of the conversation run without a wait. Local fallback
   * (no supported client): the existing client-side grant
   * (`allowAllToolsForRun`: this controller, until the run ends). Returns the
   * stored policy, or null in the fallback.
   */
  async approveAllForSession(target2, options = {}) {
    const mode = this.sessionPolicyMode();
    if (mode === "unavailable")
      throw new Error(`${this.sessionPolicyUnavailableReason} Allow once still works.`);
    if (mode !== "gateway") {
      await this.allowAllToolsForRun(target2);
      return null;
    }
    return this.writeThenAnswer(target2, { approve: { all: true, ...typeof options.maxRiskRank === "number" ? { max_risk_rank: options.maxRiskRank } : {} } }, true, options.ask);
  }
  /** "Allow all <toolset> tools for this chat": merge `{approve:{kinds:[kind]}}`, then answer `{approved:true}`. Gateway mode only. */
  approveKindForSession(target2, kind, options = {}) {
    return this.writeThenAnswer(target2, { approve: { kinds: [kind] } }, true, options.ask);
  }
  /** Deny a toolset for the chat, then answer `{approved:false}`. Gateway mode only; no panel control (hosts expose it). */
  denyKindForSession(target2, kind, options = {}) {
    return this.writeThenAnswer(target2, { deny: { kinds: [kind] } }, false, options.ask);
  }
  /** Deny one tool for the chat, then answer `{approved:false}`. Gateway mode only; no panel control (hosts expose it). */
  denyToolForSession(target2, tool, options = {}) {
    return this.writeThenAnswer(target2, { deny: { tools: [tool] } }, false, options.ask);
  }
  /** Reset: gateway mode deletes the conversation's policy; the fallback revokes the local grant. */
  /** Narrowing an approve (undo) is a reset (DELETE), never a merge: a merge only adds. */
  async resetSessionPolicy() {
    if (this.sessionPolicyMode() === "unavailable")
      throw new Error(`${this.sessionPolicyUnavailableReason}`);
    if (this.sessionPolicyMode() !== "gateway") {
      this.revokeToolApproval();
      return;
    }
    const client = this.gatewayPolicy();
    this.requireRootSession(client);
    const revision = await this.currentRevision(client);
    if (typeof revision !== "number")
      throw new Error("This chat's policy was not reset: the gateway did not return a policy revision to guard the reset with.");
    try {
      await client.reset(revision);
    } catch (error) {
      throw await this.policyWriteError(error);
    }
    this.adoptSessionPolicy(null);
  }
  withSessionPolicy(snapshot) {
    const mode = this.sessionPolicyMode();
    const { sessionPolicyReason: _previous, ...rest } = snapshot;
    void _previous;
    return { ...rest, sessionPolicyMode: mode, ...mode === "unavailable" ? { sessionPolicyReason: this.sessionPolicyUnavailableReason } : {}, sessionPolicy: this.sessionPolicyState, sessionPolicyClamped: this.sessionPolicyClamped };
  }
  withSource(snapshot) {
    const { source: _source, sourceReason: _reason, ...rest } = snapshot;
    void _source;
    void _reason;
    if (!this.source)
      return rest;
    return { ...rest, source: this.source.source, ...this.source.reason ? { sourceReason: this.source.reason } : {} };
  }
  subscribe(listener) {
    this.subscribers.add(listener);
    return () => this.subscribers.delete(listener);
  }
  getSnapshot() {
    return this.snapshot;
  }
  reset() {
    this.toolApprovalSuspended = false;
    this.toolApprovalStopped = false;
    this.approvalEpoch += 1;
    this.displayStatusAt = -Infinity;
    this.stopRequested = false;
    this.stopFollowing = false;
    this.openLlmSteps.clear();
    this.forcedStop = null;
    this.generation += 1;
    this.controller?.abort();
    this.controller = null;
    this.rootRunId = "";
    this.cursors.clear();
    this.seenRecords.clear();
    this.seenMessages.clear();
    this.watchedRuns.clear();
    this.childCatchUpAttempts.clear();
    this.runStates.clear();
    this.historicalRuns.clear();
    this.historicalRunFailures.clear();
    this.commandIds.clear();
    this.toolActivities.clear();
    this.toolPolicyByCall.clear();
    this.historicalEvidence.clear();
    this.approvedWaits.clear();
    this.grantedToolWaits.clear();
    this.resolvedWaits.clear();
    this.liveReplies.clear();
    this.closedLiveCalls.clear();
    this.shownLiveCalls.clear();
    this.liveDirty.clear();
    this.lastLiveRender = -Infinity;
    if (this.liveRenderTimer) {
      clearTimeout(this.liveRenderTimer);
      this.liveRenderTimer = null;
    }
    this.source = null;
    this.viewFold = null;
    this.viewRun = null;
    this.viewDigest = "";
    this.viewAssistantIds.clear();
    this.viewTerminalRuns.clear();
    this.viewStreamEnded = false;
    this.viewEarlier = { messages: [], tools: [] };
    this.set({ ...EMPTY });
  }
  dispose() {
    this.reset();
    this.viewTurnCache = emptyTurnCache();
    this.subscribers.clear();
  }
  async load(runId) {
    const id = text2(runId);
    this.reset();
    if (!id)
      return;
    const generation = ++this.generation;
    const abort = new AbortController();
    this.controller = abort;
    this.rootRunId = id;
    this.set({ ...this.snapshot, loading: true, historyLoading: true, status: "loading", error: null, connection: "connecting" });
    try {
      if (await this.loadView(id, generation, abort.signal))
        return;
      if (!this.live(generation))
        return;
      this.set({ ...this.snapshot });
      const [run, history] = await Promise.all([this.transport.getRun(id, abort.signal), this.transport.getHistory(id, abort.signal)]);
      if (!this.live(generation))
        return;
      const liveRun = object(run);
      const currentWait = object(liveRun?.waiting);
      const runStatus = statusOf(liveRun);
      await this.ingestHistory(history, id, generation);
      if (!this.live(generation))
        return;
      this.set({
        ...this.snapshot,
        run: liveRun,
        status: runStatus,
        loading: false,
        historyLoading: false,
        ...currentWait && !terminal(runStatus) ? { interaction: this.interactionWith({ runId: id, wait: currentWait }) } : {}
      });
      if (liveRun)
        this.updateRunState(id, liveRun);
      if (currentWait) {
        for (const child of subRunIds({ result: { wait: currentWait } }))
          if (child !== id)
            void this.catchUpAndWatch(child, generation);
      }
      await this.catchUpAndWatch(id, generation);
      void this.pollRootLifecycle(id, generation);
    } catch (error) {
      if (!abort.signal.aborted && this.live(generation))
        this.fail(error);
    }
  }
  async sendCommand(type, payload = {}) {
    if (type === "cancel") {
      this.toolApprovalStopped = true;
      this.revokeToolApproval();
      this.stopRequested = true;
      this.recomputeStop();
    }
    const resumeWaitKey = text2(payload.wait_key);
    const runId = type === "resume" ? resumeWaitKey ? this.interactionRunId() || this.rootRunId : this.rootRunId : type === "emit_event" ? this.interactionRunId() || this.rootRunId : this.rootRunId;
    if (!runId)
      throw new Error("No workflow run is loaded");
    const occurrence = type === "resume" && resumeWaitKey ? this.snapshot.interaction?.stepId || "" : "";
    const stable = `${runId}\0${type}\0${occurrence}\0${stablePayload(payload)}`;
    let commandId = this.commandIds.get(stable);
    if (!commandId) {
      commandId = this.newCommandId();
      this.commandIds.set(stable, commandId);
    }
    const generation = this.generation;
    const signal = this.controller?.signal;
    try {
      const response = await this.transport.submitCommand({ command_id: commandId, run_id: runId, type, payload, ...this.options.clientId ? { client_id: this.options.clientId } : {} }, signal);
      if (!this.live(generation))
        return response;
      const body = object(response);
      if (body && body.accepted === false) {
        if (type === "cancel") {
          this.stopRequested = false;
          this.recomputeStop();
        }
        throw new Error(text2(body.detail) || "Gateway did not accept the command");
      }
      this.commandIds.delete(stable);
      if (this.viewFold) {
        if (["pause", "resume", "cancel"].includes(type))
          void this.refreshViewRun(generation);
      } else if (runId === this.rootRunId && ["pause", "resume", "cancel"].includes(type))
        void this.refreshRunState(runId, generation);
      return response;
    } catch (error) {
      if (this.live(generation))
        this.fail(error, false);
      throw error;
    }
  }
  /** Answer the current question. With `target`, refuses when the question shown is no longer the current one. */
  resume(response, target2) {
    const interaction = this.requireInteraction();
    if (target2 && (interaction.runId !== target2.runId || text2(interaction.wait.wait_key) !== target2.waitKey || target2.stepId !== void 0 && interaction.stepId !== target2.stepId))
      throw new Error("This question has changed. Review the current question before answering.");
    return this.sendCommand("resume", { wait_key: text2(interaction.wait.wait_key), payload: { response } });
  }
  /**
   * Answer an event wait served by the replay view with its own resume command (the view's
   * `answer_payload` for an event is the payload itself). With `target`, refuses when the wait
   * shown is no longer the current one.
   */
  answerEvent(payload, target2) {
    const interaction = this.requireInteraction();
    if (target2 && (interaction.runId !== target2.runId || text2(interaction.wait.wait_key) !== target2.waitKey || target2.stepId !== void 0 && interaction.stepId !== target2.stepId))
      throw new Error("This wait has changed. Review the current one before answering.");
    if (!interaction.command)
      throw new Error("This wait has no resume command (it does not come from the replay view): send the event instead.");
    return this.sendCommand("resume", { wait_key: text2(interaction.wait.wait_key), payload });
  }
  approve(approved, target2) {
    const interaction = this.requireInteraction();
    if (terminal(this.snapshot.status))
      throw new Error("This run has already ended.");
    if (target2 && (interaction.runId !== target2.runId || text2(interaction.wait.wait_key) !== target2.waitKey || target2.stepId !== void 0 && interaction.stepId !== target2.stepId))
      throw new Error("This approval request has changed. Review the current request before deciding.");
    if (approved && this.toolApprovalPolicy && !this.toolCallsMatch(interaction, this.toolApprovalPolicy.enabledTools))
      throw new Error("This request includes an unavailable or unselected tool. It cannot be authorized. Deny this request or stop the run and change Tools settings.");
    const generation = this.generation;
    return this.sendCommand("resume", { wait_key: text2(interaction.wait.wait_key), payload: { approved: Boolean(approved) } }).then((result) => {
      if (!this.live(generation))
        return result;
      const key = this.occurrenceKey(interaction);
      this.approvedWaits.add(key);
      if (approved && this.isToolApproval(interaction) && !this.grantedToolWaits.has(key)) {
        this.grantedToolWaits.add(key);
        this.set({ ...this.snapshot });
      }
      return result;
    });
  }
  async approveWithPolicyChange(target2, onApproved) {
    const generation = this.generation;
    const epoch = this.approvalEpoch;
    if (!this.isToolApproval(this.requireInteraction()))
      throw new Error("This is not a tool approval request.");
    await this.approve(true, target2);
    if (!this.live(generation) || epoch !== this.approvalEpoch || this.toolApprovalStopped || terminal(this.snapshot.status))
      return;
    onApproved();
  }
  async allowAllToolsForRun(target2) {
    const generation = this.generation;
    const epoch = this.approvalEpoch;
    const interaction = this.requireInteraction();
    if (!this.isToolApproval(interaction))
      throw new Error("This is not a tool approval request.");
    await this.approve(true, target2);
    if (!this.live(generation) || epoch !== this.approvalEpoch || terminal(this.snapshot.status))
      return;
    this.approvedWaits.add(`${target2.runId}:${target2.waitKey}${interaction.stepId ? `:${interaction.stepId}` : ""}`);
    this.set({ ...this.snapshot, autoApproveTools: true });
  }
  revokeToolApproval() {
    this.approvalEpoch += 1;
    this.toolApprovalSuspended = true;
    this.set({ ...this.snapshot, autoApproveTools: false });
  }
  /** Host-owned persistent permissions, intersected with current availability.
   * This is configuration, not a blanket grant and cannot enable a tool. */
  setToolApprovalPolicy(policy) {
    if (stablePayload(policy) === stablePayload(this.toolApprovalPolicy))
      return;
    this.approvalEpoch += 1;
    this.toolApprovalSuspended = false;
    this.toolApprovalPolicy = policy ? { enabledTools: [...policy.enabledTools], autoApproveTools: [...policy.autoApproveTools] } : null;
    this.set({ ...this.snapshot });
  }
  occurrenceKey(interaction) {
    return `${interaction.runId}:${text2(interaction.wait.wait_key)}${interaction.stepId ? `:${interaction.stepId}` : ""}`;
  }
  /**
   * The interaction to show once `candidate` is observed. A wait a person can
   * answer (tool approval, question, event) replaces what is shown: the latest
   * evidence wins, as before. A delegation wait (`subworkflow:<child>`: the
   * root parked on its agent loop) never displaces a person-facing wait — the
   * root's wait says "the child is working", the child's says what must be
   * decided. Every client rebuilds the same gate from the same durable state
   * whichever order it reads it in (2026-09-29: a fresh client showed
   * "Running a tool" for a turn parked on the child's write_file approval).
   * Same run and key without a step id (a run snapshot) keeps the occurrence
   * the ledger record established.
   */
  interactionWith(candidate) {
    const current = this.snapshot.interaction;
    if (current && delegationWait(candidate.wait) && !delegationWait(current.wait))
      return current;
    if (current && sameWait(current, candidate) && candidate.stepId === void 0 && current.stepId !== void 0)
      return { ...candidate, stepId: current.stepId };
    return candidate;
  }
  /**
   * A run's durable wait (`GET /runs/{id}.waiting`) is the gate a client that
   * never received the ledger record must still show: the bundle's tail
   * window can drop it, a stream can reconnect past it. Ledger records keep
   * their precedence (`foldRecord`); this fills what durable state proves and
   * never re-opens a wait the ledger already resolved.
   */
  adoptDurableWait(runId, run) {
    const wait = object(run.waiting);
    if (!wait || statusOf(run) !== "waiting" || delegationWait(wait) || terminal(this.snapshot.status))
      return;
    if (this.resolvedWaits.has(`${runId}:${text2(wait.wait_key)}`))
      return;
    const next = this.interactionWith({ runId, wait });
    const current = this.snapshot.interaction;
    if (current && sameWait(current, next) && current.stepId === next.stepId)
      return;
    this.set({ ...this.snapshot, interaction: next });
  }
  /** Whether the automatic approver answers `interaction` in `snapshot`
   * (ignoring its own once-per-occurrence dedupe). Single source for both
   * the approver and the presentation flag, so they cannot disagree. */
  coveredByStandingPermission(snapshot, interaction) {
    if (snapshot.loading || this.toolApprovalStopped || this.toolApprovalSuspended || !this.toolApprovalPolicy && !snapshot.autoApproveTools || terminal(snapshot.status) || snapshot.run?.paused === true || snapshot.status === "paused" || !interaction || !this.isToolApproval(interaction))
      return false;
    if (this.toolApprovalPolicy && (!this.toolCallsMatch(interaction, this.toolApprovalPolicy.enabledTools) || !this.toolCallsMatch(interaction, this.toolApprovalPolicy.autoApproveTools)))
      return false;
    return Boolean(text2(interaction.wait.wait_key));
  }
  /** Presentation of a controller snapshot: a granted tool approval shows
   * its calls as running, never as "need approval". Raw statuses stay in
   * `toolActivities`, so a failed automatic approval reverts exactly. */
  present(next) {
    const interaction = next.interaction;
    const key = interaction ? this.occurrenceKey(interaction) : "";
    const granted = Boolean(interaction && this.isToolApproval(interaction) && (this.grantedToolWaits.has(key) || !this.approvedWaits.has(key) && this.coveredByStandingPermission({ ...next, loading: false }, interaction)));
    if (!granted && !this.snapshot.toolApprovalGranted && !next.toolApprovalGranted)
      return next.toolApprovalGranted === false ? next : { ...next, toolApprovalGranted: false };
    let changed = false;
    const messages = next.messages.map((message) => {
      const tool = message.toolActivity;
      if (!tool || this.toolActivities.get(tool.id)?.status !== "waiting")
        return message;
      const status = granted && tool.runId === interaction?.runId ? "running" : "waiting";
      if (tool.status === status)
        return message;
      changed = true;
      return this.toolMessage({ ...tool, status });
    });
    return { ...next, toolApprovalGranted: granted, ...changed ? { messages } : {} };
  }
  toolCallsMatch(interaction, names) {
    const calls = array(object(interaction.wait.details)?.tool_calls);
    return calls.length > 0 && calls.every((call) => {
      const name = text2(object(call)?.name);
      return Boolean(name) && names.includes(name);
    });
  }
  isToolApproval(interaction) {
    const details = object(interaction.wait.details);
    return details?.mode === "approval_required" || details?.kind === "tool_approval";
  }
  autoApproveCurrentWait() {
    const interaction = this.snapshot.interaction;
    if (!this.coveredByStandingPermission(this.snapshot, interaction))
      return;
    const target2 = { runId: interaction.runId, waitKey: text2(interaction.wait.wait_key), stepId: interaction.stepId };
    const key = this.occurrenceKey(interaction);
    if (this.approvedWaits.has(key))
      return;
    this.approvedWaits.add(key);
    this.grantedToolWaits.add(key);
    const generation = this.generation;
    const epoch = this.approvalEpoch;
    void this.approve(true, target2).catch((error) => {
      if (!this.live(generation))
        return;
      this.grantedToolWaits.delete(key);
      if (epoch !== this.approvalEpoch) {
        this.set({ ...this.snapshot });
        return;
      }
      this.toolApprovalSuspended = true;
      this.set({ ...this.snapshot, autoApproveTools: false });
      this.fail(error, false);
    });
  }
  emitEvent(payload) {
    return this.sendCommand("emit_event", payload);
  }
  cancel() {
    return this.sendCommand("cancel", {});
  }
  requireInteraction() {
    if (!this.snapshot.interaction)
      throw new Error("This workflow is not waiting for input");
    if (!text2(this.snapshot.interaction.wait.wait_key))
      throw new Error("The workflow wait has no wait_key");
    return this.snapshot.interaction;
  }
  interactionRunId() {
    return this.snapshot.interaction?.runId || "";
  }
  live(generation) {
    return generation === this.generation && !this.controller?.signal.aborted;
  }
  set(snapshot) {
    this.snapshot = this.present(this.withSource(this.withSessionPolicy(snapshot)));
    for (const listener of this.subscribers)
      listener();
    this.autoApproveCurrentWait();
  }
  // ---- Replay view mode (WorkflowTransport.replayView) ----------------------------------
  /**
   * Render from the gateway's replay view when the transport offers it and the gateway serves
   * it. Returns false (and labels the snapshot `ledger_fold` with the reason) otherwise: no
   * transport, a gateway that advertises no view, or one that answered it has no such route
   * (remembered per transport). Any other failure is a load failure, never a silent fallback.
   */
  async loadView(id, generation, signal) {
    const rv = this.transport.replayView;
    const fallback = (reason) => {
      if (this.live(generation))
        this.source = { source: "ledger_fold", reason };
      return false;
    };
    if (!rv)
      return fallback("this app's transport does not read the replay view");
    if (rv.advertised === false)
      return fallback("the gateway does not advertise the replay view");
    const known = REPLAY_VIEW_PROBES.get(rv);
    if (typeof known === "string")
      return fallback(known);
    let read2;
    let run;
    try {
      [read2, run] = await Promise.all([rv.getView(id, { signal }), this.transport.getRun(id, signal)]);
    } catch (error) {
      if (!replayViewUnavailable(error))
        throw error;
      const reason = error instanceof Error ? error.message : "the gateway does not serve the replay view";
      REPLAY_VIEW_PROBES.set(rv, reason);
      return fallback(reason);
    }
    REPLAY_VIEW_PROBES.set(rv, true);
    if (!this.live(generation))
      return true;
    if (read2.notModified)
      throw new Error("The gateway answered 304 to a replay view read without If-None-Match.");
    this.source = { source: "replay_view" };
    this.viewRun = object(run);
    const fold = new ReplayViewFold();
    fold.adopt(read2.view, read2.etag);
    this.viewFold = fold;
    this.viewDigest = cursorDigest(fold.lastEventId);
    this.adoptView();
    void this.followView(id, generation);
    void this.followLiveReplies(id, generation);
    await this.loadEarlierTurns(id, text2(read2.view.session_id), generation, signal);
    if (this.live(generation))
      this.set({ ...this.snapshot, historyLoading: false });
    return true;
  }
  /** Read the views of the conversation's turns before `runId` and keep their messages. */
  async loadEarlierTurns(runId, sessionId, generation, signal) {
    const rv = this.transport.replayView;
    if (!rv || !sessionId)
      return;
    const note = (id, content) => ({ id, role: "system", level: "warn", title: "History", content });
    if (!rv.listSessionTurns) {
      this.viewEarlier = { messages: [note(`history:${sessionId}:unlisted`, "Earlier turns of this conversation are not shown: this app's replay view transport cannot list the conversation's turns (createReplayViewTransport provides listSessionTurns).")], tools: [] };
      this.adoptView();
      return;
    }
    const cache = this.viewTurnCache.sessionId === sessionId && this.viewTurnCache.transport === rv ? this.viewTurnCache : { ...emptyTurnCache(), sessionId, transport: rv };
    this.viewTurnCache = cache;
    const show = (ids, extra = /* @__PURE__ */ new Map(), head2 = []) => {
      const turns = ids.map((id) => cache.turns.get(id) || extra.get(id)).filter((turn) => Boolean(turn));
      this.viewEarlier = { messages: [...head2, ...turns.flatMap((turn) => turn.messages)], tools: turns.flatMap((turn) => turn.tools) };
    };
    const knownAt = cache.order.indexOf(runId);
    let earlier;
    let over = false;
    if (knownAt >= 0 && cache.order.slice(0, knownAt).every((id) => cache.turns.has(id))) {
      earlier = cache.order.slice(0, knownAt);
    } else {
      const at = text2(this.viewRun?.created_at);
      const older = at ? cache.order.filter((id) => cache.turns.has(id) && cache.created.has(id) && cache.created.get(id) < at) : [];
      if (older.length) {
        show(older);
        this.adoptView();
      }
      let turns;
      try {
        turns = await rv.listSessionTurns(runId, { signal });
      } catch (error) {
        if (!this.live(generation))
          return;
        if (authError(error)) {
          this.viewTurnCache = emptyTurnCache();
          throw error;
        }
        show(older, /* @__PURE__ */ new Map(), [note(`history:${sessionId}:unlisted`, `Earlier turns of this conversation could not be listed: ${error instanceof Error ? error.message : String(error)}`)]);
        this.adoptView();
        return;
      }
      if (!this.live(generation))
        return;
      over = turns.length > REPLAY_SESSION_TURN_LIMIT;
      if (over)
        turns = turns.slice(turns.length - REPLAY_SESSION_TURN_LIMIT);
      for (const turn of turns)
        if (turn.created_at)
          cache.created.set(turn.run_id, turn.created_at);
      cache.order = turns.map((turn) => turn.run_id);
      const listedAt = cache.order.indexOf(runId);
      earlier = listedAt >= 0 ? cache.order.slice(0, listedAt) : cache.order.filter((id) => id !== runId);
    }
    const notes = /* @__PURE__ */ new Map();
    const missing = earlier.filter((id) => !cache.turns.has(id));
    let next = 0;
    const worker = async () => {
      while (this.live(generation)) {
        const turnId = missing[next++];
        if (!turnId)
          return;
        try {
          const got = await rv.getView(turnId, { signal });
          if (got.notModified || !got.view)
            throw new Error("the gateway answered without a view");
          const p = projectReplayView(got.view);
          if (terminal(p.status))
            cache.turns.set(turnId, { messages: p.messages, tools: p.tools });
          else
            notes.set(turnId, { messages: [...p.messages, note(`history:${turnId}:open`, `This earlier turn is still ${p.status || "running"}; open it to follow or answer it.`)], tools: p.tools });
        } catch (error) {
          if (!this.live(generation))
            return;
          if (authError(error)) {
            this.viewTurnCache = emptyTurnCache();
            throw error;
          }
          notes.set(turnId, { messages: [note(`history:${turnId}:unavailable`, `An earlier turn could not be restored (${turnId.slice(0, 8)}): ${error instanceof Error ? error.message : String(error)}`)], tools: [] });
        }
      }
    };
    await Promise.all(Array.from({ length: Math.min(4, missing.length) }, () => worker()));
    if (!this.live(generation))
      return;
    const head = over ? [note(`history:${sessionId}:limit`, `Only the last ${REPLAY_SESSION_TURN_LIMIT} turns of this conversation are shown.`)] : [];
    show(earlier, notes, head);
    this.adoptView();
  }
  /** Project the folded view into the snapshot (the ONE place view mode writes conversation state). */
  adoptView() {
    const view = this.viewFold?.view;
    if (!view)
      return;
    const p = projectReplayView(view);
    if (terminal(p.status) && view.session_id && this.viewTurnCache.sessionId === view.session_id)
      this.viewTurnCache.turns.set(view.root_run_id, { messages: p.messages, tools: p.tools });
    this.toolActivities = new Map([...this.viewEarlier.tools, ...p.tools].map((tool) => [tool.id, tool]));
    for (const key of p.endedLlmCalls)
      if (!this.closedLiveCalls.has(key))
        this.closeLiveReply(key);
    for (const m of view.messages || []) {
      if (m.role !== "assistant" || this.viewAssistantIds.has(m.id))
        continue;
      this.viewAssistantIds.add(m.id);
      this.closeLiveRepliesOfRun(m.run_id);
    }
    for (const [runId, status] of p.runStatus) {
      if (!terminal(status) || this.viewTerminalRuns.has(runId))
        continue;
      this.viewTerminalRuns.add(runId);
      this.endLiveRepliesOfRun(runId, status);
    }
    this.openLlmSteps = new Set(p.openLlmCalls);
    const done = terminal(p.status);
    const local = this.snapshot.messages.filter((message) => LOCAL_MESSAGE.test(String(message.id || "")));
    const run = { ...this.viewRun || {}, run_id: view.root_run_id, status: p.status, ...view.session_id ? { session_id: view.session_id } : {} };
    let interaction = p.interaction;
    const current = this.snapshot.interaction;
    if (interaction && current && current.runId === interaction.runId && text2(current.wait.wait_key) === text2(interaction.wait.wait_key) && current.stepId !== interaction.stepId && (current.stepId === void 0 || interaction.stepId === void 0)) {
      const { stepId: _drop, ...rest } = interaction;
      void _drop;
      interaction = current.stepId === void 0 ? rest : { ...rest, stepId: current.stepId };
    }
    this.set({
      ...this.snapshot,
      view,
      run,
      status: p.status,
      displayStatus: done ? "" : p.displayStatus,
      messages: [...this.viewEarlier.messages, ...p.messages, ...local],
      interaction,
      loading: false,
      ...done ? { autoApproveTools: false } : {}
    });
    if (this.stopRequested || this.forcedStop)
      this.recomputeStop();
    const digest = cursorDigest(this.viewFold?.lastEventId);
    if (digest !== this.viewDigest && Object.keys(view.cursor?.runs || {}).length <= 32) {
      this.viewDigest = digest;
      void this.refreshViewRun(this.generation);
    }
  }
  /** Follow the view stream (`Last-Event-ID` = the last applied frame) until `done`. */
  async followView(runId, generation) {
    const rv = this.transport.replayView;
    const fold = this.viewFold;
    if (!rv || !fold)
      return;
    let failures = 0;
    while (this.live(generation) && this.viewFold === fold && !fold.terminal) {
      this.set({ ...this.snapshot, connection: failures ? "reconnecting" : "connecting" });
      try {
        await rv.streamView(runId, {
          lastEventId: fold.lastEventId,
          signal: this.controller.signal,
          onOpen: () => {
            if (!this.live(generation))
              return;
            this.set({ ...this.snapshot, connection: "connected", error: null });
          },
          onFrame: (frame) => {
            if (!this.live(generation) || this.viewFold !== fold)
              return;
            failures = 0;
            const outcome = fold.apply(frame);
            if (outcome === "view" || outcome === "delta")
              this.adoptView();
          }
        });
        if (!this.live(generation))
          return;
        if (fold.terminal)
          break;
        failures += 1;
      } catch (error) {
        if (!this.live(generation))
          return;
        failures += 1;
        this.fail(error, false);
        if (authError(error)) {
          this.set({ ...this.snapshot, connection: "disconnected" });
          return;
        }
      }
      if (failures >= 5 || !this.live(generation))
        break;
      await this.waitForRetry(Math.min(2e3, 150 * 2 ** (failures - 1)));
    }
    this.viewStreamEnded = true;
    if (!this.live(generation) || this.viewFold !== fold)
      return;
    if (fold.terminal || terminal(this.snapshot.status)) {
      this.set({ ...this.snapshot, connection: "disconnected" });
      return;
    }
    this.set({ ...this.snapshot, connection: "disconnected", error: this.snapshot.error || "Replay view stream reconnect limit reached. Reconnect the workflow to continue." });
  }
  /**
   * Live reply text (`llm.delta`) is not part of the view: it rides the root's ledger stream
   * (which also carries the sub-runs' deltas). Its records are ignored here: the view has them.
   */
  async followLiveReplies(runId, generation) {
    let failures = 0;
    try {
      while (this.live(generation) && this.viewFold && !this.viewStreamEnded && !terminal(this.snapshot.status)) {
        const after = Number(this.viewFold.view?.cursor?.runs?.[runId]) || 0;
        this.dropLiveRepliesVia(runId);
        try {
          await this.transport.streamLedger(runId, after, () => void 0, this.controller.signal, void 0, (event) => {
            if (!this.live(generation))
              return;
            failures = 0;
            this.ingestDelta(runId, event);
          });
          if (!this.live(generation))
            return;
          failures += 1;
        } catch (error) {
          if (!this.live(generation))
            return;
          failures += 1;
          if (authError(error)) {
            this.fail(error);
            return;
          }
        }
        if (failures >= 5)
          return;
        await this.waitForRetry(Math.min(2e3, 150 * 2 ** (failures - 1)));
      }
    } finally {
      if (this.live(generation))
        this.closeLiveRepliesVia(runId);
    }
  }
  /** Conditional re-read of the view (304 while unchanged). */
  async refreshView(generation) {
    const rv = this.transport.replayView;
    const fold = this.viewFold;
    if (!rv || !fold)
      return;
    const read2 = await rv.getView(this.rootRunId, { ifNoneMatch: fold.lastEventId ? `"${fold.lastEventId}"` : null, signal: this.controller?.signal });
    if (!this.live(generation) || this.viewFold !== fold || read2.notModified)
      return;
    if (fold.adopt(read2.view, read2.etag))
      this.adoptView();
  }
  /** `GET runs/{root}` for what the view does not carry (`paused`); never a lifecycle authority over the view. */
  async refreshViewRun(generation) {
    try {
      const run = object(await this.transport.getRun(this.rootRunId, this.controller?.signal));
      if (!run || !this.live(generation) || !this.viewFold)
        return;
      this.viewRun = run;
      this.adoptView();
    } catch (error) {
      if (this.live(generation))
        this.fail(error, false);
    }
  }
  async catchUpAndWatch(runId, generation) {
    if (!this.live(generation) || this.watchedRuns.has(runId))
      return;
    this.watchedRuns.add(runId);
    try {
      if (runId !== this.rootRunId) {
        try {
          const run = object(await this.transport.getRun(runId, this.controller?.signal));
          if (!this.live(generation))
            return;
          if (run)
            this.updateRunState(runId, run);
        } catch (error) {
          if (!this.live(generation))
            return;
          if (authError(error))
            throw error;
          this.fail(error, false);
        }
      }
      await this.catchUp(runId, generation);
      if (!this.live(generation) || terminal(statusOf(this.runStates.get(runId) || null)))
        return;
      this.childCatchUpAttempts.delete(runId);
      void this.watch(runId, generation);
    } catch (error) {
      if (!this.live(generation))
        return;
      this.watchedRuns.delete(runId);
      if (runId === this.rootRunId)
        throw error;
      if (authError(error)) {
        this.fail(error);
        return;
      }
      const attempts = (this.childCatchUpAttempts.get(runId) || 0) + 1;
      this.childCatchUpAttempts.set(runId, attempts);
      this.fail(error, false);
      if (attempts >= 5)
        return;
      await this.waitForRetry(Math.min(2e3, 150 * 2 ** (attempts - 1)));
      if (this.live(generation))
        void this.catchUpAndWatch(runId, generation);
    }
  }
  async catchUp(runId, generation) {
    for (let page = 0; page < 100 && this.live(generation); page += 1) {
      const after = this.cursors.get(runId) || 0;
      const pageValue = await this.transport.getLedger(runId, after, this.controller?.signal);
      if (!this.live(generation))
        return;
      const pageObj = object(pageValue);
      const items = Array.isArray(pageValue) ? pageValue : array(pageObj?.items);
      for (const item of items)
        this.ingestItem(runId, item);
      const next = Number(pageObj?.next_after);
      if (!items.length || !Number.isFinite(next) || next <= after)
        break;
      this.cursors.set(runId, next);
    }
  }
  /** Follow one run's stream until it ends or this controller stops
   * following it; either way no live reply that stream delivered survives. */
  async watch(runId, generation) {
    try {
      await this.followStream(runId, generation);
    } finally {
      if (this.live(generation))
        this.closeLiveRepliesVia(runId);
    }
  }
  async followStream(runId, generation) {
    let attempt = 0;
    while (this.live(generation) && !terminal(statusOf(this.runStates.get(runId) || null))) {
      const after = this.cursors.get(runId) || 0;
      this.set({ ...this.snapshot, connection: attempt ? "reconnecting" : "connecting" });
      try {
        let streamConnected = false;
        const markStreamConnected = () => {
          if (!this.live(generation) || streamConnected)
            return;
          streamConnected = true;
          this.set({ ...this.snapshot, connection: "connected", error: null });
        };
        this.dropLiveRepliesVia(runId);
        await this.transport.streamLedger(runId, after, (item) => {
          if (!this.live(generation))
            return;
          markStreamConnected();
          this.ingestItem(runId, item);
        }, this.controller.signal, markStreamConnected, (event) => {
          if (!this.live(generation))
            return;
          markStreamConnected();
          this.ingestDelta(runId, event);
        });
        if (!this.live(generation))
          return;
        await this.catchUp(runId, generation);
        if (!this.live(generation))
          return;
        const run = object(await this.transport.getRun(runId, this.controller?.signal));
        if (!this.live(generation))
          return;
        if (run)
          this.updateRunState(runId, run);
        attempt += 1;
      } catch (error) {
        if (!this.live(generation))
          return;
        attempt += 1;
        this.fail(error, false);
        if (authError(error)) {
          this.set({ ...this.snapshot, connection: "disconnected" });
          return;
        }
      }
      if (attempt >= 5 || !this.live(generation))
        break;
      await this.waitForRetry(Math.min(2e3, 150 * 2 ** (attempt - 1)));
    }
    if (!this.live(generation))
      return;
    if (terminal(statusOf(this.runStates.get(runId) || null))) {
      this.set({ ...this.snapshot, connection: "disconnected" });
      return;
    }
    this.set({
      ...this.snapshot,
      connection: "disconnected",
      error: this.snapshot.error || "Ledger stream reconnect limit reached. Reconnect the workflow to continue."
    });
  }
  async ingestHistory(history, fallbackRunId, generation) {
    const bundle = object(history);
    if (!bundle)
      return;
    const session = object(bundle.session);
    const turns = array(session?.turns).map(object).filter((turn) => Boolean(turn));
    await this.hydrateHistoricalSessionRuns(turns, fallbackRunId, generation);
    if (!this.live(generation))
      return;
    for (const row2 of turns) {
      const turnRunId = text2(row2?.run_id) || fallbackRunId;
      this.ingestSessionTurn(row2, fallbackRunId, turnRunId !== fallbackRunId ? this.historicalRuns.get(turnRunId) || null : null);
    }
    const userMessageId = `turn:${fallbackRunId}:user`;
    if (!this.seenMessages.has(userMessageId)) {
      const prompt = promptFromInput(object(bundle.input_data));
      if (prompt)
        this.addMessage({ id: userMessageId, role: "user", content: prompt });
    }
    const ledgers = object(bundle.ledgers);
    if (ledgers)
      for (const [runId, ledger] of Object.entries(ledgers)) {
        const row2 = object(ledger);
        for (const item of array(row2?.items))
          this.ingestItem(runId, item);
      }
  }
  ingestSessionTurn(turn, fallbackRunId, historicalRun) {
    if (!turn)
      return;
    const runId = text2(turn.run_id) || fallbackRunId;
    const input = object(turn.input_data) || object(turn.input) || {};
    const prompt = text2(turn.prompt) || promptFromInput(input);
    if (prompt)
      this.addMessage({ id: `turn:${runId}:user`, role: "user", content: prompt, ts: text2(turn.created_at) || void 0 });
    const failure = this.historicalRunFailures.get(runId);
    if (failure) {
      const saved = text2(turn.answer) || messageText(turn.output);
      const state = failure.missing ? "is unavailable because the run no longer exists" : "could not be restored";
      const fallback = saved ? ` Saved reply (not verified as the final result): ${saved}` : "";
      this.addMessage({ id: `history:${runId}:unavailable`, role: "system", level: "warn", title: "History", content: `The final output for an earlier turn ${state}.${fallback}` });
      return;
    }
    const authoritative = historicalRun && terminal(statusOf(historicalRun)) ? displayValue(historicalRun.output) : "";
    const answer = authoritative || (historicalRun ? text2(turn.answer) || messageText(turn.output) : "");
    const evidence2 = this.historicalEvidence.get(runId);
    for (const tool of evidence2?.tools || [])
      this.upsertTool(tool);
    if (answer)
      this.addRunAssistantMessage(runId, { id: `final:${runId}`, role: "assistant", content: answer, runId, statistics: evidence2?.statistics, ts: text2(turn.updated_at) || void 0 });
  }
  /** Fetch only returned prior session roots, with bounded fan-out. */
  async hydrateHistoricalSessionRuns(turns, currentRunId, generation) {
    const ids = [...new Set(turns.map((turn) => text2(turn.run_id)).filter((runId) => runId && runId !== currentRunId && !this.historicalRuns.has(runId) && !this.historicalRunFailures.has(runId)))];
    if (!ids.length || !this.live(generation))
      return;
    let next = 0;
    let stopForAuth = false;
    const worker = async () => {
      while (!stopForAuth && this.live(generation)) {
        const runId = ids[next++];
        if (!runId)
          return;
        try {
          const run = object(await this.transport.getRun(runId, this.controller?.signal));
          if (!this.live(generation))
            return;
          if (run) {
            this.historicalRuns.set(runId, run);
            try {
              const history = await this.transport.getHistory(runId, this.controller?.signal);
              if (!this.live(generation))
                return;
              this.historicalEvidence.set(runId, workflowEvidence(historyRecords(history)));
            } catch (error) {
              if (!this.live(generation))
                return;
              if (authError(error))
                throw error;
              this.fail(new Error(`Earlier turn activity could not be restored: ${error instanceof Error ? error.message : String(error)}`), false);
            }
          } else {
            this.historicalRuns.set(runId, null);
            this.historicalRunFailures.set(runId, { missing: false, detail: "gateway returned an invalid historical run snapshot" });
          }
        } catch (error) {
          if (!this.live(generation))
            return;
          const missing = statusCode(error) === 404;
          this.historicalRuns.set(runId, null);
          this.historicalRunFailures.set(runId, { missing, detail: error instanceof Error ? error.message : text2(object(error)?.detail) || "request failed" });
          if (authError(error)) {
            stopForAuth = true;
            this.fail(error);
          }
        }
      }
    };
    await Promise.all(Array.from({ length: Math.min(4, ids.length) }, () => worker()));
    if (stopForAuth && this.live(generation)) {
      for (const runId of ids) {
        if (!this.historicalRuns.has(runId) && !this.historicalRunFailures.has(runId)) {
          this.historicalRuns.set(runId, null);
          this.historicalRunFailures.set(runId, { missing: false, detail: "authorization expired before this historical run could be restored" });
        }
      }
    }
  }
  ingestItem(fallbackRunId, item) {
    const envelope = object(item);
    const raw = object(envelope?.record) || envelope;
    if (!raw)
      return;
    const runId = runIdFrom(raw, fallbackRunId);
    const cursorRaw = Number(envelope?.cursor);
    const cursor = Number.isFinite(cursorRaw) && cursorRaw > 0 ? cursorRaw : (this.cursors.get(runId) || 0) + 1;
    const key = `${runId}:${cursor}`;
    if (this.seenRecords.has(key))
      return;
    this.seenRecords.add(key);
    this.cursors.set(runId, Math.max(this.cursors.get(runId) || 0, cursor));
    this.set({ ...this.snapshot, records: [...this.snapshot.records, { cursor, record: raw, runId }] });
    this.foldRecord(runId, raw, key);
    if (this.snapshot.messages.some((message) => message.id === `final:${this.rootRunId}`)) {
      const statistics = workflowEvidence(this.snapshot.records).statistics;
      this.set({ ...this.snapshot, messages: this.snapshot.messages.map((message) => message.id === `final:${this.rootRunId}` ? { ...message, statistics } : message) });
    }
    for (const child of subRunIds(raw))
      if (child !== runId)
        void this.catchUpAndWatch(child, this.generation);
  }
  foldRecord(runId, record3, key) {
    const eff = effect(record3);
    const effectType = text2(eff.type).toLowerCase();
    const result = object(record3.result);
    const recStatus = text2(record3.status).toLowerCase();
    const timestamp = recordTimestamp(record3);
    this.foldStopEvidence(runId, record3, effectType, recStatus);
    if (["llm_call", "tool_calls"].includes(effectType) && ["started", "running"].includes(recStatus)) {
      const at = Date.parse(timestamp || "");
      if (!Number.isFinite(at) || at >= this.displayStatusAt) {
        if (Number.isFinite(at))
          this.displayStatusAt = at;
        if (this.snapshot.displayStatus)
          this.set({ ...this.snapshot, displayStatus: "" });
      }
    }
    if (effectType === "answer_user" && recStatus === "completed") {
      const content = displayValue(result) || displayValue(object(eff.payload));
      if (content)
        this.addRunAssistantMessage(runId, { id: `answer:${runId}:${key}`, role: "assistant", kind: "answer", runId, content, ts: timestamp });
    }
    if (effectType === "emit_event" && recStatus === "completed") {
      const payload = object(eff.payload) || {};
      const emitted = object(result);
      const name = text2(payload.name) || text2(emitted?.name);
      const eventPayload = payload.payload !== void 0 ? payload.payload : emitted?.payload;
      if (name === "user_guidance") {
        const message = object(eventPayload);
        const seq = message?.seq;
        if (message && message.status === "accepted" && Number.isInteger(seq) && Number(seq) > 0 && message.run_id === runId && message.id === `${runId}:guidance:${seq}` && record3.node_id === "__host_user_guidance__" && record3.idempotency_key === `system:user_guidance:${seq}` && typeof message.text === "string" && message.text.trim()) {
          this.addMessage({ id: message.id, role: "user", kind: "guidance", source: "user_guidance", runId, content: message.text, ts: timestamp });
        }
      }
      if (name === "public_update") {
        const update = publicUpdate(eventPayload, runId);
        if (update)
          this.addMessage({ id: `public_update:${runId}:${update.id}`, role: "assistant", kind: "public_update", source: "public_update", runId, content: update.text, publicUpdate: update, ts: timestamp });
      }
      if (["abstract.message", "abstractcode.message"].includes(name)) {
        const content = displayValue(eventPayload);
        if (content) {
          const levelRaw = text2(object(eventPayload)?.level).toLowerCase();
          const level = levelRaw === "error" ? "error" : ["warn", "warning"].includes(levelRaw) ? "warn" : "info";
          this.addMessage({ id: `event:${runId}:${key}`, role: "system", title: "Workflow", content, level, ts: timestamp });
        }
      }
      if (["abstract.status", "abstractcode.status"].includes(name)) {
        const statusPayload = object(eventPayload);
        const value = statusPayload ? statusPayload.status ?? statusPayload.text ?? statusPayload.value : eventPayload;
        const at = Date.parse(timestamp || "");
        if (!terminal(this.snapshot.status) && typeof value === "string" && (!Number.isFinite(at) || at >= this.displayStatusAt)) {
          if (Number.isFinite(at))
            this.displayStatusAt = at;
          this.set({ ...this.snapshot, displayStatus: value.trim() });
        }
      }
      if (name === "abstract.tool_policy_decision") {
        const decision = toolPolicyDecision(object(eventPayload));
        if (decision) {
          this.addMessage({ id: `policy:${runId}:${key}`, role: "system", kind: "tool_policy_decision", title: "Tool policy", content: toolPolicyDecisionText(decision.provenance), ts: timestamp });
          for (const call of decision.calls) {
            const provenance = { ...decision.provenance, ...call.matched ? { matched: call.matched } : {} };
            this.toolPolicyByCall.set(`${runId}:${call.callId}`, provenance);
            for (const tool of this.toolActivities.values())
              if (tool.runId === runId && tool.callId === call.callId)
                this.upsertTool(tool);
          }
        }
      }
      if (["abstract.tool_execution", "abstractcode.tool_execution", "abstract.tool_result", "abstractcode.tool_result"].includes(name)) {
        const content = displayValue(eventPayload);
        if (content)
          this.addMessage({ id: `event:${runId}:${key}`, role: "system", title: "Tool activity", content, ts: timestamp });
      }
    }
    const waiting = waitFromRecord(record3);
    if (recStatus === "waiting" && waiting && !terminal(this.snapshot.status) && !terminal(statusOf(this.runStates.get(runId) || null))) {
      this.resolvedWaits.delete(`${runId}:${text2(waiting.wait_key)}`);
      this.set({ ...this.snapshot, interaction: this.interactionWith({ runId, wait: waiting, ...text2(record3.step_id) ? { stepId: text2(record3.step_id) } : {} }) });
    }
    if (effectType === "tool_calls")
      for (const tool of foldWorkflowTools(this.toolActivities, { runId, cursor: this.cursors.get(runId) || 0, record: record3 }))
        this.upsertTool(tool);
    if (effectType === "resume" && result?.resumed === true) {
      const resumedKey = text2(object(eff.payload)?.wait_key);
      if (resumedKey)
        this.resolvedWaits.add(`${runId}:${resumedKey}`);
      if (this.snapshot.interaction?.runId === runId) {
        this.set({ ...this.snapshot, interaction: null });
        void this.refreshRunState(runId, this.generation);
      }
    }
  }
  /** Ledger evidence for the Stop states: open model calls and forced stops. */
  foldStopEvidence(runId, record3, effectType, recStatus) {
    let changed = false;
    if (effectType === "llm_call") {
      const stepId = text2(record3.step_id);
      if (stepId) {
        const stepKey = `${runId}:${stepId}`;
        if (recStatus === "started") {
          this.openLlmSteps.add(stepKey);
          changed = true;
        } else if (["completed", "failed", "cancelled", "waiting"].includes(recStatus))
          changed = this.openLlmSteps.delete(stepKey) || changed;
        if (["completed", "failed", "cancelled"].includes(recStatus))
          this.closeLiveReply(stepKey);
      }
    }
    if (effectType === "emit_event" && recStatus === "completed") {
      const payload = object(effect(record3).payload) || {};
      const emitted = object(record3.result);
      const name = text2(payload.name) || text2(emitted?.name);
      const eventPayload = object(payload.payload !== void 0 ? payload.payload : emitted?.payload);
      if (name === "abstract.status" && text2(eventPayload?.killed_by) === "kill_switch") {
        this.forcedStop = eventPayload;
        changed = true;
      }
    }
    if (changed)
      this.recomputeStop();
  }
  recomputeStop() {
    let next = null;
    if (this.forcedStop) {
      next = { phase: "forced", label: text2(this.forcedStop.text) || "Stop forced: inference killed", record: this.forcedStop };
    } else if (this.stopRequested) {
      const cancelled = this.snapshot.status === "cancelled";
      next = cancelled && this.openLlmSteps.size === 0 ? { phase: "stopped", label: "Stopped" } : { phase: "stopping", label: "Stopping\u2026" };
    }
    const current = this.snapshot.stop || null;
    if (current?.phase !== next?.phase || current?.label !== next?.label)
      this.set({ ...this.snapshot, stop: next });
    if (next?.phase === "stopping" && this.snapshot.status === "cancelled")
      void this.followStop(this.generation);
  }
  /** Ledger catch-up while a cancelled tree still has an open model call. Ends
   * on evidence (stopped/forced) or when this controller is reset; the state
   * itself only ever changes through `foldStopEvidence`. */
  async followStop(generation) {
    if (this.stopFollowing)
      return;
    this.stopFollowing = true;
    try {
      let delay = 500;
      let ownError = null;
      while (this.live(generation) && this.snapshot.stop?.phase === "stopping") {
        await this.waitForRetry(delay);
        if (!this.live(generation))
          return;
        const runs = this.viewFold ? [] : [this.rootRunId, ...[...this.watchedRuns].filter((id) => id !== this.rootRunId)];
        let failed = false;
        if (this.viewFold) {
          try {
            await this.refreshView(generation);
          } catch (error) {
            failed = true;
            if (this.live(generation)) {
              this.fail(error, false);
              ownError = this.snapshot.error;
            }
          }
        }
        for (const id of runs) {
          try {
            await this.catchUp(id, generation);
          } catch (error) {
            failed = true;
            if (this.live(generation)) {
              this.fail(error, false);
              ownError = this.snapshot.error;
            }
          }
        }
        if (!failed && ownError && this.snapshot.error === ownError) {
          this.set({ ...this.snapshot, error: null });
          ownError = null;
        }
        delay = Math.min(5e3, delay * 2);
      }
    } finally {
      if (this.generation === generation)
        this.stopFollowing = false;
    }
  }
  addMessage(message) {
    const id = text2(message.id) || `${message.role}:${message.content}:${message.ts || ""}`;
    if (this.seenMessages.has(id))
      return;
    this.seenMessages.add(id);
    this.set({ ...this.snapshot, messages: [...this.snapshot.messages, { ...message, id }] });
  }
  toolMessage(activity) {
    const policy = activity.callId ? this.toolPolicyByCall.get(`${activity.runId}:${activity.callId}`) : void 0;
    return toolActivityMessage(policy ? { ...activity, policy } : activity);
  }
  upsertTool(tool) {
    const message = this.toolMessage(tool);
    const index = this.snapshot.messages.findIndex((item) => item.id === message.id);
    if (index < 0) {
      this.addMessage(message);
      return;
    }
    const messages = [...this.snapshot.messages];
    messages[index] = message;
    this.set({ ...this.snapshot, messages });
  }
  /** Session history is a fallback; durable answer_user and terminal output
   * are authoritative. Suppress only an exact duplicate for the same run. */
  addRunAssistantMessage(runId, message) {
    this.closeLiveRepliesOfRun(runId);
    const answerPrefix = `answer:${runId}:`;
    const finalId = `final:${runId}`;
    if (this.snapshot.messages.some((existing) => existing.role === "assistant" && existing.content === message.content && (existing.id === finalId || String(existing.id || "").startsWith(answerPrefix))))
      return;
    this.addMessage(message);
  }
  /**
   * Fold one `llm.delta` / `llm.delta_end` event delivered by the stream of
   * `streamRunId`. A snapshot replaces the channel's text (unless it is older
   * than what is shown); a live delta is appended only when its `seq` is
   * higher than the last one of its channel, so duplicates and out-of-order
   * frames are dropped. A call whose durable record or reply is already here
   * never gets a bubble again. A malformed event is reported as an error.
   */
  ingestDelta(streamRunId, raw) {
    let event;
    try {
      event = validateLlmDeltaEvent(raw);
    } catch (error) {
      this.fail(error, false);
      return;
    }
    const key = `${event.run_id}:${event.call_id}`;
    if (isLlmDeltaEnd(event)) {
      if (event.reason === "unavailable") {
        this.noteStreamUnavailable(event);
        return;
      }
      if (event.reason === "cancelled" && event.detail === "reinvoked") {
        this.closeLiveReply(key, "restarted");
        return;
      }
      this.closeLiveReply(key, event.reason === "completed" ? void 0 : event.reason);
      return;
    }
    if (this.closedLiveCalls.has(key) || this.runEnded(event.run_id) || this.runEnded(this.rootRunId))
      return;
    const reply = this.liveReplies.get(key) || { runId: event.run_id, callId: event.call_id, nodeId: event.node_id || "", via: streamRunId, text: "", reasoning: "", seq: { content: -1, reasoning: -1 } };
    const field = event.channel === "reasoning" ? "reasoning" : "text";
    const last = reply.seq[event.channel];
    if (event.snapshot) {
      if (event.seq < last)
        return;
      reply[field] = event.text;
    } else {
      if (event.seq <= last)
        return;
      reply[field] += event.text;
    }
    reply.seq[event.channel] = event.seq;
    reply.via = streamRunId;
    this.liveReplies.set(key, reply);
    this.liveDirty.add(key);
    this.scheduleLiveRender();
  }
  runEnded(runId) {
    const view = this.viewFold?.view;
    if (view)
      return terminal(String(view.runs.find((run) => run.run_id === runId)?.status || "")) || runId === this.rootRunId && terminal(String(view.status || ""));
    return terminal(statusOf(this.runStates.get(runId) || null));
  }
  /** Render changed live replies now, or at the end of the current interval. */
  scheduleLiveRender() {
    if (this.liveRenderTimer)
      return;
    const wait = this.lastLiveRender + this.liveRenderIntervalMs - Date.now();
    if (wait <= 0) {
      this.renderLiveReplies();
      return;
    }
    this.liveRenderTimer = setTimeout(() => {
      this.liveRenderTimer = null;
      this.renderLiveReplies();
    }, wait);
  }
  renderLiveReplies() {
    this.lastLiveRender = Date.now();
    if (!this.liveDirty.size)
      return;
    const messages = [...this.snapshot.messages];
    for (const key of this.liveDirty) {
      const reply = this.liveReplies.get(key);
      if (!reply)
        continue;
      const message = this.liveMessage(reply);
      const index = messages.findIndex((item) => item.id === message.id);
      if (index < 0)
        messages.push(message);
      else
        messages[index] = message;
      this.shownLiveCalls.add(key);
    }
    this.liveDirty.clear();
    this.set({ ...this.snapshot, messages });
  }
  liveMessage(reply) {
    const subAgent = reply.runId !== this.rootRunId;
    return {
      id: `live:${reply.runId}:${reply.callId}`,
      role: "assistant",
      content: reply.text,
      runId: reply.runId,
      live: { callId: reply.callId, reasoning: reply.reasoning, ...subAgent ? { caption: `sub-agent \xB7 ${reply.nodeId || reply.runId}` } : {} }
    };
  }
  /** End a live reply: remove its bubble, or replace it with a short note
   * when the stream ended because the call failed or was cancelled. */
  closeLiveReply(key, reason) {
    this.closedLiveCalls.add(key);
    const reply = this.liveReplies.get(key);
    if (!reply) {
      if (reason === "restarted" && this.shownLiveCalls.has(key))
        this.addMessage(this.restartNote(key));
      return;
    }
    this.liveReplies.delete(key);
    this.liveDirty.delete(key);
    const id = `live:${reply.runId}:${reply.callId}`;
    const index = this.snapshot.messages.findIndex((item) => item.id === id);
    if (index < 0)
      return;
    const messages = [...this.snapshot.messages];
    if (reason === "restarted") {
      const note = this.restartNote(key);
      this.seenMessages.add(String(note.id));
      messages[index] = note;
    } else if (reason) {
      const noteId = `live-end:${reply.runId}:${reply.callId}`;
      this.seenMessages.add(noteId);
      messages[index] = { id: noteId, role: "system", level: "warn", title: "Reply", runId: reply.runId, content: reason === "failed" ? "The reply stopped because the model call failed." : "The reply stopped because the model call was cancelled." };
    } else
      messages.splice(index, 1);
    this.set({ ...this.snapshot, messages });
  }
  restartNote(key) {
    const runId = key.slice(0, key.indexOf(":"));
    return { id: `live-end:${key}`, role: "system", level: "info", title: "Reply", runId, content: "Reply restarted: the model call was interrupted and is running again." };
  }
  /** A call ran without streaming: one note per run and cause, never a bubble. */
  noteStreamUnavailable(event) {
    const key = `${event.run_id}:${event.call_id}`;
    this.closeLiveReply(key);
    this.addMessage({ id: `stream-unavailable:${event.run_id}:${event.detail || "unknown"}`, role: "system", level: "info", title: "Reply", runId: event.run_id, content: describeStreamUnavailable(event.detail) });
  }
  closeLiveRepliesOfRun(runId) {
    for (const reply of [...this.liveReplies.values()])
      if (reply.runId === runId)
        this.closeLiveReply(`${reply.runId}:${reply.callId}`);
  }
  /** Close the live replies a stream delivered (the controller stopped following it). */
  closeLiveRepliesVia(streamRunId, reason) {
    for (const reply of [...this.liveReplies.values()])
      if (reply.via === streamRunId || reply.runId === streamRunId)
        this.closeLiveReply(`${reply.runId}:${reply.callId}`, reason);
  }
  /**
   * A run reached a terminal state: close its live replies (for the root, every
   * live reply of the turn, sub-agents included) whether or not their
   * `llm.delta_end` arrived, then forget its closed-call keys. Later frames for
   * it are refused by the terminal-run check in `ingestDelta`.
   */
  endLiveRepliesOfRun(runId, status) {
    const reason = status === "failed" || status === "cancelled" ? status : void 0;
    if (runId === this.rootRunId) {
      for (const reply of [...this.liveReplies.values()])
        this.closeLiveReply(`${reply.runId}:${reply.callId}`, reason);
      this.closedLiveCalls.clear();
      this.shownLiveCalls.clear();
      return;
    }
    this.closeLiveRepliesVia(runId, reason);
    for (const key of [...this.closedLiveCalls])
      if (key.startsWith(`${runId}:`))
        this.closedLiveCalls.delete(key);
    for (const key of [...this.shownLiveCalls])
      if (key.startsWith(`${runId}:`))
        this.shownLiveCalls.delete(key);
  }
  /** Forget (without closing) the live replies a stream delivered; its
   * reconnect snapshots bring the current text back. */
  dropLiveRepliesVia(streamRunId) {
    const dropped = /* @__PURE__ */ new Set();
    for (const [key, reply] of this.liveReplies)
      if (reply.via === streamRunId) {
        this.liveReplies.delete(key);
        this.liveDirty.delete(key);
        dropped.add(`live:${reply.runId}:${reply.callId}`);
      }
    if (dropped.size)
      this.set({ ...this.snapshot, messages: this.snapshot.messages.filter((message) => !dropped.has(String(message.id))) });
  }
  fail(error, setConnection = true) {
    if (authError(error)) {
      this.approvalEpoch += 1;
      this.toolApprovalStopped = true;
      this.toolApprovalSuspended = true;
      this.options.onAuthError?.(error);
    }
    this.set({ ...this.snapshot, error: error instanceof Error ? error.message : text2(object(error)?.detail) || String(error), ...authError(error) ? { autoApproveTools: false } : {}, ...setConnection ? { connection: "disconnected" } : {} });
  }
  newCommandId() {
    const cryptoApi = globalThis.crypto;
    if (cryptoApi && typeof cryptoApi.randomUUID === "function")
      return cryptoApi.randomUUID();
    if (cryptoApi && typeof cryptoApi.getRandomValues === "function") {
      const b = cryptoApi.getRandomValues(new Uint8Array(16));
      b[6] = b[6] & 15 | 64;
      b[8] = b[8] & 63 | 128;
      const hex = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
      return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
    }
    return `workflow-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }
  updateRunState(runId, run) {
    this.runStates.set(runId, run);
    if (terminal(statusOf(run)))
      this.endLiveRepliesOfRun(runId, statusOf(run));
    if (runId !== this.rootRunId) {
      if (terminal(statusOf(run)) && this.snapshot.interaction?.runId === runId)
        this.set({ ...this.snapshot, interaction: null });
      else
        this.adoptDurableWait(runId, run);
      return;
    }
    const status = statusOf(run);
    const done = terminal(status);
    if (done) {
      const content = displayValue(run.output);
      if (content)
        this.upsertFinal(runId, content, recordTimestamp(run));
    }
    this.set({ ...this.snapshot, run, status, ...done ? { interaction: null, autoApproveTools: false, displayStatus: "" } : {} });
    if (!done)
      this.adoptDurableWait(runId, run);
    if (this.stopRequested || this.forcedStop)
      this.recomputeStop();
  }
  upsertFinal(runId, content, ts) {
    this.closeLiveRepliesOfRun(runId);
    const id = `final:${runId}`;
    this.seenMessages.add(id);
    const message = { id, role: "assistant", kind: "final", content, ts, runId, statistics: workflowEvidence(this.snapshot.records).statistics };
    const index = this.snapshot.messages.findIndex((existing) => existing.id === id || String(existing.id || "").startsWith(`answer:${runId}:`) && existing.content === content);
    if (index < 0) {
      this.set({ ...this.snapshot, messages: [...this.snapshot.messages, message] });
      return;
    }
    const messages = [...this.snapshot.messages];
    messages[index] = message;
    this.set({ ...this.snapshot, messages });
  }
  async refreshRunState(runId, generation) {
    try {
      const run = object(await this.transport.getRun(runId, this.controller?.signal));
      if (run && this.live(generation))
        this.updateRunState(runId, run);
    } catch (error) {
      if (this.live(generation))
        this.fail(error, false);
    }
  }
  /**
   * SSE is the source for ledger records, not an exhaustive lifecycle feed.
   * In particular a parked event wait can remain connected while another
   * actor pauses it or cancels its root. Poll only the root metadata at a
   * modest cadence; AbortController + generation prevent stale completions
   * from an old run or auth scope changing the current snapshot.
   */
  async pollRootLifecycle(runId, generation) {
    while (this.live(generation) && this.rootRunId === runId && !terminal(statusOf(this.runStates.get(runId) || null))) {
      await this.waitForRetry(2e3);
      if (!this.live(generation) || this.rootRunId !== runId || terminal(statusOf(this.runStates.get(runId) || null)))
        return;
      try {
        const run = object(await this.transport.getRun(runId, this.controller?.signal));
        if (run && this.live(generation) && this.rootRunId === runId)
          this.updateRunState(runId, run);
      } catch (error) {
        if (!this.live(generation))
          return;
        if (authError(error)) {
          this.fail(error);
          return;
        }
        this.fail(error, false);
      }
    }
  }
  waitForRetry(delayMs) {
    const signal = this.controller?.signal;
    if (!signal || signal.aborted)
      return Promise.resolve();
    const activeSignal = signal;
    return new Promise((resolve) => {
      const timer = setTimeout(done, delayMs);
      const onAbort = () => {
        clearTimeout(timer);
        done();
      };
      function done() {
        activeSignal.removeEventListener("abort", onAbort);
        resolve();
      }
      activeSignal.addEventListener("abort", onAbort, { once: true });
    });
  }
};

// dist/use_workflow_session.js
function useWorkflowSession(options) {
  const controller = useMemo9(() => new WorkflowSessionController(options.transport, { onAuthError: options.onAuthError, clientId: options.clientId, ...options.liveRenderIntervalMs !== void 0 ? { liveRenderIntervalMs: options.liveRenderIntervalMs } : {} }), [options.transport, options.onAuthError, options.clientId, options.authScopeKey, options.liveRenderIntervalMs]);
  const snapshot = useSyncExternalStore((listener) => controller.subscribe(listener), () => controller.getSnapshot(), () => controller.getSnapshot());
  const runId = String(options.runId || "").trim();
  useEffect16(() => {
    controller.setToolApprovalPolicy(options.enabled === false ? { enabledTools: [], autoApproveTools: [] } : options.toolApprovalPolicy ?? null);
  }, [controller, options.toolApprovalPolicy, options.enabled]);
  useEffect16(() => {
    if (options.enabled === false || !runId) {
      controller.reset();
      return;
    }
    void controller.load(runId);
    return () => controller.reset();
  }, [controller, runId, options.enabled]);
  return { controller, snapshot };
}

// dist/conversation_preferences.js
import { useEffect as useEffect17, useRef as useRef12, useState as useState16 } from "react";
function read(scope2) {
  try {
    const raw = typeof localStorage === "undefined" ? null : localStorage.getItem(`abstract.conversation:${scope2}`);
    if (!raw)
      return { mode: "chat", preferences: DEFAULT_CONVERSATION_CUES, error: null };
    const saved = JSON.parse(raw);
    const preferences = Object.fromEntries(["approval", "question", "completion"].map((kind) => [kind, { visual: saved.preferences?.[kind]?.visual !== false, audio: saved.preferences?.[kind]?.audio !== false, haptic: saved.preferences?.[kind]?.haptic === true }]));
    return { mode: saved.mode === "avatar" ? "avatar" : "chat", preferences, error: null };
  } catch (error) {
    return { mode: "chat", preferences: DEFAULT_CONVERSATION_CUES, error: `Conversation preferences could not be loaded: ${String(error)}` };
  }
}
function useAvatarConversationPreferences(scope2) {
  const [saved, setSaved] = useState16(() => ({ scope: scope2, ...read(scope2) }));
  const current = saved.scope === scope2 ? saved : { scope: scope2, ...read(scope2) };
  const stateRef = useRef12(current);
  stateRef.current = current;
  useEffect17(() => {
    if (saved.scope !== scope2)
      setSaved({ scope: scope2, ...read(scope2) });
  }, [scope2, saved.scope]);
  const write = (change) => {
    const next = { ...stateRef.current, ...change, scope: scope2, error: null };
    try {
      if (typeof localStorage !== "undefined")
        localStorage.setItem(`abstract.conversation:${scope2}`, JSON.stringify({ mode: next.mode, preferences: next.preferences }));
    } catch (error) {
      next.error = `Conversation preferences could not be saved: ${String(error)}`;
    }
    stateRef.current = next;
    setSaved(next);
  };
  return { mode: current.mode, setMode: (mode) => write({ mode }), preferences: current.preferences, setPreferences: (preferences) => write({ preferences }), error: current.error };
}
async function playConversationCue(cue) {
  if (!cue.channels.audio)
    return;
  if (typeof window === "undefined" || !window.AudioContext)
    throw new Error("Audio cues are unavailable in this browser.");
  const context = new window.AudioContext();
  try {
    await context.resume();
    if (context.state !== "running")
      throw new Error("Enable audio with a browser interaction before playing conversation cues.");
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.frequency.value = cue.kind === "approval" ? 440 : cue.kind === "question" ? 600 : 800;
    gain.gain.setValueAtTime(0.035, context.currentTime);
    gain.gain.exponentialRampToValueAtTime(1e-3, context.currentTime + 0.18);
    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.start();
    oscillator.stop(context.currentTime + 0.2);
    await new Promise((resolve) => {
      oscillator.onended = () => resolve();
    });
  } finally {
    await context.close();
  }
}

// dist/present_interaction.js
import { jsx as _jsx19, jsxs as _jsxs16 } from "react/jsx-runtime";

// dist/event_target.js
function object2(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : null;
}
function text3(value) {
  return typeof value === "string" ? value.trim() : value == null ? "" : typeof value === "number" || typeof value === "boolean" ? String(value) : "";
}
function scope(value) {
  return ["session", "workflow", "run", "global"].includes(value) ? value : null;
}
function evidence(value) {
  return {
    scope: text3(value?.scope).toLowerCase(),
    name: text3(value?.name) || text3(value?.event_name),
    scopeId: text3(value?.scope_id) || text3(value?.scopeId),
    sessionId: text3(value?.session_id) || text3(value?.sessionId),
    workflowId: text3(value?.workflow_id) || text3(value?.workflowId),
    runId: text3(value?.run_id) || text3(value?.runId)
  };
}
function matchingEvidence(raw, records) {
  const wait = raw.wait;
  const key = text3(wait.wait_key);
  const out = [evidence(wait), evidence(object2(wait.details))];
  for (const entry of records) {
    if (entry.runId !== raw.runId)
      continue;
    const record3 = entry.record;
    const result = object2(record3.result);
    const storedWait = object2(result?.wait);
    const effect2 = object2(record3.effect);
    const payload = object2(effect2?.payload);
    if (text3(storedWait?.wait_key) !== key && text3(payload?.wait_key) !== key)
      continue;
    out.push(evidence(record3), evidence(payload), evidence(object2(payload?.details)), evidence(storedWait), evidence(object2(storedWait?.details)));
  }
  return out;
}
function idFor(scopeName, row2) {
  if (row2.scopeId)
    return row2.scopeId;
  if (scopeName === "session")
    return row2.sessionId;
  if (scopeName === "workflow")
    return row2.workflowId;
  if (scopeName === "run")
    return row2.runId;
  return "global";
}
function target(scopeName, scopeId, name) {
  return {
    scope: scopeName,
    scopeId,
    name,
    ...scopeName === "session" ? { sessionId: scopeId } : {},
    ...scopeName === "workflow" ? { workflowId: scopeId } : {},
    ...scopeName === "run" ? { runId: scopeId } : {}
  };
}
function decodeWithKnownId(key, scopeName, scopeId) {
  if (!scopeId)
    return null;
  const prefix = `evt:${scopeName}:${scopeId}:`;
  if (!key.startsWith(prefix))
    return null;
  const name = key.slice(prefix.length);
  return name ? target(scopeName, scopeId, name) : null;
}
function resolveWorkflowEventTarget(raw, records = [], currentRun) {
  if (!raw)
    return { target: null, error: "No event wait is available." };
  const key = text3(raw.wait.wait_key);
  const scopeMatch = /^evt:(session|workflow|run|global):/.exec(key);
  if (!scopeMatch)
    return { target: null, error: "The gateway did not provide a canonical event wait key." };
  const keyScope = scope(scopeMatch[1]);
  if (!keyScope)
    return { target: null, error: "The event wait uses an unsupported scope." };
  const facts = matchingEvidence(raw, Array.isArray(records) ? records : []);
  const proven = /* @__PURE__ */ new Map();
  for (const fact of facts) {
    const factScope = scope(fact.scope);
    if (!factScope || !fact.name)
      continue;
    if (factScope !== keyScope)
      return { target: null, error: "Event metadata conflicts with the canonical wait scope." };
    const prefix = `evt:${factScope}:`;
    const suffix = `:${fact.name}`;
    if (!key.startsWith(prefix) || !key.endsWith(suffix) || key.length <= prefix.length + suffix.length) {
      return { target: null, error: "Event metadata does not exactly match the canonical wait key." };
    }
    const scopeId = key.slice(prefix.length, -suffix.length);
    const declaredId = idFor(factScope, fact);
    if (declaredId && declaredId !== scopeId)
      return { target: null, error: "Event metadata conflicts with the canonical wait target." };
    const resolved = target(factScope, scopeId, fact.name);
    proven.set(`${resolved.scope}\0${resolved.scopeId}\0${resolved.name}`, resolved);
  }
  if (proven.size > 1)
    return { target: null, error: "Multiple event targets match this wait; routing is unavailable." };
  if (proven.size === 1)
    return { target: [...proven.values()][0] };
  const ids = /* @__PURE__ */ new Set();
  if (keyScope === "run")
    ids.add(raw.runId);
  if (keyScope === "global")
    ids.add("global");
  for (const fact of facts) {
    const value = idFor(keyScope, fact);
    if (value)
      ids.add(value);
  }
  const currentMatches = text3(currentRun?.run_id) === raw.runId;
  if (currentMatches) {
    const current = evidence(currentRun || null);
    const value = idFor(keyScope, current);
    if (value)
      ids.add(value);
  }
  const decoded = [...ids].map((scopeId) => decodeWithKnownId(key, keyScope, scopeId)).filter((item) => Boolean(item));
  const unique = new Map(decoded.map((item) => [`${item.scope}\0${item.scopeId}\0${item.name}`, item]));
  if (unique.size === 1)
    return { target: [...unique.values()][0] };
  if (unique.size > 1)
    return { target: null, error: "The event key is ambiguous for the available scope metadata." };
  return { target: null, error: "The gateway did not provide enough canonical event routing metadata." };
}

// dist/present_interaction.js
import { ToolCallWordsList } from "@abstractframework/ui-kit";

// dist/public_approval.js
var record2 = (v) => v && typeof v === "object" && !Array.isArray(v) ? v : null;
var text4 = (v) => typeof v === "string" ? v.trim() : "";
function publicApprovalRequest(calls, value, runId) {
  const actions = calls.map((call) => {
    let args = record2(call.arguments);
    if (!args && typeof call.arguments === "string") {
      try {
        args = record2(JSON.parse(call.arguments));
      } catch {
      }
    }
    const a = args || {};
    const path = text4(a.file_path) || text4(a.path);
    switch (call.name) {
      case "fetch_url":
      case "skim_url": {
        const method = a.method === void 0 ? "GET" : text4(a.method).toUpperCase();
        const displayOptions = /* @__PURE__ */ new Set(["url", "method", "timeout", "include_binary_preview", "render_js", "keep_links", "include_full_content"]);
        const extraRequestData = Object.keys(a).some((key) => !displayOptions.has(key) && a[key] !== void 0 && a[key] !== null);
        if (!["GET", "HEAD"].includes(method) || extraRequestData)
          return { kind: "unknown", label: "A website request that needs a closer look", target: text4(a.url) };
        return { kind: "page", label: "Read a webpage", target: text4(a.url) };
      }
      case "web_search":
      case "skim_websearch":
        return { kind: "search", label: "Search the web", target: text4(a.query) };
      case "read_file":
        return { kind: "read", label: "Read a file", target: path };
      case "write_file":
        return { kind: "write", label: "Write to a file \u2014 this can replace its contents", target: path };
      case "edit_file":
        return { kind: "edit", label: "Change a file\u2019s contents", target: path };
      case "list_files":
        return { kind: "folder", label: "Look through a folder", target: text4(a.directory_path) || path || "The current workspace" };
      default:
        return { kind: "unknown", label: "An action that needs a closer look", target: "" };
    }
  });
  const kind = actions[0]?.kind;
  const same = actions.length > 0 && actions.every((a) => a.kind === kind);
  const questions = {
    page: ["May I read this webpage?", `May I read these ${actions.length} webpages?`],
    search: ["May I search the web?", "May I make these web searches?"],
    read: ["May I read this file?", `May I read these ${actions.length} files?`],
    write: ["May I write to this file?", `May I write to these ${actions.length} files?`],
    edit: ["May I change this file?", `May I change these ${actions.length} files?`],
    folder: ["May I look through this folder?", "May I look through these folders?"]
  };
  const reviewRequired = !actions.length || actions.some((a) => a.kind === "unknown" || !a.target);
  const question = same && questions[kind] ? questions[kind][actions.length === 1 ? 0 : 1] : "May I do these things?";
  const source = record2(value);
  const ids = calls.map((c) => text4(c.call_id) || text4(c.id));
  const bound = source && Array.isArray(source.call_ids) ? source.call_ids : [];
  const explanation = source && text4(runId) && text4(source.run_id) === runId && text4(source.update_id) && typeof source.iteration === "number" && Number.isInteger(source.iteration) && source.iteration > 0 && ids.length > 0 && ids.every(Boolean) && new Set(ids).size === ids.length && bound.length === ids.length && new Set(bound).size === bound.length && bound.every((id) => typeof id === "string" && ids.includes(id)) && text4(source.text) && text4(source.text).length <= 600 && !/```\s*diary\b|<\s*diary\b|<\s*think\b/i.test(text4(source.text)) ? { text: text4(source.text), updateId: text4(source.update_id) } : void 0;
  return { question, actions, reviewRequired, ...explanation ? { explanation } : {} };
}

// dist/present_interaction.js
function isReplayInteraction(value) {
  const v = value;
  return Boolean(v && typeof v === "object" && typeof v.run_id === "string" && typeof v.wait_key === "string" && !("wait" in v));
}
function presentInteraction(input, controller, options = {}) {
  if (!input)
    return null;
  const raw = isReplayInteraction(input) ? replayInteractionWait(input) : input;
  const wait = raw.wait;
  const id = `${raw.runId}:${wait.wait_key}:${raw.stepId || ""}`;
  const details = wait.details || {};
  if (details.mode === "approval_required" || details.kind === "tool_approval") {
    const calls = Array.isArray(details.tool_calls) ? details.tool_calls : [];
    const target2 = { runId: raw.runId, waitKey: String(wait.wait_key || ""), stepId: raw.stepId };
    const names = [...new Set(calls.map((call) => String(call?.name || "tool")))];
    const onPermissionsAll = options.onPermissionsAll;
    const onAllowForSession = options.onAllowForSession;
    const scope2 = String(options.approveAllScope || "").trim();
    const remember = options.remember?.(names) || void 0;
    const L2 = WORKFLOW_INTERACTION_LABELS;
    const hostChatGrant = onAllowForSession ? {
      approveForSessionLabel: L2.allowForChat,
      approveForSessionDescription: "Allow for this chat approves this batch and the enabled tools for the rest of this chat. Unchecked tools stay unavailable; questions still need your answer.",
      onApproveForSession: async () => {
        let grant;
        await controller.approveWithPolicyChange(target2, () => {
          grant = onAllowForSession();
        });
        if (grant)
          await grant.catch((error) => {
            throw new Error(`This batch was allowed, but "Allow for this chat" could not be turned on: ${error instanceof Error ? error.message : String(error)}`);
          });
      }
    } : {};
    let sessionFields = hostChatGrant;
    let refusedByPolicy = [];
    const policy = options.sessionPolicy;
    if (policy) {
      const approveAllForSession = controller.approveAllForSession;
      const approveKindForSession = controller.approveKindForSession;
      const denyToolForSession = controller.denyToolForSession;
      const denyKindForSession = controller.denyKindForSession;
      const sessionPolicyStatus = controller.sessionPolicyStatus;
      if (typeof approveAllForSession !== "function" || typeof approveKindForSession !== "function" || typeof denyToolForSession !== "function" || typeof denyKindForSession !== "function" || typeof sessionPolicyStatus !== "function")
        throw new Error("presentInteraction: sessionPolicy needs a WorkflowSessionController (approveAllForSession, approveKindForSession, denyToolForSession, denyKindForSession, sessionPolicyStatus).");
      const status = sessionPolicyStatus.call(controller);
      const ask = policy.ask ? [...policy.ask] : void 0;
      const applies = (stored, which) => {
        const words = String(stored?.scope?.[which] || "").trim();
        return words ? `Applies: ${words}` : L2.noScopeNote;
      };
      const covered = (result) => ({
        outcomeNote: [sessionPolicyClampedText(result?.clamped), applies(result, "approve")].filter(Boolean).join(" ")
      });
      const denied = (result) => ({ outcomeNote: `${L2.denyForChatNote} ${applies(result, "deny")}` });
      const notCovered = sessionPolicyClampedText(status.clamped);
      if (status.mode === "unavailable") {
        sessionFields = { scopeNote: L2.unavailablePolicyNote(status.reason || "") };
      } else if (status.mode === "gateway") {
        const toolsets = [
          ...new Set(calls.map((call) => String(call?.toolset || "").trim() || String(policy.toolsetOf?.(String(call?.name || "")) || "").trim()).filter(Boolean))
        ];
        const askNames = (ask || []).map((name) => String(name).trim()).filter(Boolean);
        const asking = askNames.length ? `Tools set to Ask keep asking: ${askNames.join(", ")}.` : "Nothing is set to Ask, so tools that reach destinations the model picks (fetch_url, browser_probe, send_email) are included.";
        const stored = status.policy;
        refusedByPolicy = stored ? names.filter((name) => Object.prototype.hasOwnProperty.call(stored.deny || {}, name)) : [];
        sessionFields = {
          approveForSessionLabel: L2.allowForChat,
          // The real button labels, never a "<toolset>" placeholder; alternatives, each with
          // its reach (release-closing polish).
          approveForSessionDescription: toolsets.length ? `Each of ${(() => {
            const items = [`\u201C${L2.allowForChat}\u201D (every tool)`, ...toolsets.map((kind) => `\u201C${L2.allowKindForChat(kind)}\u201D (that toolset only)`)];
            return `${items.slice(0, -1).join(", ")} or ${items[items.length - 1]}`;
          })()} approves this batch and stores a policy for this chat on the gateway: the later tool calls it covers, in every run of this chat, run without asking, until the policy is reset. ${asking} Tools the gateway does not authorize stay uncovered.` : `\u201C${L2.allowForChat}\u201D approves this batch and stores a policy for this chat on the gateway: later tool calls of every run of this chat run without asking, until the policy is reset. ${asking} Tools the gateway does not authorize stay uncovered.`,
          // Always visible under the decisions (the full sentences are in the disclosure): what
          // a broad grant reaches, and the Ask warning, before any click.
          broadScopeSummary: `The broader choices keep allowing later tool calls of this chat until the policy is reset. ${asking}`,
          onApproveForSession: async () => covered(await approveAllForSession.call(controller, target2, { ...policy.maxRiskRank !== void 0 ? { maxRiskRank: policy.maxRiskRank } : {}, ...ask ? { ask } : {} })),
          approveKinds: toolsets.map((kind) => ({
            kind,
            label: L2.allowKindForChat(kind),
            onApprove: async () => covered(await approveKindForSession.call(controller, target2, kind, ask ? { ask } : {}))
          })),
          denyOptions: [
            ...names.map((name) => ({
              key: `tool:${name}`,
              label: L2.denyToolForChat(name),
              onDeny: async () => denied(await denyToolForSession.call(controller, target2, name, ask ? { ask } : {}))
            })),
            ...toolsets.map((kind) => ({
              key: `kind:${kind}`,
              label: L2.denyKindForChat(kind),
              onDeny: async () => denied(await denyKindForSession.call(controller, target2, kind, ask ? { ask } : {}))
            }))
          ],
          ...refusedByPolicy.length ? { deniedNote: `Denied by this chat's policy: ${refusedByPolicy.join(", ")}. The gateway refuses ${refusedByPolicy.length === 1 ? "it" : "them"} even if allowed once.` } : {},
          ...stored ? {
            policySummary: `This chat's policy: ${Object.keys(stored.approve || {}).length} tools allowed without asking, ${Object.keys(stored.deny || {}).length} denied. ${applies(stored, "approve")}`
          } : {},
          ...notCovered ? { notCovered } : {}
        };
      } else {
        sessionFields = onAllowForSession ? { ...hostChatGrant, scopeNote: L2.localChatPolicyNote } : {
          // The grant ends with the run: the button says so (ADR 0001 §5).
          approveForSessionLabel: L2.allowForRun,
          onApproveForSession: async () => {
            await approveAllForSession.call(controller, target2, {});
          },
          scopeNote: L2.localRunPolicyNote
        };
      }
    }
    return {
      id,
      kind: "tool-approval",
      title: `${calls.length || "Requested"} ${calls.length === 1 ? "action needs" : "actions need"} permission`,
      toolName: names.join(", ") || "the requested tools",
      publicRequest: publicApprovalRequest(calls, details.public_action, raw.runId),
      description: "Review the targets below. Allow once approves this batch only.",
      detail: _jsxs16("div", { className: "pc-approval-summary", children: [_jsx19(ToolCallWordsList, { calls: calls.map((call) => {
        const args = toolArguments(call?.arguments);
        return { name: String(call?.name || "tool"), arguments: args && typeof args === "object" && !Array.isArray(args) ? args : null };
      }), label: "Tool calls to approve", heading: "The assistant wants to use these tools:" }), _jsxs16("details", { children: [_jsx19("summary", { children: "Review full tool arguments (JSON)" }), _jsx19(JsonViewer, { value: calls.length ? calls : details })] })] }),
      approveLabel: WORKFLOW_INTERACTION_LABELS.allowOnce,
      denyLabel: WORKFLOW_INTERACTION_LABELS.deny,
      approveAllLabel: onPermissionsAll ? WORKFLOW_INTERACTION_LABELS.allowAll : void 0,
      approveAllDescription: onPermissionsAll ? `Sets permissions: all${scope2 ? ` ${scope2}` : ""}, including future turns. Unchecked tools stay unavailable; explicit Ask overrides and Gateway restrictions remain enforced. Questions still need your answer.` : void 0,
      ...onPermissionsAll ? { broadScopeSummary: `\u201C${WORKFLOW_INTERACTION_LABELS.allowAll}\u201D changes your tool permissions for future turns too.` } : {},
      ...sessionFields,
      ...options.approveAllDisabledReason ? { disabledReason: options.approveAllDisabledReason } : {},
      ...remember ? { remember } : {},
      ...options.onDefer ? { onDefer: options.onDefer } : {},
      onApproveAll: onPermissionsAll ? async () => {
        await controller.approveWithPolicyChange(target2, () => {
          void onPermissionsAll();
        });
      } : void 0,
      onApprove: async () => {
        await controller.approve(true, target2);
        return refusedByPolicy.length ? { outcomeNote: `The gateway refuses ${refusedByPolicy.join(", ")}: denied by this chat's policy.` } : void 0;
      },
      onDeny: async () => {
        await controller.approve(false, target2);
      }
    };
  }
  const askTarget = { runId: raw.runId, waitKey: String(wait.wait_key || ""), stepId: raw.stepId };
  const question = details.question && typeof details.question === "object" && details.question.purpose === "conversation" ? details.question : null;
  const essential = question?.importance === "essential";
  const clarification = question?.importance === "clarification";
  const deadlineTime = typeof question?.deadline === "string" && Number.isFinite(Date.parse(question.deadline)) ? new Date(question.deadline).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "";
  if (wait.reason === "user" || wait.reason === "ask_user")
    return {
      id,
      kind: "ask-user",
      title: essential ? "Your answer is required" : clarification ? "A clarification for you" : "A question for you",
      ...essential ? { description: "This question needs your answer. I will keep waiting; silence does not grant permission." } : clarification ? { description: `${deadlineTime ? `Answer by ${deadlineTime}. ` : ""}${question.fallback ? `Without an answer: ${String(question.fallback)}` : ""}` } : {},
      prompt: String(wait.prompt || details.prompt || "How would you like to continue?"),
      allowFreeText: wait.allow_free_text !== false,
      choices: (Array.isArray(wait.choices) ? wait.choices : []).map((choice) => typeof choice === "object" && choice !== null ? {
        id: String(choice.value ?? choice.id ?? choice.label),
        label: String(choice.label ?? choice.text ?? choice.value ?? choice.id),
        description: choice.description
      } : { id: String(choice), label: String(choice) }),
      onSubmit: async (answer) => {
        await controller.resume(answer, askTarget);
      },
      ...options.allowSkip && !question ? {
        onSkip: async () => {
          await controller.resume("", askTarget);
        }
      } : {},
      ...options.onDefer ? { onDefer: options.onDefer } : {}
    };
  const key = String(wait.wait_key || "");
  if (wait.reason === "event" || key.startsWith("evt:")) {
    const command = raw.command;
    if (command) {
      const answerEvent = controller.answerEvent;
      if (typeof answerEvent !== "function")
        throw new Error("presentInteraction: an event wait from the replay view needs a WorkflowSessionController (answerEvent).");
      const eventTarget = { runId: raw.runId, waitKey: key, stepId: raw.stepId };
      return {
        id,
        kind: "event-wait",
        title: "Waiting for your input",
        eventName: key,
        prompt: String(wait.prompt || "This workflow is waiting for an event."),
        description: Array.isArray(wait.choices) && wait.choices.length ? `Expected: ${wait.choices.map((choice) => typeof choice === "object" && choice !== null ? String(choice.label ?? choice.value ?? "") : String(choice)).join(", ")}` : "The data you send resumes this wait.",
        initialPayload: "{}",
        payloadLabel: "Event data (JSON)",
        sendLabel: "Send",
        onSend: async (text5) => {
          await answerEvent.call(controller, JSON.parse(text5 || "{}"), eventTarget);
        }
      };
    }
    const routing = resolveWorkflowEventTarget(raw, options.records || [], options.currentRun ?? null);
    const target2 = routing.target;
    const eventName = target2?.name || "";
    return {
      id,
      kind: "event-wait",
      title: target2 ? "Waiting for an event" : "Event routing unavailable",
      eventName,
      prompt: String(wait.prompt || `This workflow will continue when \u201C${eventName || "its trigger"}\u201D arrives.`),
      description: target2 ? "You can also send the expected event here." : `This event cannot be sent safely. ${routing.error}`,
      initialPayload: "{}",
      payloadLabel: "Event data (JSON)",
      sendLabel: "Send event",
      onSend: async (text5) => {
        if (!target2)
          throw new Error(routing.error);
        const payload = JSON.parse(text5 || "{}");
        const event = { name: target2.name, scope: target2.scope, payload };
        if (target2.scope === "session")
          event.session_id = target2.scopeId;
        else if (target2.scope === "workflow")
          event.workflow_id = target2.scopeId;
        else if (target2.scope === "run")
          event.run_id = target2.scopeId;
        await controller.emitEvent(event);
      }
    };
  }
  return null;
}
export {
  AvatarConversation,
  ChatComposer,
  ChatMessageCard,
  ChatThread,
  DEFAULT_CONVERSATION_CUES,
  ToolActivity,
  ToolActivityGroup,
  WorkflowChat,
  WorkflowInteractionPanel,
  conversationCueStep,
  conversationMessages,
  conversationNarrationStep,
  conversationPages,
  conversationReply,
  conversationSnapshot,
  conversationState,
  outputArtifacts,
  playConversationCue,
  presentInteraction,
  publicApprovalRequest,
  publicUpdate,
  submittedArtifacts,
  useAvatarConversationPreferences,
  useWorkflowSession
};
