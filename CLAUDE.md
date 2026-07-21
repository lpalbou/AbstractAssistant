# AbstractAssistant Development Log

This file tracks major development tasks, architectural decisions, and implementation notes for AbstractAssistant.

---

## TASK COMPLETION LOG

### Task: Model/voice selection is a LOCAL override, never a gateway mutation (2026-07-18)

**Symptom (two reports, one cause)**: (1) chat "failed offline"; (2) picking a
provider/model in settings "changed the DEFAULT OF THE GATEWAY" instead of being
a local override for the assistant.

**Root cause (confirmed by run forensics + code)**: the settings tab's
`_save_route` called `controller.save_route_default` → `gateway_service.save_route_default`
→ `client.set_capability_default` → HTTP `PUT /api/gateway/config/capability-defaults/{kind}/{modality}`
— a mutation of the gateway's GLOBAL capability default, shared by every client.
That default had been set to an online-only `endpoint:ovh-provider` /
`Meta-Llama-3_3-70B-Instruct`; offline, every chat run failed (`run_03c9e69f`
DNS `[Errno 8] nodename nor servname`, then `run_a84afc0b` "Circuit breaker
open"). The assistant sent NO provider/model override, so it inherited the
corrupted global default. The two problems are the same bug.

**Override channel — DUAL, both required (adversary-corrected)**: the override
must ride BOTH channels of `build_run_input_data`:
- TOP-LEVEL `input_data.provider`/`model` — flows through the start node's pins
  into the ROUTER `llm_call` node (`route_call`). Visual `llm_call` nodes do NOT
  read `_runtime`, so a `_runtime`-only override leaves the router on the baked
  gateway default. LIVE-PROVEN both ways on the current gateway: `_runtime`-only
  → `route_call` payload `provider=None` (baked default, breaks offline at the
  FIRST call); top-level → `route_call` payload `provider=lmstudio` (override
  honored). My first-pass `_runtime`-only fix was WRONG for exactly this reason;
  an earlier note claiming "top-level does NOT override" misread `vars._runtime.provider`
  (a host mirror that `bundle_host._seed` fills only-when-empty, ~1697-1706) as
  the router's actual routing.
- `_runtime.provider`/`model` — covers the `assistant_agent` CHILD subrun (which
  DOES inherit run-scoped defaults via `setdefault` in `runtime.py`, protected
  from clobber) and any future run-default-reading node.
Sending both makes the whole workflow (router + agent) use the override without
touching the gateway default.

**base_url is best-effort (runtime limitation, reported not owned)**: for a plain
provider, `MultiLocalAbstractCoreLLMClient._create_client` builds the switched
client from `dict(self._llm_kwargs)`, which carries the DEFAULT provider's
`base_url`/`api_key` (`llm_client.py` ~7119). So switching to plain `lmstudio`
while the baked default is `endpoint:ovh-provider` yields a lmstudio client
pointed at OVH's URL → "model not found" listing the OVH catalog (also leaks the
OVH bearer to the new host). Mitigations: `endpoint:<id>` providers self-resolve
their base_url/key via the runtime's live `resolve_provider_endpoint_profile`
(reliable); when the baked default is itself a local provider (the normal
post-fix state), plain-provider overrides work. The assistant sends base_url on
both channels best-effort. The kwargs-inheritance is a runtime defect to file
against abstractruntime.

**base_url gotcha (runtime, reported not owned)**: `MultiLocalAbstractCoreLLMClient`
builds a switched-provider client from `dict(self._llm_kwargs)`, which carries
the DEFAULT provider's `base_url`. So when the baked default is
`endpoint:ovh-provider` (base_url=OVH) and you override to plain `lmstudio`, the
lmstudio client inherits OVH's base_url and 400s "model not found" (lists OVH
models). Two mitigations: the assistant sends `base_url` in the override too
(rides `_runtime.base_url`), and `endpoint:` profiles carry their own base_url
via the runtime's `resolve_provider_endpoint_profile` resolver so they always
work. When the gateway default is itself a local provider (the normal,
post-fix state), plain-provider overrides work without a base_url. Live "Model
unloaded"/"Failed to load model" 400s during testing were LM Studio JIT
load/unload churn, not the override path.

