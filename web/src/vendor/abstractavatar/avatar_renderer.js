const poses = ["ready", "thinking", "working", "listening", "speaking", "waiting", "error"];
const unit = (value) => typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
export function parseAvatarFrame(value) {
    if (value === null || typeof value !== "object" || Array.isArray(value))
        throw new Error("Avatar frame must be an object");
    const v = value;
    if (Object.keys(v).some(key => !["schema_version", "style", "state", "time", "level", "gaze", "bands"].includes(key)))
        throw new Error("Unknown avatar frame field");
    if (v.schema_version !== 1 || typeof v.style !== "string" || !/^[a-z][a-z0-9_-]{0,63}$/.test(v.style)
        || !poses.includes(v.state) || typeof v.time !== "number" || !Number.isFinite(v.time)
        || v.time < 0 || v.time > 86400 || !unit(v.level))
        throw new Error("Invalid avatar frame version, style, state, time or level");
    if (v.gaze !== undefined && (!Array.isArray(v.gaze) || v.gaze.length !== 2
        || v.gaze.some(n => typeof n !== "number" || !Number.isFinite(n) || n < -1 || n > 1)))
        throw new Error("Avatar gaze requires two normalized coordinates");
    if (v.bands !== undefined && (!Array.isArray(v.bands) || v.bands.length !== 8 || !v.bands.every(unit)))
        throw new Error("Avatar bands require eight normalized levels");
    return {
        schema_version: 1, style: v.style, state: v.state, time: v.time, level: v.level,
        ...(v.gaze === undefined ? {} : { gaze: [...v.gaze] }),
        ...(v.bands === undefined ? {} : { bands: [...v.bands] }),
    };
}
let shared;
async function instantiate(source) {
    let bytes;
    if (source !== undefined)
        bytes = source;
    else {
        const response = await fetch(new URL("./avatars/avatar_core.wasm", import.meta.url));
        if (!response.ok)
            throw new Error(`Avatar renderer unavailable (${response.status})`);
        bytes = await response.arrayBuffer();
    }
    if (bytes.byteLength > 8 * 1024 * 1024)
        throw new Error("Avatar renderer module exceeds the size limit");
    const module = await WebAssembly.compile(bytes);
    if (WebAssembly.Module.imports(module).length !== 0)
        throw new Error("Avatar renderer must not import host capabilities");
    const instance = await WebAssembly.instantiate(module);
    const core = instance.exports;
    const functions = ["avatar_abi_version", "avatar_style_count", "avatar_style_field_ptr", "avatar_style_field_len",
        "avatar_create", "avatar_destroy", "avatar_set_shade", "avatar_set_gaze", "avatar_set_bands", "avatar_render", "avatar_pixels", "avatar_pixels_len"];
    if (!(core.memory instanceof WebAssembly.Memory) || core.memory.buffer.byteLength > 64 * 1024 * 1024
        || functions.some(name => typeof core[name] !== "function") || core.avatar_abi_version() !== 1)
        throw new Error("Unsupported avatar renderer version");
    return core;
}
async function load(source) {
    if (source)
        return instantiate(source);
    if (!shared)
        shared = instantiate().catch(e => { shared = undefined; throw e; });
    return shared;
}
function catalog(core) {
    const decoder = new TextDecoder("utf-8", { fatal: true });
    const field = (s, f) => {
        const start = core.avatar_style_field_ptr(s, f) >>> 0, length = core.avatar_style_field_len(s, f);
        if (!Number.isInteger(length) || length < 0 || length > 512 || start + length > core.memory.buffer.byteLength)
            throw new Error("Invalid avatar catalog field bounds");
        return decoder.decode(new Uint8Array(core.memory.buffer, start, length));
    };
    const count = core.avatar_style_count();
    if (!Number.isInteger(count) || count < 1 || count > 256)
        throw new Error("Invalid avatar catalog size");
    const designs = Array.from({ length: count }, (_, i) => ({ id: field(i, 0), name: field(i, 1), description: field(i, 2), watchCode: field(i, 3), family: field(i, 4) }));
    if (new Set(designs.map(d => d.id)).size !== count || designs.some(d => !/^[a-z][a-z0-9_-]{0,63}$/.test(d.id)))
        throw new Error("Invalid avatar catalog identity");
    return designs;
}
export async function avatarDesigns(source) { return catalog(await load(source)); }
function pack(c) {
    if (c.length !== 4 || c.some(v => !Number.isInteger(v) || v < 0 || v > 255))
        throw new Error("Avatar colors require four bytes");
    return ((c[0] << 24) | (c[1] << 16) | (c[2] << 8) | c[3]) >>> 0;
}
const mix = (a, b, t) => a.map((v, i) => Math.round(v + (b[i] - v) * t));
export class AvatarRenderer {
    constructor(core, canvas, width, height) {
        this.core = core;
        const context = canvas.getContext("2d");
        if (!context)
            throw new Error("Avatar requires a Canvas 2D context");
        const image = context.createImageData(width, height);
        this.designs = catalog(core);
        const h = core.avatar_create(width, height);
        if (!h)
            throw new Error("Avatar size or live renderer limit exceeded");
        this.handle = h;
        this.context = context;
        canvas.width = width;
        canvas.height = height;
        this.image = image;
    }
    static async create(canvas, options) {
        const width = options.width ?? 128, height = options.height ?? width;
        if (!Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1 || width > 512 || height > 512)
            throw new Error("Avatar dimensions must be 1–512 pixels");
        if (options.signal?.aborted)
            throw new DOMException("Avatar renderer creation cancelled", "AbortError");
        const core = await load(options.source);
        if (options.signal?.aborted)
            throw new DOMException("Avatar renderer creation cancelled", "AbortError");
        const renderer = new AvatarRenderer(core, canvas, width, height);
        try {
            renderer.setPalette(options.palette);
            return renderer;
        }
        catch (e) {
            renderer.dispose();
            throw e;
        }
    }
    setPalette(p) {
        if (!this.handle)
            throw new Error("Avatar renderer disposed");
        [p.background, p.warm, p.eye, p.shadow, p.highlight, p.muted].forEach(pack);
        for (const [material, mid, hi] of [[0, p.warm, p.highlight], [1, p.eye, p.highlight], [2, p.shadow, p.muted]]) {
            for (let i = 0; i < 256; i++) {
                const t = i / 255;
                const ink = t < 0.65 ? mix(p.background, mid, t / 0.65) : mix(mid, hi, (t - 0.65) / 0.35);
                if (this.core.avatar_set_shade(this.handle, material, i, pack(ink)) !== 0)
                    throw new Error("Avatar palette update failed");
            }
        }
    }
    draw(style, pose, level, time, gaze) {
        this.renderFrame({ schema_version: 1, style, state: pose, level, time, ...(gaze === undefined ? {} : { gaze }) });
    }
    paint(style, pose, level, time, gaze) {
        if (!this.handle)
            throw new Error("Avatar renderer disposed");
        const index = this.designs.findIndex(d => d.id === style), phase = poses.indexOf(pose);
        if (index < 0 || phase < 0 || !Number.isFinite(level) || !Number.isFinite(time))
            throw new Error("Invalid avatar style, pose, level or time");
        if (gaze && gaze.some(v => !Number.isFinite(v)))
            throw new Error("Invalid avatar gaze");
        if (this.core.avatar_set_gaze(this.handle, gaze?.[0] ?? 0, gaze?.[1] ?? 0) !== 0)
            throw new Error("Avatar gaze update failed");
        const result = this.core.avatar_render(this.handle, index, phase, level, time, 1);
        if (result !== 0)
            throw new Error(`Avatar rendering failed (${result})`);
        const ptr = this.core.avatar_pixels(this.handle) >>> 0, len = this.core.avatar_pixels_len(this.handle);
        if (len !== this.image.data.length || ptr + len > this.core.memory.buffer.byteLength
            || this.core.memory.buffer.byteLength > 64 * 1024 * 1024)
            throw new Error("Invalid avatar raster frame bounds");
        this.image.data.set(new Uint8Array(this.core.memory.buffer, ptr, len));
        this.context.putImageData(this.image, 0, 0);
    }
    /** Read a validated frame request using the shared generator's raster contract. */
    renderFrame(value) {
        const frame = parseAvatarFrame(value);
        if (!this.handle)
            throw new Error("Avatar renderer disposed");
        // Absent measured bands mean the scalar envelope in every band, matching
        // the native descriptor binding. An explicit zero vector means silence.
        const bands = frame.bands ?? Array(8).fill(frame.level);
        if (this.core.avatar_set_bands(this.handle, bands[0], bands[1], bands[2], bands[3], bands[4], bands[5], bands[6], bands[7]) !== 0)
            throw new Error("Avatar audio-band update failed");
        this.paint(frame.style, frame.state, frame.level, frame.time, frame.gaze);
    }
    dispose() {
        if (this.handle) {
            this.core.avatar_destroy(this.handle);
            this.handle = 0;
        }
    }
}
/** Resolve existing semantic CSS tokens; caller may supply an explicit palette instead. */
export function avatarPaletteFromCss(canvas) {
    const style = getComputedStyle(canvas), probe = canvas.ownerDocument.createElement("canvas");
    probe.width = probe.height = 1;
    const ctx = probe.getContext("2d");
    if (!ctx)
        throw new Error("Avatar theme color conversion unavailable");
    const color = (token) => {
        const value = style.getPropertyValue(token).trim();
        if (!value)
            throw new Error(`Avatar theme token missing: ${token}`);
        ctx.clearRect(0, 0, 1, 1);
        ctx.fillStyle = value;
        ctx.fillRect(0, 0, 1, 1);
        return Array.from(ctx.getImageData(0, 0, 1, 1).data);
    };
    const background = color("--bg-primary"), border = color("--ui-border-2"), a = border[3] / 255;
    const shadow = [Math.round(border[0] * a + background[0] * (1 - a)), Math.round(border[1] * a + background[1] * (1 - a)), Math.round(border[2] * a + background[2] * (1 - a)), 255];
    return { background, warm: color("--warning"), eye: color("--error"), shadow, highlight: color("--text-primary"), muted: color("--text-secondary") };
}
