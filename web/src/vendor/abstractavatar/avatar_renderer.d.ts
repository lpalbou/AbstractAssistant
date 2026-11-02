/** Canvas presentation of AbstractAvatar's shared procedural frames. */
export type AvatarPose = "ready" | "thinking" | "working" | "listening" | "speaking" | "waiting" | "error";
export type AvatarColor = readonly [
    number,
    number,
    number,
    number
];
export interface AvatarPalette {
    background: AvatarColor;
    warm: AvatarColor;
    eye: AvatarColor;
    shadow: AvatarColor;
    highlight: AvatarColor;
    muted: AvatarColor;
}
export interface AvatarDesign {
    id: string;
    name: string;
    description: string;
    watchCode: string;
    family: string;
    /** Catalog field 5: "eyes" when the design has eyes that may follow the pointer. A
     * catalog without the field, or with any other value, means "none": nothing follows. */
    gaze: "eyes" | "none";
}
/** Versioned frame request. Generation remains in AbstractAvatar, not a script interpreter. */
export interface AvatarFrameDescriptor {
    schema_version: 1;
    style: string;
    state: AvatarPose;
    time: number;
    level: number;
    gaze?: readonly [number, number];
    bands?: readonly number[];
}
/** Trusted local AbstractAvatar module bytes, useful for offline embedding and tests.
 * Never pass untrusted uploaded/external Wasm; a frame descriptor contains data only. */
export type AvatarSource = BufferSource;
export declare function parseAvatarFrame(value: unknown): AvatarFrameDescriptor;
/** The one pointer-to-gaze rule for every host: a normalized gaze target for a design whose
 * catalog says it has eyes, from a mouse or pen position relative to the avatar's bounds.
 * Any other design, touch input or empty bounds gets undefined: the renderer moves only
 * eyes, and nothing at all for a design without them. */
export declare function avatarGazeTarget(design: AvatarDesign | undefined, pointer: {
    clientX: number;
    clientY: number;
    pointerType?: string;
}, bounds: {
    x: number;
    y: number;
    width: number;
    height: number;
}): readonly [number, number] | undefined;
export declare function avatarDesigns(source?: AvatarSource): Promise<readonly AvatarDesign[]>;
export declare class AvatarRenderer {
    private readonly core;
    private handle;
    private readonly context;
    private readonly image;
    readonly designs: readonly AvatarDesign[];
    private constructor();
    static create(canvas: HTMLCanvasElement, options: {
        width?: number;
        height?: number;
        palette: AvatarPalette;
        source?: AvatarSource;
        signal?: AbortSignal;
    }): Promise<AvatarRenderer>;
    setPalette(p: AvatarPalette): void;
    draw(style: string, pose: AvatarPose, level: number, time: number, gaze?: readonly [number, number]): void;
    private paint;
    /** Read a validated frame request using the shared generator's raster contract. */
    renderFrame(value: AvatarFrameDescriptor): void;
    dispose(): void;
}
/** Resolve existing semantic CSS tokens; caller may supply an explicit palette instead. */
export declare function avatarPaletteFromCss(canvas: HTMLCanvasElement): AvatarPalette;
//# sourceMappingURL=avatar_renderer.d.ts.map