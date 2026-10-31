// dist/session_card.js
import { jsx as _jsx2, jsxs as _jsxs2 } from "react/jsx-runtime";

// dist/icon.js
import { jsx as _jsx, Fragment as _Fragment, jsxs as _jsxs } from "react/jsx-runtime";
var GRID_16 = /* @__PURE__ */ new Set(["board", "inbox", "server", "agent", "playCircle", "list", "gear"]);
function paths(name) {
  switch (name) {
    case "chat":
      return _jsx("path", { d: "M21 15a2 2 0 0 1-2 2H8l-5 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" });
    case "plus":
      return _jsxs(_Fragment, { children: [_jsx("path", { d: "M12 5v14" }), _jsx("path", { d: "M5 12h14" })] });
    case "history":
      return _jsxs(_Fragment, { children: [_jsx("circle", { cx: "12", cy: "12", r: "9" }), _jsx("path", { d: "M12 7v5l3 3" })] });
    case "refresh":
      return _jsxs(_Fragment, { children: [_jsx("path", { d: "M21 12a9 9 0 0 0-15.5-6.4L3 8" }), _jsx("path", { d: "M3 3v5h5" }), _jsx("path", { d: "M3 12a9 9 0 0 0 15.5 6.4L21 16" }), _jsx("path", { d: "M21 21v-5h-5" })] });
    case "cog":
      return _jsxs(_Fragment, { children: [_jsx("path", { d: "M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" }), _jsx("circle", { cx: "12", cy: "12", r: "3" })] });
    case "activity":
      return _jsx("path", { d: "M22 12h-4l-3 9L9 3l-3 9H2" });
    case "settings":
      return _jsxs(_Fragment, { children: [_jsx("path", { d: "M4 6h16" }), _jsx("circle", { cx: "8", cy: "6", r: "2" }), _jsx("path", { d: "M4 12h16" }), _jsx("circle", { cx: "16", cy: "12", r: "2" }), _jsx("path", { d: "M4 18h16" }), _jsx("circle", { cx: "10", cy: "18", r: "2" })] });
    case "user":
      return _jsxs(_Fragment, { children: [_jsx("circle", { cx: "12", cy: "8", r: "4" }), _jsx("path", { d: "M4 21a8 8 0 0 1 16 0" })] });
    case "bot":
      return _jsxs(_Fragment, { children: [_jsx("path", { d: "M12 2v3" }), _jsx("rect", { x: "5", y: "6", width: "14", height: "14", rx: "3" }), _jsx("circle", { cx: "9", cy: "13", r: "1", fill: "currentColor", stroke: "none" }), _jsx("circle", { cx: "15", cy: "13", r: "1", fill: "currentColor", stroke: "none" }), _jsx("path", { d: "M9 17h6" })] });
    case "paperclip":
      return _jsx("path", { d: "M21.44 11.05l-9.19 9.19a5.5 5.5 0 0 1-7.78-7.78l9.19-9.19a3.5 3.5 0 0 1 4.95 4.95l-9.2 9.19a1.5 1.5 0 0 1-2.12-2.12l8.49-8.48" });
    case "mic":
      return _jsxs(_Fragment, { children: [_jsx("path", { d: "M12 14a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3z" }), _jsx("path", { d: "M19 11a7 7 0 0 1-14 0" }), _jsx("path", { d: "M12 18v4" }), _jsx("path", { d: "M8 22h8" })] });
    case "speaker":
      return _jsxs(_Fragment, { children: [_jsx("path", { d: "M11 5L6 9H2v6h4l5 4V5z" }), _jsx("path", { d: "M15.5 8.5a5 5 0 0 1 0 7" }), _jsx("path", { d: "M18 6a9 9 0 0 1 0 12" })] });
    case "pause":
      return _jsxs(_Fragment, { children: [_jsx("rect", { x: "6", y: "4", width: "4", height: "16", rx: "1", fill: "currentColor", stroke: "none" }), _jsx("rect", { x: "14", y: "4", width: "4", height: "16", rx: "1", fill: "currentColor", stroke: "none" })] });
    case "terminal":
      return _jsxs(_Fragment, { children: [_jsx("rect", { x: "3", y: "4", width: "18", height: "16", rx: "2", ry: "2" }), _jsx("path", { d: "M7 9l3 3-3 3" }), _jsx("path", { d: "M12 15h5" })] });
    case "edit":
      return _jsxs(_Fragment, { children: [_jsx("path", { d: "M12 20h9" }), _jsx("path", { d: "M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" })] });
    case "download":
      return _jsxs(_Fragment, { children: [_jsx("path", { d: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" }), _jsx("path", { d: "M7 10l5 5 5-5" }), _jsx("path", { d: "M12 15V3" })] });
    case "loader":
      return _jsx("path", { d: "M21 12a9 9 0 1 1-3.3-6.9" });
    case "info":
      return _jsxs(_Fragment, { children: [_jsx("circle", { cx: "12", cy: "12", r: "10" }), _jsx("path", { d: "M12 16v-4" }), _jsx("circle", { cx: "12", cy: "8", r: "0.75", fill: "currentColor", stroke: "none" })] });
    case "about":
      return _jsxs(_Fragment, { children: [_jsx("circle", { cx: "12", cy: "12", r: "9" }), _jsx("circle", { cx: "12", cy: "7.5", r: "1.5", fill: "currentColor", stroke: "none" }), _jsx("path", { d: "M12 11v6" })] });
    case "warning":
      return _jsxs(_Fragment, { children: [_jsx("path", { d: "M12 3l10 18H2L12 3z" }), _jsx("path", { d: "M12 9v4" }), _jsx("circle", { cx: "12", cy: "17", r: "0.75", fill: "currentColor", stroke: "none" })] });
    case "error":
      return _jsxs(_Fragment, { children: [_jsx("circle", { cx: "12", cy: "12", r: "10" }), _jsx("path", { d: "M15 9l-6 6" }), _jsx("path", { d: "M9 9l6 6" })] });
    case "copy":
      return _jsxs(_Fragment, { children: [_jsx("rect", { x: "9", y: "9", width: "13", height: "13", rx: "2" }), _jsx("path", { d: "M5 15V5a2 2 0 0 1 2-2h10" })] });
    case "check":
      return _jsx("path", { d: "M20 6L9 17l-5-5" });
    case "x":
      return _jsxs(_Fragment, { children: [_jsx("path", { d: "M18 6L6 18" }), _jsx("path", { d: "M6 6l12 12" })] });
    case "chevronDown":
      return _jsx("path", { d: "M6 9l6 6 6-6" });
    case "chevronRight":
      return _jsx("path", { d: "M9 18l6-6-6-6" });
    case "trash":
      return _jsxs(_Fragment, { children: [_jsx("path", { d: "M3 6h18" }), _jsx("path", { d: "M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" }), _jsx("path", { d: "M6 6l1 16h10l1-16" }), _jsx("path", { d: "M10 11v6" }), _jsx("path", { d: "M14 11v6" })] });
    case "send":
      return _jsxs(_Fragment, { children: [_jsx("path", { d: "M22 2L11 13" }), _jsx("path", { d: "M22 2L15 22l-4-9-9-4 20-7z" })] });
    case "thumbsUp":
      return _jsxs(_Fragment, { children: [_jsx("path", { d: "M7 10v11" }), _jsx("path", { d: "M7 10l4.5-8a2 2 0 0 1 3.6 1.5L14 8h5.2a2 2 0 0 1 2 2.4l-1.6 8a2 2 0 0 1-2 1.6H7" })] });
    case "thumbsDown":
      return _jsxs(_Fragment, { children: [_jsx("path", { d: "M17 14V3" }), _jsx("path", { d: "M17 14l-4.5 8a2 2 0 0 1-3.6-1.5L10 16H4.8a2 2 0 0 1-2-2.4l1.6-8a2 2 0 0 1 2-1.6H17" })] });
    // The filled twins reuse the stroke twins' exact coordinates — the mitt
    // outline is CLOSED (z) and filled per-path, the stem stays a stroked
    // line — so toggling stroke↔filled never shifts a pixel.
    case "thumbsUpFilled":
      return _jsxs(_Fragment, { children: [_jsx("path", { d: "M7 10v11" }), _jsx("path", { d: "M7 10l4.5-8a2 2 0 0 1 3.6 1.5L14 8h5.2a2 2 0 0 1 2 2.4l-1.6 8a2 2 0 0 1-2 1.6H7z", fill: "currentColor", stroke: "none" })] });
    case "thumbsDownFilled":
      return _jsxs(_Fragment, { children: [_jsx("path", { d: "M17 14V3" }), _jsx("path", { d: "M17 14l-4.5 8a2 2 0 0 1-3.6-1.5L10 16H4.8a2 2 0 0 1-2-2.4l1.6-8a2 2 0 0 1 2-1.6H17z", fill: "currentColor", stroke: "none" })] });
    case "board":
      return _jsxs(_Fragment, { children: [_jsx("rect", { x: "1.5", y: "2", width: "3.6", height: "12", rx: "1" }), _jsx("rect", { x: "6.2", y: "2", width: "3.6", height: "8.5", rx: "1" }), _jsx("rect", { x: "10.9", y: "2", width: "3.6", height: "5.5", rx: "1" })] });
    case "inbox":
      return _jsxs(_Fragment, { children: [_jsx("path", { d: "M2 9.5 L4 3.5 h8 l2 6" }), _jsx("path", { d: "M2 9.5 v3 h12 v-3" }), _jsx("path", { d: "M2 9.5 h3.4 l1 1.6 h3.2 l1-1.6 H14" })] });
    case "server":
      return _jsxs(_Fragment, { children: [_jsx("rect", { x: "2", y: "2.5", width: "12", height: "4.6", rx: "1.2" }), _jsx("rect", { x: "2", y: "8.9", width: "12", height: "4.6", rx: "1.2" }), _jsx("circle", { cx: "4.6", cy: "4.8", r: "0.8", fill: "currentColor", stroke: "none" }), _jsx("circle", { cx: "4.6", cy: "11.2", r: "0.8", fill: "currentColor", stroke: "none" })] });
    case "agent":
      return _jsxs(_Fragment, { children: [_jsx("rect", { x: "3", y: "4.5", width: "10", height: "8", rx: "2" }), _jsx("path", { d: "M8 4.5V2.2" }), _jsx("circle", { cx: "8", cy: "1.8", r: "0.9", fill: "currentColor", stroke: "none" }), _jsx("circle", { cx: "5.8", cy: "8.4", r: "0.9", fill: "currentColor", stroke: "none" }), _jsx("circle", { cx: "10.2", cy: "8.4", r: "0.9", fill: "currentColor", stroke: "none" })] });
    case "playCircle":
      return _jsxs(_Fragment, { children: [_jsx("circle", { cx: "8", cy: "8", r: "6.2" }), _jsx("path", { d: "M6.5 5.6 L11 8 L6.5 10.4 Z", fill: "currentColor", stroke: "none" })] });
    case "list":
      return _jsxs(_Fragment, { children: [_jsx("path", { d: "M2.5 4h11" }), _jsx("path", { d: "M2.5 8h11" }), _jsx("path", { d: "M2.5 12h7" })] });
    case "gear":
      return _jsxs(_Fragment, { children: [_jsx("circle", { cx: "8", cy: "8", r: "2.2" }), _jsx("path", { d: "M8 1.6v2" }), _jsx("path", { d: "M8 12.4v2" }), _jsx("path", { d: "M1.6 8h2" }), _jsx("path", { d: "M12.4 8h2" }), _jsx("path", { d: "M3.5 3.5l1.4 1.4" }), _jsx("path", { d: "M11.1 11.1l1.4 1.4" }), _jsx("path", { d: "M12.5 3.5l-1.4 1.4" }), _jsx("path", { d: "M4.9 11.1l-1.4 1.4" })] });
    case "sparkle":
      return _jsxs(_Fragment, { children: [_jsx("path", { d: "M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" }), _jsx("path", { d: "M18.5 15.5l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z" })] });
    case "contrast":
      return _jsxs(_Fragment, { children: [_jsx("circle", { cx: "12", cy: "12", r: "9" }), _jsx("path", { d: "M12 3a9 9 0 0 1 0 18z", fill: "currentColor", stroke: "none" })] });
    case "logout":
      return _jsxs(_Fragment, { children: [_jsx("path", { d: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" }), _jsx("path", { d: "M16 17l5-5-5-5" }), _jsx("path", { d: "M21 12H9" })] });
    case "play":
      return _jsx("path", { d: "M7 4.5v15a1 1 0 0 0 1.5.86l12-7.5a1 1 0 0 0 0-1.72l-12-7.5A1 1 0 0 0 7 4.5z", fill: "currentColor", stroke: "none" });
    case "stop":
      return _jsx("rect", { x: "5", y: "5", width: "14", height: "14", rx: "2", fill: "currentColor", stroke: "none" });
    case "folder":
      return _jsx("path", { d: "M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" });
    case "file":
      return _jsxs(_Fragment, { children: [_jsx("path", { d: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" }), _jsx("path", { d: "M14 2v6h6" })] });
    case "archive":
      return _jsxs(_Fragment, { children: [_jsx("rect", { x: "2", y: "3", width: "20", height: "5", rx: "1" }), _jsx("path", { d: "M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8" }), _jsx("path", { d: "M10 12h4" })] });
    case "unarchive":
      return _jsxs(_Fragment, { children: [_jsx("rect", { x: "2", y: "3", width: "20", height: "5", rx: "1" }), _jsx("path", { d: "M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8" }), _jsx("path", { d: "M12 18v-6" }), _jsx("path", { d: "m9 14 3-3 3 3" })] });
    case "wrench":
      return _jsx("path", { d: "M14.5 6.5 18 3a6 6 0 0 0-7.6 7.6L3 18a2.1 2.1 0 0 0 3 3l7.4-7.4A6 6 0 0 0 21 6l-3.5 3.5-3-3Z" });
    case "clock":
      return _jsxs(_Fragment, { children: [_jsx("circle", { cx: "12", cy: "12", r: "10" }), _jsx("path", { d: "M12 6v6h4" })] });
    case "book":
      return _jsxs(_Fragment, { children: [_jsx("path", { d: "M2 4h6a4 4 0 0 1 4 4v13a3 3 0 0 0-3-3H2z" }), _jsx("path", { d: "M22 4h-6a4 4 0 0 0-4 4v13a3 3 0 0 1 3-3h7z" })] });
    case "compose":
      return _jsxs(_Fragment, { children: [_jsx("path", { d: "M12 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" }), _jsx("path", { d: "M18.4 2.6a2.1 2.1 0 0 1 3 3L12 15l-4 1 1-4z" })] });
    case "image":
      return _jsxs(_Fragment, { children: [_jsx("rect", { x: "3", y: "3", width: "18", height: "18", rx: "2" }), _jsx("circle", { cx: "9", cy: "9", r: "2" }), _jsx("path", { d: "M21 15l-3.1-3.1a2 2 0 0 0-2.8 0L6 21" })] });
    case "video":
      return _jsxs(_Fragment, { children: [_jsx("rect", { x: "2", y: "6", width: "14", height: "12", rx: "2" }), _jsx("path", { d: "M16 10.5l5.2-3.1a.5.5 0 0 1 .8.4v8.4a.5.5 0 0 1-.8.4L16 13.5" })] });
    case "camera":
      return _jsxs(_Fragment, { children: [_jsx("path", { d: "M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3z" }), _jsx("circle", { cx: "12", cy: "13", r: "3" })] });
    case "music":
      return _jsxs(_Fragment, { children: [_jsx("path", { d: "M9 18V5l12-2v13" }), _jsx("circle", { cx: "6", cy: "18", r: "3" }), _jsx("circle", { cx: "18", cy: "16", r: "3" })] });
    case "database":
      return _jsxs(_Fragment, { children: [_jsx("ellipse", { cx: "12", cy: "5", rx: "9", ry: "3" }), _jsx("path", { d: "M3 5v14a9 3 0 0 0 18 0V5" }), _jsx("path", { d: "M3 12a9 3 0 0 0 18 0" })] });
    case "branch":
      return _jsxs(_Fragment, { children: [_jsx("path", { d: "M6 3v12" }), _jsx("circle", { cx: "18", cy: "6", r: "3" }), _jsx("circle", { cx: "6", cy: "18", r: "3" }), _jsx("path", { d: "M18 9a9 9 0 0 1-9 9" })] });
    case "loop":
      return _jsxs(_Fragment, { children: [_jsx("path", { d: "M17 2l4 4-4 4" }), _jsx("path", { d: "M3 11v-1a4 4 0 0 1 4-4h14" }), _jsx("path", { d: "M7 22l-4-4 4-4" }), _jsx("path", { d: "M21 13v1a4 4 0 0 1-4 4H3" })] });
    case "variable":
      return _jsxs(_Fragment, { children: [_jsx("path", { d: "M8 21s-4-3-4-9 4-9 4-9" }), _jsx("path", { d: "M16 3s4 3 4 9-4 9-4 9" }), _jsx("path", { d: "M15 9l-6 6" }), _jsx("path", { d: "M9 9l6 6" })] });
    case "minus":
      return _jsx("path", { d: "M5 12h14" });
    case "divide":
      return _jsxs(_Fragment, { children: [_jsx("circle", { cx: "12", cy: "6", r: "1.25", fill: "currentColor", stroke: "none" }), _jsx("path", { d: "M5 12h14" }), _jsx("circle", { cx: "12", cy: "18", r: "1.25", fill: "currentColor", stroke: "none" })] });
    case "function":
      return _jsxs(_Fragment, { children: [_jsx("rect", { x: "3", y: "3", width: "18", height: "18", rx: "2" }), _jsx("path", { d: "M9 17c2 0 2.8-1 2.8-2.8V10c0-2 1-3.3 3.2-3" }), _jsx("path", { d: "M9 11.2h5.7" })] });
    case "zoomIn":
      return _jsxs(_Fragment, { children: [_jsx("circle", { cx: "11", cy: "11", r: "8" }), _jsx("path", { d: "M21 21l-4.35-4.35" }), _jsx("path", { d: "M11 8v6" }), _jsx("path", { d: "M8 11h6" })] });
    case "zoomOut":
      return _jsxs(_Fragment, { children: [_jsx("circle", { cx: "11", cy: "11", r: "8" }), _jsx("path", { d: "M21 21l-4.35-4.35" }), _jsx("path", { d: "M8 11h6" })] });
    case "fitView":
      return _jsxs(_Fragment, { children: [_jsx("path", { d: "M8 3H5a2 2 0 0 0-2 2v3" }), _jsx("path", { d: "M21 8V5a2 2 0 0 0-2-2h-3" }), _jsx("path", { d: "M3 16v3a2 2 0 0 0 2 2h3" }), _jsx("path", { d: "M16 21h3a2 2 0 0 0 2-2v-3" })] });
    case "lock":
      return _jsxs(_Fragment, { children: [_jsx("rect", { x: "4", y: "11", width: "16", height: "10", rx: "2" }), _jsx("path", { d: "M8 11V7a4 4 0 0 1 8 0v4" })] });
    default:
      return null;
  }
}
function Icon({ name, size = 16, className, title, ...props }) {
  const aria_hidden = title ? void 0 : true;
  const is16 = GRID_16.has(name);
  return _jsxs("svg", { width: size, height: size, viewBox: is16 ? "0 0 16 16" : "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: is16 ? 1.4 : 2, strokeLinecap: "round", strokeLinejoin: "round", className, "aria-hidden": aria_hidden, role: title ? "img" : "presentation", ...props, children: [title ? _jsx("title", { children: title }) : null, paths(name)] });
}

// dist/relative_time.js
var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
var MINUTE = 6e4;
var HOUR = 60 * MINUTE;
var DAY = 24 * HOUR;
function timeValueMs(ts) {
  if (ts === null || ts === void 0 || ts === "")
    return NaN;
  if (ts instanceof Date)
    return ts.getTime();
  if (typeof ts === "number")
    return Number.isFinite(ts) ? ts < 1e12 ? ts * 1e3 : ts : NaN;
  const text = String(ts).trim();
  if (/^\d+(\.\d+)?$/.test(text))
    return timeValueMs(Number(text));
  return Date.parse(text);
}
function pad(n) {
  return n < 10 ? `0${n}` : String(n);
}
function formatShortDate(ts, nowMs) {
  const ms = timeValueMs(ts);
  if (!Number.isFinite(ms))
    return "";
  const d = new Date(ms);
  const sameYear = d.getFullYear() === new Date(nowMs).getFullYear();
  return `${MONTHS[d.getMonth()]} ${d.getDate()}${sameYear ? "" : `, ${d.getFullYear()}`}`;
}
function formatExactTime(ts) {
  const ms = timeValueMs(ts);
  if (!Number.isFinite(ms))
    return "";
  const d = new Date(ms);
  return `${MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}, ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
function formatRelativeTime(ts, nowMs) {
  const ms = timeValueMs(ts);
  if (!Number.isFinite(ms) || !Number.isFinite(nowMs))
    return "";
  const delta = nowMs - ms;
  if (delta < 0) {
    const ahead = -delta;
    if (ahead < MINUTE)
      return "due now";
    if (ahead < HOUR)
      return `in ${Math.round(ahead / MINUTE)} min`;
    if (ahead < DAY)
      return `in ${Math.round(ahead / HOUR)} h`;
    const days2 = Math.round(ahead / DAY);
    return days2 < 7 ? `in ${days2} ${days2 === 1 ? "day" : "days"}` : formatShortDate(ms, nowMs);
  }
  if (delta < MINUTE)
    return "just now";
  if (delta < HOUR)
    return `${Math.floor(delta / MINUTE)} min ago`;
  if (delta < DAY)
    return `${Math.floor(delta / HOUR)} h ago`;
  const days = Math.floor(delta / DAY);
  if (days === 1)
    return "yesterday";
  if (days < 7)
    return `${days} days ago`;
  return formatShortDate(ms, nowMs);
}

// dist/session_card.js
function SessionCard(p) {
  const status = [p.needsAttention ? "Needs you" : "", p.unread ? "New messages" : "", p.working ? "Working" : ""].filter(Boolean).join(". ");
  const marker = p.needsAttention ? "attention" : p.working ? "working" : p.unread ? "unread" : "";
  const count = (n) => typeof n === "number" && Number.isSafeInteger(n) && n >= 0;
  const stamp = formatRelativeTime(p.updatedAt, p.nowMs);
  const number = (n) => `${p.countsPartial ? "\u2265" : ""}${n}`;
  const label = (n, word) => `${p.countsPartial ? "At least " : ""}${n} ${word}${n === 1 ? "" : "s"}`;
  const description = [status, count(p.turnCount) ? label(p.turnCount, "turn") : "", count(p.toolCount) && p.toolCount > 0 ? label(p.toolCount, "tool call") : "", stamp].filter(Boolean).join(". ");
  return _jsxs2("div", { className: `af-session-card${p.className ? ` ${p.className}` : ""}`, "data-selected": p.selected || void 0, "data-unread": p.unread || void 0, "data-attention": p.needsAttention || void 0, "data-working": p.working || void 0, children: [_jsxs2("button", { type: "button", className: "af-session-card__open", "data-session-id": p.sessionId, disabled: p.disabled, "aria-current": p.selected ? "page" : void 0, "aria-label": `${p.title}${description ? `. ${description}` : ""}`, onClick: p.onOpen, children: [_jsxs2("span", { className: "af-session-card__heading", children: [marker && _jsx2("span", { className: `af-session-card__marker is-${marker}`, "aria-hidden": "true" }), _jsx2("span", { className: "af-session-card__title", title: p.title, children: p.title })] }), _jsxs2("span", { className: "af-session-card__meta", children: [count(p.turnCount) && _jsxs2("span", { "aria-label": label(p.turnCount, "turn"), title: label(p.turnCount, "turn"), children: [_jsx2(Icon, { name: "chat", size: 14 }), _jsx2("span", { "aria-hidden": "true", children: number(p.turnCount) })] }), count(p.toolCount) && p.toolCount > 0 && _jsxs2("span", { "aria-label": label(p.toolCount, "tool call"), title: label(p.toolCount, "tool call"), children: [_jsx2(Icon, { name: "wrench", size: 14 }), _jsx2("span", { "aria-hidden": "true", children: number(p.toolCount) })] }), p.needsAttention ? _jsx2("span", { className: "af-session-card__attention", children: "Needs you" }) : stamp && _jsxs2("span", { className: "af-session-card__time", title: formatExactTime(p.updatedAt), children: [_jsx2(Icon, { name: "clock", size: 14 }), _jsx2("span", { children: stamp })] })] })] }), p.onArchive && _jsx2("button", { type: "button", className: "af-session-card__archive", "aria-label": `Archive ${p.title}`, title: "Archive conversation", disabled: p.disabled || p.archiveDisabled, onClick: p.onArchive, children: _jsx2(Icon, { name: "archive", size: 16 }) })] });
}

// dist/session_activity.js
function sessionContentRevision(runId, status) {
  return JSON.stringify([runId, ["completed", "failed", "cancelled"].includes(status.toLowerCase()) ? status.toLowerCase() : "request"]);
}
function sessionNeedsAttention(run) {
  const wait = run.waiting && typeof run.waiting === "object" ? run.waiting : {};
  return run.status === "waiting" && (wait.reason === "user" || run.wait_reason === "user");
}
function sessionActivityFromRuns(body) {
  const root = body && typeof body === "object" ? body : {};
  const rows = Array.isArray(body) ? body : Array.isArray(root.items) ? root.items : Array.isArray(root.runs) ? root.runs : [];
  const groups = /* @__PURE__ */ new Map();
  for (const row of rows) {
    if (!row || typeof row !== "object" || row.parent_run_id || typeof row.session_id !== "string" || typeof row.run_id !== "string")
      continue;
    const list = groups.get(row.session_id) ?? [];
    list.push(row);
    groups.set(row.session_id, list);
  }
  const out = /* @__PURE__ */ Object.create(null);
  const time = (r) => Date.parse(String(r.created_at || r.updated_at || "")) || 0;
  for (const [id, runs] of groups) {
    runs.sort((a, b) => time(b) - time(a));
    const latest = runs[0];
    const tools = runs.map((r) => r.tool_calls);
    out[id] = {
      revision: sessionContentRevision(String(latest.run_id), String(latest.status || "")),
      updatedAt: String(latest.updated_at || latest.created_at || ""),
      content: runs.map((r) => ({ sessionId: id, runId: String(r.run_id), status: String(r.status || ""), revision: sessionContentRevision(String(r.run_id), String(r.status || "")), updatedAt: String(r.updated_at || r.created_at || "") })),
      needsAttention: runs.some(sessionNeedsAttention),
      working: runs.some((r) => ["running", "queued", "pending"].includes(String(r.status))),
      ...tools.every((n) => typeof n === "number" && Number.isSafeInteger(n) && n >= 0) ? { toolCount: tools.reduce((a, b) => a + b, 0) } : {}
    };
  }
  return out;
}
function sessionReadScope(connection) {
  const user = connection?.gateway?.principal?.user_id;
  if (!user || !connection?.gateway_url)
    return "";
  let gateway;
  try {
    const url = new URL(connection.gateway_url);
    url.username = "";
    url.password = "";
    url.search = "";
    url.hash = "";
    gateway = url.href.replace(/\/+$/, "");
  } catch {
    return "";
  }
  return JSON.stringify([gateway, connection.gateway?.principal?.tenant_id || "", user, connection.gateway?.principal?.runtime_id || ""]);
}
var SessionReadStore = class {
  constructor(scope, storage, now = Date.now()) {
    this.storage = storage;
    this.error = "";
    this.memory = /* @__PURE__ */ new Set();
    this.prefix = `af.session-read.v1:${encodeURIComponent(scope)}:`;
    let since = now;
    if (scope && !storage)
      this.error = "Read markers could not be saved in this browser.";
    try {
      const raw = storage?.getItem(this.prefix + "since"), saved = Number(raw);
      if (raw && Number.isFinite(saved) && saved > 0 && saved <= now)
        since = saved;
      else
        storage?.setItem(this.prefix + "since", String(now));
    } catch {
      this.error = "Read markers could not be saved in this browser.";
    }
    this.since = since;
  }
  key(p) {
    return this.prefix + encodeURIComponent(JSON.stringify(p.sessionId)) + ":" + encodeURIComponent(JSON.stringify(p.revision));
  }
  observe(p) {
    if (Date.parse(p.updatedAt) < this.since)
      this.markRead(p);
  }
  isUnread(p) {
    if (!p.sessionId || !p.revision || !Number.isFinite(Date.parse(p.updatedAt)) || Date.parse(p.updatedAt) < this.since)
      return false;
    const key = this.key(p);
    if (this.memory.has(key))
      return false;
    try {
      return !this.storage?.getItem(key);
    } catch {
      return true;
    }
  }
  markRead(p) {
    if (!p.sessionId || !p.revision)
      return;
    const key = this.key(p);
    if (this.memory.has(key))
      return;
    this.memory.add(key);
    try {
      if (this.storage?.getItem(key))
        return;
      this.storage?.setItem(key, String(Date.now()));
      const keys = [];
      for (let i = 0; i < (this.storage?.length || 0); i++) {
        const k = this.storage.key(i);
        if (k?.startsWith(this.prefix) && k !== this.prefix + "since")
          keys.push([k, Number(this.storage.getItem(k)) || 0]);
      }
      keys.sort((a, b) => b[1] - a[1]);
      for (const [k] of keys.slice(4096))
        if (k !== key)
          this.storage?.removeItem(k);
    } catch {
      this.error = "Read markers could not be saved in this browser.";
    }
    if (this.memory.size > 4096)
      this.memory.delete(this.memory.values().next().value);
  }
};
function sessionReadTarget(messages, runId, status) {
  const outcome = status === "failed" ? "Request failed." : status === "cancelled" ? "Request cancelled." : void 0;
  const role = status === "completed" ? "assistant" : "user";
  const candidates = messages.filter((m) => m.runId === runId && !m.live && !m.toolActivity && m.role === role);
  return { message: candidates[candidates.length - 1], ...outcome ? { outcome } : {} };
}

// dist/session_reads.js
import { jsx as _jsx3 } from "react/jsx-runtime";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
function useSessionReads(scope, observed = []) {
  const [, refresh] = useState(0);
  const store = useMemo(() => {
    let storage = null;
    try {
      storage = window.localStorage;
    } catch {
    }
    return new SessionReadStore(scope, scope ? storage : null);
  }, [scope]);
  useEffect(() => {
    if (scope)
      for (const p of observed)
        store.observe(p);
  }, [scope, store, observed]);
  useEffect(() => {
    const changed = (e) => {
      if (!e.key || e.key.startsWith(store.prefix))
        refresh((n) => n + 1);
    };
    window.addEventListener("storage", changed);
    return () => window.removeEventListener("storage", changed);
  }, [store]);
  const markRead = useCallback((p) => {
    if (!scope)
      return;
    store.markRead(p);
    refresh((n) => n + 1);
    window.dispatchEvent(new StorageEvent("storage", { key: store.prefix }));
  }, [scope, store]);
  return { isUnread: (p) => Boolean(scope) && store.isUnread(p), markRead, error: store.error };
}
function SessionReadMarker(p) {
  const ref = useRef(null), callback = useRef(p.onRead);
  callback.current = p.onRead;
  const { sessionId, revision, updatedAt } = p.receipt;
  useEffect(() => {
    const el = ref.current;
    if (!el || !p.enabled)
      return;
    const notify = callback.current;
    let timer, done = false;
    const visible = () => {
      if (document.hidden || !document.hasFocus() || !el.isConnected)
        return false;
      const b = el.getBoundingClientRect();
      if (b.width <= 0 || b.height <= 0 || b.top < 0 || b.bottom > window.innerHeight)
        return false;
      const hit = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
      return hit === el || Boolean(hit && el.contains(hit));
    };
    const check = () => {
      if (done)
        return;
      clearTimeout(timer);
      if (visible())
        timer = setTimeout(() => {
          if (visible()) {
            done = true;
            notify({ sessionId, revision, updatedAt });
          }
        }, 250);
    };
    const observer = new IntersectionObserver(check, { threshold: 1 });
    observer.observe(el);
    for (const event of ["focus", "blur", "resize", "pointerup", "keyup", "scroll"])
      window.addEventListener(event, check, true);
    document.addEventListener("visibilitychange", check);
    check();
    return () => {
      clearTimeout(timer);
      observer.disconnect();
      for (const event of ["focus", "blur", "resize", "pointerup", "keyup", "scroll"])
        window.removeEventListener(event, check, true);
      document.removeEventListener("visibilitychange", check);
    };
  }, [p.enabled, p.ownerKey, sessionId, revision, updatedAt]);
  return _jsx3("span", { ref, "aria-hidden": "true", className: "af-session-read-marker", style: { display: "block", width: "100%", height: 1 } });
}
export {
  SessionCard,
  SessionReadMarker,
  SessionReadStore,
  sessionActivityFromRuns,
  sessionContentRevision,
  sessionNeedsAttention,
  sessionReadScope,
  sessionReadTarget,
  useSessionReads
};
