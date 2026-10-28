/**
 * The run input the web Assistant sends to the managed assistant workflow:
 * a PORT of abstractassistant/gateway/run_input.py `build_run_input_data`,
 * with the SAME snake_case argument names so the parity test can feed both
 * builders the same cases (src/lib/__fixtures__/run_input_parity.json,
 * generated FROM the Python builder by scripts/gen_run_input_parity.py).
 *
 * Not ported, on purpose (web v1 offers neither): `media_overrides` (the
 * per-route media model pins) and `speculation`. Passing them is a type error.
 *
 * The contract, in short (run_input.py:106-143):
 * - history belongs to the gateway: `use_session_history` (default true)
 *   asks it to replay the session's durable turns; `messages` is sent only
 *   with `use_context`;
 * - a provider/model override needs BOTH and rides two channels: top-level
 *   pins (the router llm_call node) and `_runtime` (agent nodes); a half pin
 *   is dropped;
 * - `thinking` and `stream` ride `_runtime`; `stream` undefined sends nothing
 *   (the gateway's `agents.streaming_default` applies);
 * - `workspace_root` blank sends nothing.
 */

export type ChatMessageIn = { role?: unknown; content?: unknown };
export type ArtifactRef = Record<string, unknown> & { $artifact?: unknown };

/** The tool part (`tools`, `_runtime.allowed_tools`, `_runtime.tool_policy`) is NOT built here:
 * the kit's `planRunTools` + `withRunTools` (ui-kit tool_plan, backlog 0033) add it to this input. */
export type RunInputArgs = {
  prompt: string;
  system?: string;
  messages?: ChatMessageIn[];
  attachments?: ArtifactRef[];
  temperature?: number | null;
  seed?: number | null;
  max_iterations?: number;
  use_context?: boolean;
  use_session_history?: boolean;
  primary_image_artifact?: ArtifactRef | null;
  provider?: string;
  model?: string;
  base_url?: string;
  thinking?: string;
  stream?: boolean | null;
  workspace_root?: string;
};

function toChatMessages(messages: ChatMessageIn[], keep: number): Array<{ role: string; content: string }> {
  const out: Array<{ role: string; content: string }> = [];
  for (const m of messages || []) {
    if (!m || typeof m !== "object") continue;
    const role = String(m.role ?? "").trim();
    if (!["user", "assistant", "system"].includes(role)) continue;
    const content = String(m.content ?? "");
    if (!content.trim()) continue;
    out.push({ role, content });
  }
  return keep <= 0 ? out : out.slice(-keep);
}

const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const hasRef = (a: unknown): a is ArtifactRef =>
  Boolean(a) && typeof a === "object" && Boolean((a as ArtifactRef).$artifact);

export function buildRunInputData(args: RunInputArgs): Record<string, unknown> {
  const prompt = String(args.prompt ?? "");
  const system = String(args.system ?? "");
  const useContext = Boolean(args.use_context ?? false);
  const useSessionHistory = args.use_session_history ?? true;

  const attachments = (args.attachments || []).filter(hasRef).map((a) => ({ ...a }));
  const messages = useContext ? toChatMessages(args.messages || [], 200) : [];
  const primary =
    hasRef(args.primary_image_artifact) && String(args.primary_image_artifact.$artifact).trim()
      ? { ...args.primary_image_artifact }
      : null;

  const ctx: Record<string, unknown> = { task: prompt, messages };
  if (attachments.length) {
    ctx.attachments = attachments;
    ctx.media = attachments;
  }
  if (primary) ctx.primary_image_artifact = primary;

  const runtime: Record<string, unknown> = {};
  if (isNum(args.temperature)) runtime.temperature = args.temperature;
  if (isNum(args.seed) && Number.isInteger(args.seed)) runtime.seed = args.seed;

  const provider = String(args.provider ?? "").trim();
  const model = String(args.model ?? "").trim();
  const baseUrl = String(args.base_url ?? "").trim();
  const override = Boolean(provider && model);
  if (override) {
    runtime.provider = provider;
    runtime.model = model;
    if (baseUrl) runtime.base_url = baseUrl;
  }

  const thinking = String(args.thinking ?? "").trim().toLowerCase();
  if (thinking) runtime.thinking = thinking;
  if (args.stream !== undefined && args.stream !== null) {
    if (typeof args.stream !== "boolean") throw new Error(`stream must be null, true or false, not ${JSON.stringify(args.stream)}`);
    runtime.stream = args.stream;
  }

  const out: Record<string, unknown> = {
    prompt,
    context: ctx,
    use_context: useContext,
    use_session_history: Boolean(useSessionHistory),
    _runtime: runtime,
    max_iterations: Math.max(1, Math.trunc(args.max_iterations ?? 50)),
    has_primary_image_context: primary !== null,
  };
  if (override) {
    out.provider = provider;
    out.model = model;
    if (baseUrl) out.base_url = baseUrl;
  }
  if (system) out.system = system;
  if (attachments.length) out.attachments = attachments;
  if (primary) out.primary_image_artifact = primary;
  if (isNum(args.temperature)) out.temperature = args.temperature;
  if (isNum(args.seed) && Number.isInteger(args.seed)) out.seed = args.seed;
  const root = String(args.workspace_root ?? "").trim();
  if (root) out.workspace_root = root;
  return out;
}
