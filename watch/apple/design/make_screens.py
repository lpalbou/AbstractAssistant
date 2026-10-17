"""AbstractAssistant for Apple Watch: screen mockups (SVG -> PNG).

Coordinate system: Apple Watch Series 11, 46 mm, 416 x 496 px logical screen.
Rendered at 2x inside a watch bezel. Style: abstractframework.ai dark palette, Inter.
"""
from __future__ import annotations

import os
import subprocess
import textwrap

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screens")  # regenerate: python3 make_screens.py (needs rsvg-convert)
os.makedirs(OUT, exist_ok=True)

W, H = 416, 496            # logical screen
R = 90                     # screen corner radius (watch display)
BZ = 36                    # bezel width
FONT = "Inter, 'Helvetica Neue', Arial, sans-serif"
MONO = "'Roboto Mono', Menlo, monospace"

BG = "#0a0a12"
CARD = "#15151f"
CARD2 = "#1b1b28"
LINE = "#2a2a3a"
INK = "#eceef5"
INK2 = "#c4c6d4"
MUTED = "#8f91a6"
INDIGO = "#818cf8"
INDIGO_D = "#4f46e5"
CYAN = "#22d3ee"
GREEN = "#34d399"
GREEN_D = "#059669"
AMBER = "#fbbf24"
AMBER_D = "#b45309"
RED = "#f87171"
RED_D = "#b91c1c"
PINK = "#f472b6"


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Screen:
    def __init__(self, name: str, title: str | None = None, time: str = "9:41"):
        self.name = name
        self.parts: list[str] = []
        self.time = time
        if title:
            self.statusbar(title)

    # ---- primitives ----
    def add(self, s: str):
        self.parts.append(s)

    def text(self, x, y, s, size=15, color=INK2, weight=500, anchor="start", family=FONT, opacity=1.0, letter=0):
        self.add(f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" font-weight="{weight}" '
                 f'fill="{color}" text-anchor="{anchor}" opacity="{opacity}" letter-spacing="{letter}">{esc(s)}</text>')

    def wrap(self, x, y, s, width_chars, size=15, color=INK2, weight=500, lh=None, family=FONT, max_lines=None):
        lh = lh or int(size * 1.3)
        lines = textwrap.wrap(s, width_chars)
        if max_lines:
            lines = lines[:max_lines]
        for i, ln in enumerate(lines):
            self.text(x, y + i * lh, ln, size=size, color=color, weight=weight, family=family)
        return y + len(lines) * lh

    def rect(self, x, y, w, h, fill=CARD, stroke=None, r=18, sw=1, opacity=1.0):
        st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}"{st} opacity="{opacity}"/>')

    def circle(self, cx, cy, r, fill, stroke=None, sw=2, opacity=1.0):
        st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
        self.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}"{st} opacity="{opacity}"/>')

    def pill(self, x, y, label, color, size=12, h=24, fill=None, text_color=None, pad=12):
        w = int(len(label) * size * 0.6 + pad * 2)
        self.rect(x, y, w, h, fill=fill or "#101018", stroke=color, r=h / 2)
        self.text(x + w / 2, y + h / 2 + size * 0.36, label, size=size, color=text_color or color, weight=700, anchor="middle")
        return w

    def button(self, x, y, w, h, label, fill, color=INK, size=18, icon=None, weight=700):
        self.rect(x, y, w, h, fill=fill, r=h / 2)
        tx = x + w / 2
        if icon:
            self.text(x + 22, y + h / 2 + size * 0.36, icon, size=size, color=color, weight=weight)
        self.text(tx, y + h / 2 + size * 0.36, label, size=size, color=color, weight=weight, anchor="middle")

    def dot(self, x, y, color, r=5, glow=True):
        if glow:
            self.circle(x, y, r * 2.2, color, opacity=0.18)
        self.circle(x, y, r, color)

    def statusbar(self, title):
        # watchOS: time top-right, title top-left
        self.text(20, 40, title, size=16, color=INK, weight=700)
        self.text(W - 20, 40, self.time, size=16, color=INK, weight=700, anchor="end")

    def chevron(self, x, y, color=MUTED):
        self.add(f'<path d="M{x} {y-7} l7 7 l-7 7" fill="none" stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>')

    def orb(self, cx, cy, r=36, mode="idle"):
        """The assistant's presence: glow, core, and a state (idle | listening | thinking)."""
        self.circle(cx, cy, r * 1.3, CYAN, opacity=0.10)
        if mode == "listening":
            for k, (rr, op) in enumerate(((1.15, 0.55), (1.45, 0.25))):
                self.circle(cx, cy, r * rr, "none", stroke=CYAN, sw=2.2, opacity=op)
        if mode == "thinking":
            import math
            for i, col in enumerate((INDIGO, CYAN, GREEN)):
                a = i * 2 * math.pi / 3 + 0.6
                self.circle(cx + math.cos(a) * r * 1.25, cy + math.sin(a) * r * 0.7, r * 0.14, col)
        self.add(f'<defs><radialGradient id="orb{int(cx)}{int(cy)}" cx="42%" cy="38%" r="60%">'
                 f'<stop offset="0" stop-color="#e0fbff"/><stop offset="0.3" stop-color="{CYAN}"/>'
                 f'<stop offset="0.72" stop-color="{INDIGO_D}"/><stop offset="1" stop-color="#1e1b4b"/></radialGradient></defs>')
        self.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#orb{int(cx)}{int(cy)})"/>')
        self.add(f'<ellipse cx="{cx - r*0.25}" cy="{cy - r*0.32}" rx="{r*0.42}" ry="{r*0.24}" fill="#ffffff" opacity="0.16"/>')

    def mic(self, cx, cy, s=1.0, color=INK):
        self.add(f'<g transform="translate({cx},{cy}) scale({s})" fill="none" stroke="{color}" stroke-width="3" stroke-linecap="round">'
                 f'<rect x="-7" y="-20" width="14" height="26" rx="7" fill="{color}" stroke="none"/>'
                 f'<path d="M-14 -2 a14 14 0 0 0 28 0"/><path d="M0 12 v8"/><path d="M-8 20 h16"/></g>')

    def check(self, cx, cy, r=34, color=GREEN):
        self.circle(cx, cy, r + 10, color, opacity=0.15)
        self.circle(cx, cy, r, color)
        self.add(f'<path d="M{cx-14} {cy+1} l9 9 l19 -20" fill="none" stroke="{BG}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>')

    def waveform(self, x, y, w, n=22, heights=None, color=CYAN):
        import math
        gap = w / n
        for i in range(n):
            h = heights[i] if heights else 10 + 26 * abs(math.sin(i * 0.9)) + 6 * abs(math.sin(i * 2.3))
            self.rect(x + i * gap, y - h / 2, gap * 0.55, h, fill=color, r=gap * 0.27)

    def row(self, y, title, sub, state_color, state_label, h=64):
        self.rect(16, y, W - 32, h, fill=CARD, r=16)
        self.dot(38, y + h / 2, state_color)
        self.text(56, y + 28, title, size=16, color=INK, weight=600)
        self.text(56, y + 48, sub, size=12.5, color=MUTED)
        self.pill(W - 16 - 12 - len(state_label) * 7.2 - 24 + 12, y + 20, state_label, state_color, size=11, h=22)

    def progress_dots(self, cx, cy, active=0, color=INDIGO):
        for i in range(3):
            self.circle(cx - 16 + i * 16, cy, 5, color, opacity=1.0 if i == active else 0.3)

    # ---- output ----
    def svg(self, bezel=True) -> str:
        if bezel:
            tw, th = W + 2 * BZ, H + 2 * BZ
            body = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{tw*2}" height="{th*2}" viewBox="0 0 {tw} {th}">',
                    '<defs><clipPath id="scr"><rect x="0" y="0" width="%d" height="%d" rx="%d"/></clipPath>'
                    '<linearGradient id="bez" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2b2b33"/><stop offset="1" stop-color="#0d0d12"/></linearGradient>'
                    '</defs>' % (W, H, R),
                    f'<rect x="4" y="4" width="{tw-8}" height="{th-8}" rx="{R+BZ-6}" fill="url(#bez)" stroke="#3a3a44" stroke-width="2"/>',
                    f'<rect x="{tw-14}" y="{th*0.30}" width="12" height="52" rx="6" fill="#2a2a33"/>',  # crown
                    f'<rect x="{tw-12}" y="{th*0.46}" width="10" height="70" rx="5" fill="#23232b"/>',  # side button
                    f'<g transform="translate({BZ},{BZ})" clip-path="url(#scr)">',
                    f'<rect x="0" y="0" width="{W}" height="{H}" fill="{BG}"/>']
            body += self.parts
            body += ['</g>', '</svg>']
        else:
            body = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W*2}" height="{H*2}" viewBox="0 0 {W} {H}">',
                    f'<rect x="0" y="0" width="{W}" height="{H}" rx="{R}" fill="{BG}"/>'] + self.parts + ['</svg>']
        return "\n".join(body)

    def save(self):
        for bezel, suffix in ((True, ""), (False, "-flat")):
            p = os.path.join(OUT, f"{self.name}{suffix}.svg")
            with open(p, "w") as f:
                f.write(self.svg(bezel))
            subprocess.run(["/opt/homebrew/bin/rsvg-convert", p, "-o", p.replace(".svg", ".png")], check=True)
        return self