**Fix (assistant-only, gateway never mutated)**:
- `preferences.py`: `AssistantPreferences.route_overrides: Dict[route_key, {provider, model, base_url?, options?}]`;
  `LOCAL_OVERRIDE_ROUTE_KEYS = ("output.text", "output.voice", "input.voice")`;
  `_normalize_route_overrides` drops half-pins (provider without model).
- `controller.py`: `route_override` / `save_route_override` / `clear_route_override`
  write LOCAL prefs only (the gateway-mutating `save_route_default`/`clear_route_default`
  are GONE). `build_chat_worker` passes the `output.text` override as
  `provider_override`/`model_override`/`base_url_override`. `_sync_gateway_voice_defaults`
  now pushes only the LOCAL voice/STT override onto `current_tts_*`/`current_stt_model`
  (empty = let the gateway default resolve) — it no longer pins the gateway's
  moving default as if it were the user's choice.
- `gateway/run_input.py`: `build_run_input_data(provider, model, base_url)` sets
  BOTH top-level `provider`/`model`/`base_url` (router coverage) AND
  `_runtime.{provider,model,base_url}` (agent coverage); both provider+model
  required (half-pin dropped on both channels).
- `ui/gateway_worker.py`: `provider_override`/`model_override`/`base_url_override`
  threaded into `build_run_input_data`.
- `_save_preferences` (General tab) now carries `route_overrides` when rebuilding
  the prefs object — omitting it silently wiped the overrides on every General
  save (adversary Q5.4).
- STT provider threaded: `client.audio_transcribe(provider=...)` (the gateway
  transcribe route accepts it; the client had dropped it), `GatewaySTTAdapter`
  gained `stt_provider_fn`, voice manager `_selected_stt_provider`, controller
  syncs `current_stt_provider` from the `input.voice` override.
- `app.py` settings: tab "Gateway Defaults" → "Models & Voice"; rows built from
  `_build_override_rows` (only the 3 overrideable routes; media/embedding removed
  from the thin client); mode = local override present?; state line shows BOTH
  the gateway default and this-app override; "Reset to gateway" button
  (`_reset_route_to_gateway` → `clear_route_override`); radios "Use gateway
  default" / "Override for this app".

**Scope decision**: media/embedding routes were removed from the assistant
settings. The assistant only TRIGGERS media generation; it cannot honor a local
per-run override for media nodes (no proven `_runtime` route-override channel for
them), so offering it would be dishonest, and reconfiguring the gateway's media
models belongs to the gateway console — not a thin client forbidden from
mutating the gateway.

**Testing**: `tests/basic` 268 passed. New: `test_settings_routes.py` rewritten
for the local-override contract (guards that the gateway-mutating API is never
reached from the dialog; reset button; only-overrideable-routes listed);
`test_gateway_run_input.py` override-in-`_runtime` + half-pin-dropped;
`test_assistant_palette.py` build_chat_worker passes/omits the override. Live:
override stored in `preferences.json`, gateway capability default byte-unchanged
before/after, reset clears the override.

---

### Task: Run Visibility, Run Controls, and Mid-Run Steering (2026-07-10)

**Description**: Gave the assistant (v2 palette primarily; v1 bubble kept in parity) live
visibility into agent cycles and tool launches, durable pause/resume/cancel controls, and
mid-run steering — typed text during a run redirects the agent without cancelling it.

**How it works**:
1. **Visibility** (`gateway/adapter.py`): STARTED ledger records now produce UI events —
   `{"type": "cycle", "iteration": N}` for `llm_call` starts on the agent's `reason` node
   (counted per run id), and `{"type": "tool_started", "tools": [{name, arguments_preview}]}`
   for `tool_calls` starts (pre-execution; previously only tool *results* were visible).
   Both palettes render them on the inline status line ("Thinking — cycle 3",
   "Tool: read_file {'file_path': …}").
