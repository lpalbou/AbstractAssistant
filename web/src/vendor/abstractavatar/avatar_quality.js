// A single portrait (balanced, high) moves at one smooth rate in every animated pose: the
// resting Ready and Waiting motion at 6–12 fps read as a stutter in the avatar views. Only
// economy, meant for grids of small previews, keeps slower idle rates to bound their total cost.
const budgets = {
    economy: { pixels: 256, ratio: 1.5, active: 12, ready: 2, waiting: 6 },
    balanced: { pixels: 384, ratio: 2, active: 24, ready: 24, waiting: 24 },
    high: { pixels: 512, ratio: 3, active: 30, ready: 30, waiting: 30 },
};
function budget(quality) {
    if (!Object.prototype.hasOwnProperty.call(budgets, quality))
        throw new Error("Unknown avatar quality");
    return budgets[quality];
}
export function avatarResolution(size, pixelRatio, quality) {
    if (!Number.isFinite(size) || size <= 0 || size > 4096)
        throw new Error("Avatar display size must be greater than zero and at most 4096 pixels");
    const b = budget(quality);
    const ratio = Number.isFinite(pixelRatio) ? Math.max(1, Math.min(b.ratio, pixelRatio)) : 1;
    return Math.max(1, Math.min(b.pixels, Math.round(size * ratio)));
}
export function avatarFrameInterval(quality, pose, tracking) {
    const b = budget(quality);
    return 1000 / (pose === "ready" && !tracking ? b.ready : pose === "waiting" ? b.waiting : b.active);
}