# =====================================================================================
# Screens
# =====================================================================================
screens: list[Screen] = []


def s_pairing():
    s = Screen("01-pairing", "Pair")
    s.text(20, 86, "Pair with your gateway", size=18, color=INK, weight=700)
    s.wrap(20, 112, "On your Mac, open the console › Devices, then enter this code.", 34, size=14, color=MUTED)
    s.rect(20, 160, W - 40, 92, fill=CARD, stroke=LINE, r=22)
    s.text(W / 2, 220, "K7PQ · 3M", size=40, color=CYAN, weight=800, anchor="middle", family=MONO, letter=2)
    s.text(W / 2, 282, "expires in 9:42", size=13, color=MUTED, anchor="middle")
    s.progress_dots(W / 2, 318, active=0)
    s.text(W / 2, 352, "waiting for the console…", size=13, color=INDIGO, anchor="middle")
    s.button(20, 392, W - 40, 50, "Use a token instead", CARD2, color=INK2, size=15)
    s.text(W / 2, 470, "gateway: mbp.local · 127.0.0.1:8080", size=11, color=MUTED, anchor="middle", family=MONO)
    return s


def s_home(waiting=2):
    s = Screen("02-home", "Assistant")
    s.dot(106, 36, GREEN, r=4)
    s.text(116, 40, "mbp", size=12, color=MUTED, weight=600)
    # waiting tile
    s.rect(16, 62, W - 32, 112, fill="#1e1708", stroke=AMBER_D, r=22)
    s.text(36, 100, str(waiting), size=44, color=AMBER, weight=800)
    s.text(36 + (48 if waiting < 10 else 72), 100, "waiting for you", size=19, color=INK, weight=700)
    s.text(36, 128, "execute_command · coding-agent", size=12.5, color=INK2, family=MONO)
    s.text(36, 150, "ask_user · deep-research", size=12.5, color=INK2, family=MONO)
    s.chevron(W - 42, 118, AMBER)
    # actions
    s.rect(16, 188, (W - 44) / 2, 96, fill="#121a2b", stroke="#1d2d4d", r=22)
    s.orb(16 + (W - 44) / 4, 224, r=20)
    s.text(16 + (W - 44) / 4, 270, "Ask", size=15, color=INK, weight=700, anchor="middle")
    rx = 28 + (W - 44) / 2
    s.rect(rx, 188, (W - 44) / 2, 96, fill=CARD, stroke=LINE, r=22)
    s.text(rx + 22, 216, "2", size=15, color=CYAN, weight=800); s.text(rx + 40, 216, "running", size=12, color=MUTED)
    s.text(rx + 22, 236, "12", size=15, color=GREEN, weight=800); s.text(rx + 46, 236, "done", size=12, color=MUTED)
    s.text(rx + (W - 44) / 4, 270, "Runs", size=15, color=INK, weight=700, anchor="middle")
    # automations row
    s.rect(16, 298, W - 32, 64, fill=CARD, r=18)
    s.text(34, 324, "Automations", size=16, color=INK, weight=700)
    s.text(34, 346, "Morning digest · next 07:00", size=12.5, color=MUTED)
    s.chevron(W - 38, 330)
    # last event
    s.text(20, 396, "LAST EVENT", size=10.5, color=MUTED, weight=700, letter=1)
    s.text(20, 420, "deep-research finished", size=14, color=INK2, weight=600)
    s.text(20, 440, "12 min ago · report.pdf ready", size=12.5, color=MUTED)
    s.rect(16, 456, W - 32, 2, fill=LINE, r=1)
    return s