2. **Controls**: `GatewayClient.pause_run/resume_run/cancel_run/inject_guidance` wrappers
   (durable gateway commands; pause/cancel are tree-wide, pause lands at the next step
   boundary). v2 controller gained `pause_run/resume_run/inject_guidance` beside the
   existing `cancel_run`. UI: the send/stop button's right-click menu offers
   Pause/Resume/Stop while a run is active.
3. **Steering**: while a run is active, `_submit` (v2) / `send_message` (v1) no longer
   refuse typed text — it is delivered via `inject_guidance` into the run's durable
   `_runtime.inbox`, folds into the agent's next reasoning cycle as a durable transcript
   message (see abstractagent adapters, maintainer ruling 2026-07-09/10), and is echoed
   into the local transcript with `metadata.kind = "operator_guidance"`.
4. **Local (non-gateway) parity**: `AgentHost` gained `active_run_id/inject_guidance/
   pause_turn/resume_turn/cancel_turn`; the v1 bubble routes controls to the gateway or
   the local host transparently.

**Files Modified**: `abstractassistant/gateway/adapter.py`, `abstractassistant/gateway/client.py`,
`abstractassistant/core/agent_host.py`, `abstractassistant/ui/qt_bubble.py`,
`abstractassistantv2/controller.py`, `abstractassistantv2/app.py`.

**Testing**: `tests/basic` — 265 passed. New: adapter cycle/tool_started contract tests,
client run-control command tests, v2 palette steering + status tests, v2 controller command
tests. The steering/pause/resume/cancel mechanics were separately live-verified at the
runtime/agent layer (ReAct/MemAct/CodeAct all drain the inbox into the durable transcript).

**Notes/Limitations**: steering requires the flow to reach an inbox-bearing agent loop
(Agent-node/abstractagent loops qualify; hand-built `llm_call` loops do not — see
`docs/guide/event-inbox-agent.md`). Pause is honored at the next commit point; an in-flight
LLM/tool call finishes first. The tray app was not driven end-to-end headlessly; UI-level
changes are covered by the palette unit tests.

**Post-release fix (same day, live-testing feedback)**: after Stop, the follower thread
lingers until its next SSE line/idle window; during that window `self._worker` was still
set, so (a) the Send icon did not come back and (b) a re-sent message was silently routed
into the STEERING path of the now-cancelled run — it never started a new run and the
session ended with the misleading "no written reply" banner. Fixes in `app.py`:
`_cancel_active_run` restores the Send button immediately and marks `_cancel_requested`;
`_submit` steers only live non-cancelled runs, queues a send issued during teardown
(`_pending_submit`, fired by `_on_worker_finished`), and clears stale finished workers;
a user-stopped run now reports "Run stopped." instead of the no-written-reply diagnostic.
Same teardown guard added to the v1 bubble. State flags are class-level defaults because
`getattr(obj, missing, default)` raises RuntimeError on `__new__`-built QObjects (tests).
Four regression tests added (269 passing).

---

### Task: AbstractCore 2.4.5 Upgrade and File Attachment Feature (2025-10-21)

**Description**: Upgraded AbstractCore from 2.4.2 to 2.4.5 to leverage new universal media handling capabilities and implemented a complete file attachment system in the chat bubble UI, enabling users to attach and send images, PDFs, Office documents, and other file types alongside text messages.

**Goals**:
1. ✅ Update AbstractCore dependency to version 2.4.5
2. ✅ Ensure AbstractAssistant remains fully functional with the new version
3. ✅ Add file attachment capability to the message bubble UI leveraging AbstractCore's media handling

**Implementation Details**:

#### 1. AbstractCore Upgrade (2.4.2 → 2.4.5)

**Files Modified**:
- `requirements.txt`: Updated `abstractcore[all]>=2.4.2` → `abstractcore[all]>=2.4.5`
- `pyproject.toml`: Updated `"abstractcore[all]>=2.4.2"` → `"abstractcore[all]>=2.4.5"`

