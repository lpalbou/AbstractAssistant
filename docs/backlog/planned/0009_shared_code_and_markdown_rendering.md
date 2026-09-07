# Planned: Share code and markdown rendering with abstractuic

## Metadata
- Created: 2026-09-06
- Status: Planned
- Completed: N/A

## ADR status
- Governing ADRs: [ADR 0001](../../adr/0001_gateway_native_assistant_v2.md)
- ADR impact: None. This is presentation only; it does not touch the gateway boundary.

## Context

The operator reported that shell blocks in the chat rendered very poorly, and asked whether the
renderer lives in `abstractuic` so a single view could be shared across file types and modalities.
It does not — not in any form this client can call.

`abstractuic` has two markdown renderers, and both are React/TypeScript:

- `abstractuic/panel-chat/src/markdown.tsx`
- `abstractuic/monitor-flow/src/Markdown.tsx`

AbstractAssistant is PyQt5. It renders markdown to an HTML fragment that Qt's limited rich-text
engine can display (`abstractassistant/utils/markdown_renderer.py`, ~950 lines: markdown-it-py for
structure, Pygments for code, inline styles because Qt supports almost no CSS). There is no runtime
in which a `.tsx` component and a `QTextBrowser` fragment can be the same code, so the fix for the
shell rendering was made here.

`abstractuic` already carries a related item —
`abstractuic/docs/backlog/proposed/0010_rich_markdown_renderer_package.md` — which proposes
extracting its renderer into a package. That proposal is currently framed for web consumers only.

## Current code reality

Duplicated between the two stacks today:

- the code-block token palette (which token type gets which colour);
- the language normalisation rules (`shell-session` → `bash`, sniffing an unlabelled block);
- the code-panel chrome (accent rail, body surface, padding, radius);
- inline-code treatment;
- table, list and blockquote spacing decisions.

Diverged already: this client has a shell-readability pass that re-tags command names, flags and
redirections (Pygments leaves 16 of 26 tokens on a real pipeline as plain `Token.Text`); the web
renderers use Shiki/Prism defaults and do not.

## What sharing would actually mean

The renderers cannot share an implementation across Python and TypeScript, but they can share the
part that matters for consistency — the DATA:

1. **A colour and token contract, published from `abstractuic`** as JSON, the way `theme.css`
   already is. This client reads `theme.css` today (`abstractassistant/ui_themes.py`, with a
   vendored fallback and a `--refresh` drift check); a `code-tokens.json` beside it would be the
   same pattern, consumed by both stacks.
2. **A shared language-normalisation table** (alias → canonical language, plus the sniffing rules
   for unlabelled blocks), also as data.
3. **A shared shell-token specification**, so a command/flag/redirect is coloured the same way in
   the desktop client and on the web. This is the piece that just diverged.

What cannot be shared: the emit layer. Qt's rich text does not support the CSS the web renderer
relies on, so the HTML/inline-style generation stays per-stack.

## Proposed work

- [ ] Agree the contract with `abstractuic` (link this item to their 0010) — data, not components.
- [ ] Publish `code-tokens.json` + `languages.json` from `abstractuic/ui-kit/src/`.
- [ ] Consume them here through the existing three-tier resolver (sibling checkout → vendored
      snapshot → built-in default) and delete the hard-coded token palette in
      `_AbstractAssistantCodeStyle`.
- [ ] Port the shell-readability rules into the shared spec so the web renderers gain them.
- [ ] Extend the existing drift check (`ui_themes.py --refresh`) to cover the new files, so an
      upstream change is detected rather than silently diverging.

## Risks

- The web renderer's token set (Shiki) is finer-grained than Pygments'; the contract has to be
  expressed in terms both can map onto, or it becomes a lowest-common-denominator that makes both
  renderers worse.
- Pulling colours from a shared file must not break offline operation. The current resolver already
  guarantees this (vendored snapshot, no network); anything new must follow it.

## Acceptance

- One source of truth for code-token colours and language aliases, consumed by both stacks.
- A shell block is coloured identically in the desktop client and in `panel-chat`.
- `tests/basic` still passes offline with the sibling checkout absent.