def s_approval(risk="Destructive", tool="execute_command", cmd="rm -rf build/ && make", run="94a436 · coding-agent"):
    s = Screen("03-approval", "Approval")
    s.text(20, 84, tool, size=20, color=INK, weight=800, family=MONO)
    s.text(20, 108, "needs your approval", size=14, color=MUTED)
    w = s.pill(20, 120, risk, RED if risk == "Destructive" else AMBER, size=11.5, h=24)
    s.pill(20 + w + 8, 120, "can delete", RED, size=11.5, h=24)
    s.rect(20, 160, W - 40, 72, fill="#08080e", stroke=LINE, r=16)
    s.text(36, 190, "$ " + cmd, size=14, color=INK, family=MONO)
    s.text(36, 214, "cwd  ~/projects/assay-pipeline", size=12, color=MUTED, family=MONO)
    s.text(20, 258, "run " + run, size=12, color=MUTED, family=MONO)
    s.text(20, 278, "asked 40 s ago · also shown on Mac and iPhone", size=12, color=MUTED)
    s.button(20, 300, W - 40, 52, "Allow once", GREEN_D, size=18, icon="✓")
    s.button(20, 362, (W - 52) / 2, 52, "Deny", RED_D, size=17)
    s.button(32 + (W - 52) / 2, 362, (W - 52) / 2, 52, "Later", CARD2, color=INK2, size=17)
    s.text(W / 2, 444, "hold Allow for “allow all in this run”", size=11.5, color=MUTED, anchor="middle")
    return s


