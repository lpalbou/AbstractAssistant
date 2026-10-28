/**
 * The Assistant's gateway calls as panel-chat's `WorkflowTransport`: the kit's
 * `WorkflowSessionController` (through `useWorkflowSession`) folds the ledger, follows child
 * runs, keeps live replies and the pending question, and sends the commands. Only the HTTP
 * stays here (src/gateway/client.ts: the host builds every URL and authenticates every call).
 */
import { llmDeltaFromSse, type WorkflowTransport } from "@abstractframework/panel-chat";

import type { GatewayClient } from "./client";

export function createAssistantTransport(client: GatewayClient, opts: { onDeltaError: (message: string) => void }): WorkflowTransport {
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
                  if (parsed) onDelta(parsed);
                },
              }
            : {}),
        },
        signal,
      );
    },
    submitCommand: (command) => client.submitCommand({ ...command, client_id: command.client_id || "abstractassistant-web" }),
  };
}