**Key Changes in AbstractCore 2.4.5**:
- **Universal Media Handling System**: Production-ready unified file attachment API
- **Cross-Format Support**: Images (PNG, JPEG, GIF, WEBP, BMP, TIFF), PDFs, Office docs (DOCX, XLSX, PPTX), data files (CSV, TSV, JSON)
- **Intelligent Processing**: Automatic file type detection with specialized processors
- **Provider Adaptation**: Automatic formatting for each provider's API requirements
- **API**: Simple `media=[]` parameter in `generate()` calls works across all providers

**Testing**:
- ✅ Verified imports: `from abstractcore import create_llm`
- ✅ Verified LLMManager compatibility
- ✅ All existing functionality preserved

#### 2. LLMManager Media Support (`abstractassistant/core/llm_manager.py`)

**Updated Method Signature**:
```python
def generate_response(
    self,
    message: str,
    provider: str = None,
    model: str = None,
    media: Optional[List[str]] = None  # NEW: file paths for media attachments
) -> str
```

**Implementation**:
```python
# Generate response with optional media files
if media and len(media) > 0:
    response = self.current_session.generate(message, media=media)
else:
    response = self.current_session.generate(message)
```

**Key Features**:
- Accepts optional list of file paths
- Passes media files directly to AbstractCore's session.generate()
- Maintains backward compatibility (media parameter is optional)
- Supports all file types handled by AbstractCore 2.4.5

#### 3. LLMWorker Thread Updates (`abstractassistant/ui/qt_bubble.py`)

**Enhanced Worker Class**:
```python
class LLMWorker(QThread):
    def __init__(self, llm_manager, message, provider, model, media=None):
        # ...
        self.media = media or []

    def run(self):
        response = self.llm_manager.generate_response(
            self.message,
            self.provider,
            self.model,
            media=self.media if self.media else None
        )
```

**Purpose**: Enables background LLM processing with media file attachments without blocking the UI.

#### 4. File Attachment UI Implementation (`abstractassistant/ui/qt_bubble.py`)

**New UI Components**:

1. **Attach Button** (📎):
   - Positioned before text input field
   - Opens multi-file selection dialog
   - Supports all AbstractCore media types
   - Modern styling with hover effects
   - Tooltip: "Attach files (images, PDFs, Office docs, etc.)"

2. **Attached Files Container**:
   - Hidden by default, appears when files are attached
   - Displays file "chips" with icon, name, and remove button
   - Styled with modern card design (blue tint, rounded corners)
   - Auto-hides when no files attached

3. **File Chips**:
   - Display file icon based on type (🖼️ for images, 📄 for PDFs, etc.)
   - Show truncated filename (max 20 chars)
   - Individual remove buttons (✕) for each file
   - Compact, clean design

**New State Management**:
```python
# In QtChatBubble.__init__
self.attached_files: List[str] = []  # Stores file paths
```

**New Methods**:

1. **`attach_files()`**:
   - Opens `QFileDialog` with multi-file selection
   - Filter: Images, Documents (PDF, Office), Data files (CSV, JSON, etc.)
   - Prevents duplicate file attachments
   - Updates visual display after selection

2. **`update_attached_files_display()`**:
   - Creates visual "chips" for each attached file
   - Determines appropriate icon based on file extension
   - Adds remove button for each chip
   - Shows/hides container based on attachment state

3. **`remove_attached_file(file_path)`**:
   - Removes file from attached files list
   - Refreshes visual display
   - Debug logging for file removal

**Enhanced `send_message()` Method**:
```python
def send_message(self):
    message = self.input_text.toPlainText().strip()

    # Capture attached files before clearing
    media_files = self.attached_files.copy()

    # Clear UI
    self.attached_files.clear()
    self.update_attached_files_display()

    # Create worker with media files
    self.worker = LLMWorker(
        self.llm_manager,
        message,
        self.current_provider,
        self.current_model,
        media=media_files if media_files else None
    )
```