def s_email_approval():
    s = Screen("17-approval-email", "Approval")
    s.text(20, 84, "send_email", size=20, color=INK, weight=800, family=MONO)
    s.text(20, 108, "wants to send this", size=14, color=MUTED)
    s.pill(20, 120, "sends to someone else", AMBER, size=11.5, h=24)
    s.rect(20, 160, W - 40, 86, fill="#08080e", stroke=LINE, r=16)
    s.text(36, 186, "To", size=11, color=MUTED, weight=700); s.text(60, 186, "qc-team@example.org", size=14, color=INK)
    s.wrap(36, 212, "Nightly assay QC: 2 plates to review", 36, size=14, color=INK, weight=600, max_lines=2)
    s.text(20, 272, "⎘ View draft", size=14, color=CYAN, weight=700)
    s.text(20, 292, "run c17d20 · Morning digest · asked 25 s ago", size=11.5, color=MUTED, family=MONO)
    s.button(20, 312, W - 40, 50, "Send it", GREEN_D, size=18, icon="✓")
    s.button(20, 372, (W - 52) / 2, 50, "Deny", RED_D, size=17)
    s.button(32 + (W - 52) / 2, 372, (W - 52) / 2, 50, "Later", CARD2, color=INK2, size=17)
    s.text(W / 2, 452, "Double Tap is off for sends", size=11.5, color=MUTED, anchor="middle")
    return s


def s_picker():
    s = Screen("18-who-answers", "Who answers")
    rows = [("Assistant", "the gateway's default agent workflow", True), ("Castor", "phase work · long-lived", False),
            ("Mira", "phase personal", False), ("Nerin", "phase sleep", False)]
    y = 62
    for name, sub, sel in rows:
        s.rect(16, y, W - 32, 66, fill=CARD, stroke=(CYAN if sel else LINE), r=18)
        s.orb(44, y + 33, r=13)
        s.text(70, y + 28, name, size=16, color=INK, weight=700)
        s.text(70, y + 48, sub, size=12, color=MUTED)
        if sel: s.text(W - 36, y + 40, "✓", size=16, color=CYAN, weight=800, anchor="middle")
        y += 74
    s.text(20, y + 10, "ENTITIES", size=10.5, color=MUTED, weight=700, letter=1) if False else None
    s.text(W / 2, 378, "the choice is kept for this watch", size=11.5, color=MUTED, anchor="middle")
    return s


