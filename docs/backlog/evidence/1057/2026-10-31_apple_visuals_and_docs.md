# Apple visuals and Docs layout — 2026-10-31

The Docs panel lacked a height/flex boundary. The shared `docsAssistantPanel`
now requests `fill` and its root establishes the flex column. The footer uses
plain wording. Live validation also found the browser requested the unknown
`assistant` corpus id and served SPA HTML instead of its documentation. It uses
`assistant-web` and ships a browser guide at `llms.txt` with `text/plain`.
The private web app adapts its published panel-chat 0.6.4 pin with
a scoped wrapper and short placeholder, without changing conversation ownership.

AbstractAvatar owns the procedural generator and catalog; AbstractUIC provides
Canvas/React presentation. The web picker uses all 44 designs: 34 Watch picker
entries, three Watch shape variants, the iPhone woven orb and six shaded styles.
The browser default is `watch-halo` for unset/invalid preferences; an existing
valid style stays. Native SwiftUI and browser pixels are not claimed identical.

The app's published ui-kit 0.9.6 pin predates this catalog. Until the next package
release is adopted, `scripts/sync_apple_avatars.mjs` copies the compiled canonical
presenter, adapter and Wasm artifact. Provenance pins source and artifact SHA256
hashes; standalone builds verify committed snapshots. This contains no independent
browser generator. No registry publish or dependency floor change was performed.

Validation:

- 62 web unit tests, TypeScript/Vite build, relative URL guard.
- 16 light/dark desktop/tablet/phone layout combinations.
- Real Chromium with fake Gateway and virtual audio: seven Apple styles × seven
  phases paint, reduced motion is stable, shaded Hover's red errors remain,
  preference persistence, keyboard recovery, speech interruption and phone approvals.
- Docs composer near the bottom at 420px and 1440px, no visible internal API text,
  question/answer round trip and New conversation.
- Shared Docs panel 25 checks and Docs assistant 59 checks; shared Apple engine
  compatibility adapter and generator checks are maintained with AbstractAvatar.

Screenshots are local under `untracked/assistant-apple-iteration/`. Physical
microphone/playback and native Watch rendering were not exercised by these checks.
The next release adoption/removal is tracked in parent item 1057.

Live Gateway validation: signed-in `/apps/assistant-web/` handover, account and
assets 200, scoped app cookies, 44 catalog choices, fresh Watch Halo default,
iPhone Waiting preview, full-height Docs drawer, nonempty documentation corpus
200, a real documentation question answered successfully, and existing conversation history. Zero JavaScript errors. Local installation
used a verified private tarball and a managed restart for the server MIME change.
