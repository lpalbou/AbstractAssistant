import React from "react";
import type { AutomationSummary } from "@abstractframework/ui-kit";
/** Same facts as the Watch ScheduleLine; never derives a scheduled fire time. */
export declare function automationCardSchedule(s: AutomationSummary): string;
/** A duration UNTIL a gateway-served time, matching the Watch's compact countdown. */
export declare function automationCardNext(at: string | undefined, nowMs: number): string;
export interface AutomationCardProps {
    summary: AutomationSummary;
    selected?: boolean;
    nowMs: number;
    onOpen: () => void;
    onArchive?: () => void;
    archiveDisabled?: boolean;
    archiveTitle?: string;
    disabled?: boolean;
    className?: string;
}
/** Controlled Watch-style automation row. Pause/resume belongs in the editor, not the list. */
export declare function AutomationCard(p: AutomationCardProps): React.ReactElement;
//# sourceMappingURL=automation_card.d.ts.map