def s_approval_done():
    s = Screen("04-approval-done", "Approval")
    s.check(W / 2, 180)
    s.text(W / 2, 258, "Allowed once", size=22, color=INK, weight=800, anchor="middle")
    s.text(W / 2, 286, "recorded in the run ledger", size=13.5, color=MUTED, anchor="middle")
    s.rect(20, 316, W - 40, 70, fill=CARD, stroke=LINE, r=18)
    s.dot(42, 351, GREEN)
    s.text(58, 345, "coding-agent continues", size=15, color=INK, weight=600)
    s.text(58, 366, "on your Mac · step 14 of the run", size=12.5, color=MUTED)
    s.text(W / 2, 430, "1 still waiting for you", size=14, color=AMBER, weight=700, anchor="middle")
    return s


def s_ask_idle():
    s = Screen("05-ask", "Ask")
    s.text(20, 72, "ASSISTANT ⌄", size=11, color=CYAN, weight=700, letter=1)
    s.orb(W / 2, 200, r=48)
    s.text(W / 2, 306, "Tap to ask", size=20, color=INK, weight=700, anchor="middle")
    s.text(W / 2, 332, "hold to record · dictation or Whisper on your Mac", size=12, color=MUTED, anchor="middle")
    s.text(20, 380, "RECENT", size=10.5, color=MUTED, weight=700, letter=1)
    s.text(20, 404, "“Did the nightly assay QC pass?”", size=13.5, color=INK2)
    s.text(20, 428, "“Summarise the open issues in my project”", size=13.5, color=INK2)
    return s


def s_ask_listening():
    s = Screen("06-ask-listening", "Ask")
    s.text(20, 72, "ASSISTANT ⌄", size=11, color=CYAN, weight=700, letter=1)
    s.orb(W / 2, 165, r=42, mode="listening")
    s.waveform(60, 268, W - 120)
    s.text(W / 2, 320, "Listening…", size=18, color=CYAN, weight=700, anchor="middle")
    s.wrap(30, 362, "“Compare overall survival by treatment arm in the ADTTE I sent you”", 36, size=14.5, color=INK, weight=500)
    s.button(20, 428, W - 40, 46, "Send", INDIGO_D, size=16)
    return s


def s_ask_thinking():
    s = Screen("07-ask-thinking", "Ask")
    s.wrap(20, 86, "Compare overall survival by treatment arm in the ADTTE I sent you", 36, size=14.5, color=INK2)
    s.rect(16, 150, W - 32, 150, fill=CARD, stroke=LINE, r=20)
    s.orb(W / 2, 200, r=26, mode="thinking")
    s.text(W / 2, 252, "Assistant is working", size=14, color=INK, weight=600, anchor="middle")
    s.text(W / 2, 272, "step 4 · running the analysis", size=12.5, color=MUTED, anchor="middle", family=MONO)
    s.text(W / 2, 290, "on your Mac · local model", size=12, color=MUTED, anchor="middle")
    s.text(20, 340, "you can lower your wrist; we’ll tap you", size=12.5, color=MUTED)
    s.button(20, 380, W - 40, 46, "Continue on Mac", CARD2, color=INK2, size=15)
    return s


def s_answer():
    s = Screen("08-answer", "Answer")
    s.rect(16, 60, W - 32, 236, fill=CARD, r=20)
    y = s.wrap(32, 90, "Overall survival favoured arm B: HR 0.78 (95% CI 0.61–0.99), n = 412, 287 events. Proportional hazards held (Schoenfeld p = 0.41).", 34, size=14, color=INK, lh=20)
    s.text(32, y + 8, "reviewer: approved after 1 revision", size=12, color=GREEN, family=MONO)
    s.text(32, y + 28, "rules: 6 / 6 · km_by_arm.png · report.pdf", size=12, color=MUTED, family=MONO)
    s.button(20, 312, (W - 52) / 2, 48, "Speak", "#0f3344", color=CYAN, size=15, icon="▶")
    s.button(32 + (W - 52) / 2, 312, (W - 52) / 2, 48, "Follow-up", CARD2, color=INK2, size=15)
    s.button(20, 372, W - 40, 48, "Continue on Mac", INDIGO_D, size=15)
    s.text(W / 2, 452, "same session · run 7c1e02 · 3 min 40 s", size=11.5, color=MUTED, anchor="middle", family=MONO)
    return s


