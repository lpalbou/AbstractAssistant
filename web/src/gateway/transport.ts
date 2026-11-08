/**
 * The Assistant's gateway calls as panel-chat's `WorkflowTransport`. With `replayView` the
 * kit's `WorkflowSessionController` (through `useWorkflowSession`) renders the conversation
 * from the gateway's replay view (`GET runs/{id}/view` + its stream, AbstractGateway >= 0.17.0:
 * status, the pending question wherever in the run tree it waits, messages, tool rows) and opens
 * the ledger stream only for live reply text; on an older gateway it falls back to folding the
 * ledger itself, labeled (`snapshot.source`). Only the HTTP stays here (src/gateway/client.ts:
 * the host builds every URL and authenticates every call).
 */
import { createReplayViewTransport, llmDeltaFromSse, type WorkflowTransport } from "@abstractframework/panel-chat";

import type { GatewayClient } from "./client";

export function createAssistantTransport(
  client: GatewayClient,
  opts: {
    onDeltaError: (message: string) => void;
    /** Every replay view read (the loaded turn, each earlier turn): the Workspace learns which
     * turns are `@` mentions from the view's own `workflow` (lib/mentions.ts). */
    onView?: (view: unknown) => void;
    /** Each live reply frame's `author` (the gateway names the turn's author on every frame), by
     * the frame's run: live text is labelled before the saved message replaces it. */
    onLiveAuthor?: (runId: string, author: unknown) => void;
  },
): WorkflowTransport {
  const views = createReplayViewTransport({ fetch: client.replayFetch });
  const onView = opts.onView;
  return {
    getRun: (runId) => client.getRun(runId),
    getHistory: (runId) => client.historyBundle(runId),
    getLedger: (runId, after) => client.ledgerPage(runId, after),
    async streamLedger(runId, after, onStep, signal, onOpen, onDelta) {
      await client.streamLedger(
        runId,
        after,
        {
          onStep: (step) => onStep({ cursor: step.cursor, record: step.record }),
          onOpen,
          ...(onDelta
            ? {
                onDelta: (event, data) => {
                  let parsed;
                  try {
                    parsed = llmDeltaFromSse(event, data);
                  } catch (err) {
                    // A malformed live frame is reported and skipped; the ledger keeps flowing.
                    opts.onDeltaError(err instanceof Error ? err.message : String(err));
                    return;
                  }
                  if (!parsed) return;
                  const frame = JSON.parse(data) as Record<string, unknown>;
                  if (opts.onLiveAuthor && frame.author !== undefined) opts.onLiveAuthor(String(frame.run_id || ""), frame.author);
                  onDelta(parsed);
                },
              }
            : {}),
        },
        signal,
      );
    },
    submitCommand: (command) => client.submitCommand({ ...command, client_id: command.client_id || "abstractassistant-web" }),
    replayView: onView
      ? {
          ...views,
          async getView(runId, options) {
            const read = await views.getView(runId, options);
            if (!read.notModified) onView(read.view);
            return read;
          },
        }
      : views,
  };
}
