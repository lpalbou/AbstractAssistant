import React from "react";
/** What the host knows about the chat being scheduled (all optional). */
export type ScheduleSeed = {
    prompt?: string;
    title?: string;
    /** The chat's target, in the create-request shape (`{bundle_ref, flow_id}` or `{flow_id:"@default", interface}`). */
    target?: {
        flow_id: string;
        bundle_ref?: string;
        interface?: string;
        input_data?: Record<string, unknown>;
    };
};
export type ScheduleThisActionProps = {
    seed: ScheduleSeed;
    onSchedule(seed: ScheduleSeed): void;
    disabled?: boolean;
    /** Defaults to "Schedule this…". */
    label?: string;
    className?: string;
};
export declare function ScheduleThisAction(props: ScheduleThisActionProps): React.ReactElement;
export type FromAutomationBadgeProps = {
    /** The automation's title. */
    title: string;
    /** Occurrence index, when the message belongs to one occurrence. */
    index?: number;
    /** Open the automation (makes the badge a button). */
    onOpen?(): void;
    className?: string;
};
/** "from automation <title> · #<index>". */
export declare function fromAutomationText(title: string, index?: number): string;
export declare function FromAutomationBadge(props: FromAutomationBadgeProps): React.ReactElement;
//# sourceMappingURL=automation_badges.d.ts.map