def s_runs():
    s = Screen("09-runs", "Runs")
    s.row(60, "coding-agent", "waiting for you · 40 s", AMBER, "waiting")
    s.row(134, "analytics-assistant", "step 4 · running the analysis", CYAN, "running")
    s.row(208, "deep-research", "done · 12 min ago", GREEN, "done")
    s.row(282, "Morning digest", "automation · 07:04", GREEN, "done")
    s.row(356, "docs-qa", "failed · model timeout", RED, "failed")
    s.text(W / 2, 462, "pull to refresh · live on wrist raise", size=11.5, color=MUTED, anchor="middle")
    return s


def s_run_detail():
    s = Screen("10-run-detail", "Run")
    s.text(20, 84, "analytics-assistant", size=18, color=INK, weight=800)
    s.text(20, 106, "run 7c1e02 · started 09:38 · local model", size=12, color=MUTED, family=MONO)
    steps = [("#2", "llm_call", "plan", GREEN), ("#3", "llm_call", "code v1", GREEN), ("#4", "code", "KeyError 'ARM'", RED),
             ("#5", "llm_call", "code v2 · traceback in context", GREEN), ("#6", "tool_calls", "python analysis/run.py", CYAN)]
    y = 128
    for n, kind, what, col in steps:
        s.rect(16, y, W - 32, 44, fill=CARD, r=12)
        s.text(30, y + 27, n, size=12, color=MUTED, family=MONO)
        s.pill(58, y + 10, kind, col, size=10.5, h=22)
        s.text(160, y + 27, what, size=12.5, color=INK2, family=MONO)
        y += 50
    s.button(20, 392, (W - 52) / 2, 46, "Cancel", RED_D, size=15)
    s.button(32 + (W - 52) / 2, 392, (W - 52) / 2, 46, "Discuss", INDIGO_D, size=15)
    s.text(W / 2, 466, "ledger live · 6 of ~14 records", size=11.5, color=MUTED, anchor="middle", family=MONO)
    return s


def s_automations():
    s = Screen("11-automations", "Automations")
    s.row(60, "Morning digest", "every day · last 07:04 · ok", GREEN, "daily")
    s.row(134, "Literature watch", "every 7 days · 3 new papers", CYAN, "weekly")
    s.row(208, "Assay QC check", "when a file lands · ok", GREEN, "on event")
    s.rect(16, 292, W - 32, 92, fill="#121a2b", stroke="#1d2d4d", r=20)
    s.text(34, 322, "Run now", size=16, color=INK, weight=700)
    s.text(34, 344, "Morning digest · ~2 min on your Mac", size=12.5, color=MUTED)
    s.button(W - 16 - 96, 312, 84, 44, "Run", INDIGO_D, size=15)
    s.text(W / 2, 430, "notified only on a question, an approval or a failure", size=11.5, color=MUTED, anchor="middle")
    return s


def s_automation_result():
    s = Screen("12-automation-result", "Digest")
    s.text(20, 84, "Morning digest", size=18, color=INK, weight=800)
    s.text(20, 106, "07:04 · 2 min 10 s · 3 sources", size=12, color=MUTED, family=MONO)
    s.rect(16, 120, W - 32, 220, fill=CARD, r=20)
    s.wrap(32, 150, "Three things today: the assay QC run passed; two new papers on your target (one with a phase II readout); the dependency check found one update to pin.", 34, size=14, color=INK, lh=20)
    s.button(20, 356, W - 40, 48, "Discuss on Mac", INDIGO_D, size=15)
    s.button(20, 414, W - 40, 44, "Mark read", CARD2, color=INK2, size=14)
    return s


def s_notification():
    s = Screen("13-notification", time="9:41")
    s.rect(16, 50, W - 32, 150, fill="#1e1708", stroke=AMBER_D, r=22)
    s.text(36, 82, "AbstractAssistant", size=12.5, color=AMBER, weight=700)
    s.text(36, 110, "execute_command needs", size=17, color=INK, weight=700)
    s.text(36, 134, "your approval", size=17, color=INK, weight=700)
    s.text(36, 160, "Destructive · can delete · coding-agent", size=12, color=INK2, family=MONO)
    s.text(36, 182, "$ rm -rf build/ && make", size=12, color=MUTED, family=MONO)
    s.button(20, 220, W - 40, 50, "Allow once", GREEN_D, size=17, icon="✓")
    s.button(20, 282, W - 40, 50, "Deny", RED_D, size=17)
    s.button(20, 344, W - 40, 50, "Open", CARD2, color=INK2, size=16)
    s.text(W / 2, 430, "answered here, recorded in the ledger", size=11.5, color=MUTED, anchor="middle")
    return s


