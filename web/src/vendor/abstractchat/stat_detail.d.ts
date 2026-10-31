import React from "react";
import type { WorkflowStatistics } from "./workflow_evidence.js";
/**
 * Structured detail for the message-card stat chips (tokens / time / tools / files).
 *
 * WHY STRUCTURED (operator, 2026-09-22): the chips used a native `title`
 * with one or two lines ("Input: 5,996 · Output: 423"), while the run ledger
 * carries the prompt-cache split, measured time-to-first-token, generation
 * rate, speculative-decoding acceptance and per-tool timing. The detail is
 * built here as DATA (`statDetail`, pure and testable in Node) and rendered
 * by `StatDetailPanel`; `StatChip` gives it hover/focus/escape behaviour.
 *
 * Honesty rule, unchanged: a value the ledger did not report reads
 * "not reported" — never 0, which would be a claim.
 */
export type StatDetailKind = "tokens" | "time" | "tools" | "files";
export type StatDetailRow = {
    label: string;
    value: string;
    hint?: string;
};
export type StatDetailSection = {
    heading: string;
    rows?: StatDetailRow[];
    table?: {
        columns: string[];
        rows: string[][];
    };
    note?: string;
};
export type StatDetail = {
    kind: StatDetailKind;
    title: string;
    headline: string;
    sections: StatDetailSection[];
    footer: string[];
};
export declare const formatDuration: (ms?: number) => string;
/** `org/Model-Name` → `Model-Name`; a local path keeps its last segment. */
export declare const shortModel: (model: string) => string;
/** Pure: the structured detail for one chip, from the folded statistics. */
export declare function statDetail(kind: StatDetailKind, statistics: WorkflowStatistics): StatDetail;
/** Plain-text rendering (copy, logs, non-DOM hosts). */
export declare function statDetailText(detail: StatDetail): string;
export declare function StatDetailPanel(props: {
    detail: StatDetail;
    id?: string;
    style?: React.CSSProperties;
    panelRef?: React.Ref<HTMLDivElement>;
    onMouseEnter?: () => void;
    onMouseLeave?: () => void;
}): React.ReactElement;
/**
 * A stat chip whose detail opens on hover or keyboard focus, closes on
 * mouse-out / blur / Escape, and is positioned (in a body portal, so no
 * clipping ancestor can cut it) above the chip — or below when there is no
 * room — clamped inside the viewport.
 */
export declare function StatChip(props: {
    label: string;
    detail: StatDetail;
    className?: string;
    icon?: React.ReactNode;
    onClick?: () => void;
    defaultOpen?: boolean;
}): React.ReactElement;
//# sourceMappingURL=stat_detail.d.ts.map