export declare function tryParseJson(text: string): unknown | null;
export declare function chatToMarkdown(messages: Array<{
    role: string;
    content: string;
    ts?: string;
    title?: string;
}>, opts?: {
    heading?: string;
}): string;
export declare function copyText(text: string): Promise<boolean>;
export declare function downloadTextFile(opts: {
    filename: string;
    text: string;
    mime?: string;
}): void;
//# sourceMappingURL=utils.d.ts.map