def s_complication():
    s = Screen("14-smart-stack", time="9:41")
    s.text(20, 40, "Smart Stack", size=16, color=INK, weight=700)
    # rectangular widget
    s.rect(16, 62, W - 32, 110, fill="#1e1708", stroke=AMBER_D, r=22)
    s.text(36, 92, "AbstractAssistant", size=11.5, color=AMBER, weight=700)
    s.text(36, 128, "2", size=36, color=AMBER, weight=800)
    s.text(72, 128, "waiting for you", size=18, color=INK, weight=700)
    s.text(36, 156, "execute_command · ask_user", size=12, color=INK2, family=MONO)
    # second widget: last automation
    s.rect(16, 186, W - 32, 110, fill=CARD, stroke=LINE, r=22)
    s.text(36, 216, "AbstractAssistant", size=11.5, color=INDIGO, weight=700)
    s.dot(46, 248, GREEN)
    s.text(62, 253, "Morning digest · done", size=17, color=INK, weight=700)
    s.text(36, 280, "07:04 · 3 things today", size=12.5, color=MUTED)
    # corner complication preview
    s.text(20, 338, "CORNER COMPLICATION", size=10.5, color=MUTED, weight=700, letter=1)
    s.circle(60, 396, 30, CARD, stroke=AMBER, sw=3)
    s.text(60, 404, "2", size=24, color=AMBER, weight=800, anchor="middle")
    s.text(104, 392, "runs waiting · tap opens the first one", size=12.5, color=INK2)
    s.text(104, 412, "updates on background refresh + push", size=12, color=MUTED)
    return s


def s_settings():
    s = Screen("15-settings", "Settings")
    rows = [("Gateway", "mbp.local · signed in as albou", GREEN), ("Network", "Tailscale Funnel · https", GREEN),
            ("Voice", "dictation · Whisper on Mac", CYAN), ("Haptics", "approvals · failures", INDIGO),
            ("Double Tap", "Allow once (reads only)", INDIGO), ("Sign out", "", RED)]
    y = 60
    for t, sub, col in rows:
        s.rect(16, y, W - 32, 56, fill=CARD, r=14)
        s.text(32, y + 24 if sub else y + 34, t, size=15, color=col if t == "Sign out" else INK, weight=700)
        if sub:
            s.text(32, y + 44, sub, size=12, color=MUTED)
        if t != "Sign out":
            s.chevron(W - 36, y + 28)
        y += 62
    s.text(W / 2, 466, "AbstractAssistant for Apple Watch · 0.1.0", size=11, color=MUTED, anchor="middle")
    return s


def s_askuser():
    s = Screen("16-ask-user", "Question")
    s.text(20, 84, "deep-research asks", size=18, color=INK, weight=800)
    s.wrap(20, 112, "Two sources disagree on the phase II endpoint. Which one should I treat as primary?", 36, size=14.5, color=INK2, lh=20)
    opts = [("EMA assessment report (2025)", INDIGO_D, INK), ("Company press release", CARD2, INK2), ("Cite both, flag the conflict", CARD2, INK2)]
    y = 196
    for label, fill, col in opts:
        s.button(20, y, W - 40, 48, label, fill, color=col, size=14.5)
        y += 58
    s.text(W / 2, 410, "or dictate another answer", size=12.5, color=MUTED, anchor="middle")
    s.text(W / 2, 452, "run 3e9a10 · the run waits until you answer", size=11.5, color=MUTED, anchor="middle", family=MONO)
    return s


for fn in (s_pairing, s_home, s_approval, s_approval_done, s_ask_idle, s_ask_listening, s_ask_thinking, s_answer,
           s_runs, s_run_detail, s_automations, s_automation_result, s_notification, s_complication, s_settings, s_askuser,
           s_email_approval, s_picker):
    screens.append(fn().save())

print("wrote", len(screens), "screens to", OUT)
