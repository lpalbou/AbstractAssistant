import React from "react";
import type { WorkflowStatistics } from "./workflow_evidence.js";
import { type StatDetail } from "./stat_detail.js";
export type ChatStat = {
    id?: string;
    label: string;
    /** A ONE-line hint. A multi-line explanation is a `detail` (the message footer spec:
     *  every workflow chip opens the structured panel, never a native multi-line tooltip). */
    title?: string;
    icon?: React.ReactNode;
    onClick?: () => void;
    /** Structured detail (tokens / time / tools). When present the chip opens
     *  a hover/focus panel instead of a native one-line `title`. */
    detail?: StatDetail;
};
/** The workflow stat chips (2026-09-22 rework). The native `title` held one
 *  or two lines ("Input: 5,996 · Output: 423"); the ledger carries the cache
 *  split, measured TTFT, generation rate, speculation and per-tool timing.
 *  `statDetail` (pure, see stat_detail.tsx) folds them into sections; the
 *  chip renders them as a structured panel. Absent metrics read "not
 *  reported", never 0. */
export declare function workflowStats(metrics: WorkflowStatistics): ChatStat[];
/** A turn's stat chips (a message card's, or a tools-only turn's under its tool group). */
export declare function ChatStatsRow({ stats }: {
    stats: ChatStat[];
}): React.ReactElement;
//# sourceMappingURL=chat_stats.d.ts.map