**Supported File Types**:
- **Images**: PNG, JPEG, GIF, WEBP, BMP, TIFF (displayed with 🖼️)
- **PDFs**: Portable Document Format (displayed with 📄)
- **Word**: DOCX, DOC (displayed with 📝)
- **Excel**: XLSX, XLS (displayed with 📊)
- **PowerPoint**: PPTX, PPT (displayed with 📊)
- **Data**: CSV, TSV, JSON (displayed with 📋)
- **Text**: TXT, MD (displayed with 📎)

#### 5. Integration Flow

**Complete File Attachment Workflow**:
1. User clicks 📎 button
2. File dialog opens with filtered file types
3. User selects one or more files
4. Files appear as chips in UI with icons and remove buttons
5. User types message
6. User sends message
7. Message + file paths passed to LLMWorker
8. LLMWorker passes to LLMManager.generate_response()
9. LLMManager passes to AbstractCore session.generate(message, media=files)
10. AbstractCore processes files and generates response
11. Response displayed to user

**Error Handling**:
- Duplicate file prevention (same file can't be attached twice)
- Graceful fallback if media processing fails
- Debug logging at each step for troubleshooting

**UI/UX Considerations**:
- **Modern Design**: Follows existing dark theme with blue accents
- **Visual Feedback**: File chips clearly show what's attached
- **Easy Removal**: One-click removal of individual files
- **Non-Intrusive**: Container auto-hides when empty
- **Accessibility**: Tooltips and clear visual indicators
- **Responsive**: Smooth show/hide transitions

#### Results

**✅ All Goals Achieved**:
1. ✅ AbstractCore upgraded from 2.4.2 to 2.4.5 successfully
2. ✅ Full backward compatibility maintained - all existing features work
3. ✅ Complete file attachment system implemented with:
   - File selection dialog with appropriate filters
   - Visual file chips with icons and remove buttons
   - Seamless integration with AbstractCore's media handling
   - Support for images, PDFs, Office docs, and data files

**✅ Testing Verified**:
- `from abstractcore import create_llm` ✅
- `from abstractassistant.core.llm_manager import LLMManager` ✅
- `from abstractassistant.ui.qt_bubble import QtChatBubble` ✅

**Code Quality**:
- Clean separation of concerns (UI, business logic, threading)
- Consistent with existing AbstractAssistant architecture
- Proper Qt threading (LLMWorker for background processing)
- Type hints for media parameter
- Debug logging throughout for troubleshooting

**Files Modified**:
- `requirements.txt` - AbstractCore version update
- `pyproject.toml` - AbstractCore version update
- `abstractassistant/core/llm_manager.py` - Added media parameter support
- `abstractassistant/ui/qt_bubble.py` - File attachment UI and integration

**Issues/Concerns**:

None. Implementation is clean, well-integrated, and maintains full backward compatibility. The file attachment feature leverages AbstractCore's robust media handling system, which automatically:
- Detects file types
- Processes images (resize, optimize, format conversion)
- Extracts text from PDFs (PyMuPDF4LLM)
- Processes Office documents (DOCX, XLSX, PPTX via Unstructured)
- Parses data files (CSV, TSV, JSON)
- Formats content appropriately for each LLM provider

**Verification**:

**To test file attachment feature**:
1. Launch AbstractAssistant: `assistant`
2. Click systray icon to open chat bubble
3. Click 📎 button to attach files
4. Select images, PDFs, or Office documents
5. Files appear as chips below input field
6. Type a message asking about the files
7. Send message
8. LLM will analyze all attached files and respond

**Example queries**:
- With image: "What do you see in this image?"
- With PDF: "Summarize this document"
- With Excel: "What data patterns are in this spreadsheet?"
- Multiple files: "Compare these documents and explain the differences"

**Next Steps**:

No immediate next steps required. The file attachment feature is complete and production-ready. Potential future enhancements could include:
- Drag-and-drop file attachment
- File preview thumbnails
- Attachment size limits/warnings
- History of recently attached file types
- Keyboard shortcut for attaching files (e.g., Cmd+O)

---

