import React from "react";
export type ToolSandboxRow = {
    path: string;
    /** "Read & write" | "Read-only" | "Refused" */
    mode: string;
    /** True for the run's private workspace. */
    private?: boolean;
};
export type ToolSandbox = {
    /** "sandboxed" (an OS sandbox ran the command), "refused" (no sandbox: nothing ran),
     *  "unsandboxed" (the host allowed commands without a sandbox). */
    state: "sandboxed" | "refused" | "unsandboxed";
    kind: string;
    label: string;
    /** The one line shown for the call. */
    line: string;
    /** The paths the sandbox enforced (empty when refused). */
    rows: ToolSandboxRow[];
    /** Built-in protected folders refused on top of the rows (host policy; counted, never listed). */
    builtinRefused: number;
};
/** The sandbox evidence of one tool result: `result.output.sandbox` (or `sandbox` on the value given). */
export declare function sandboxEvidence(value: unknown): Record<string, any> | null;
/** One tool call's sandbox, or null when its result carries no sandbox evidence. */
export declare function toolSandbox(value: unknown): ToolSandbox | null;
/** The line (and, for a sandboxed call, the enforced paths) in a tool call's detail. */
export declare function ToolSandboxLine({ sandbox, className }: {
    sandbox: ToolSandbox | null | undefined;
    className?: string;
}): React.ReactElement | null;
//# sourceMappingURL=sandbox_line.d.ts.map