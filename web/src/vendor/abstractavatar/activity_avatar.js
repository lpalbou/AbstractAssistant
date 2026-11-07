import { jsx as _jsx } from "react/jsx-runtime";
import { useEffect, useRef, useState } from "react";
import { AvatarRenderer, avatarGazeTarget, avatarPaletteFromCss } from "./avatar_renderer.js";
import { avatarFrameInterval, avatarResolution } from "./avatar_quality.js";
/** The shown side is rounded up to this step and settles for this long before the raster follows it. */
const SHOWN_STEP = 16, SHOWN_SETTLE_MS = 150;
/** Presentation only; a host can wrap this in its own accessible activation control. */
export function ActivityAvatar({ design = "watch-hover", pose = "ready", level = 0, bands, size = 128, quality = "balanced", animated = true, active = true, followCursor = false, palette, className, label, onError }) {
    const canvas = useRef(null), latest = useRef({ design, pose, level, bands });
    latest.current = { design, pose, level, bands };
    const [error, setError] = useState(false), errorHandler = useRef(onError);
    const animationClock = useRef({ elapsed: 0, previous: undefined });
    errorHandler.current = onError;
    const [pixelRatio, setPixelRatio] = useState(1);
    useEffect(() => {
        let query;
        const refresh = () => {
            query?.removeEventListener("change", refresh);
            const ratio = window.devicePixelRatio || 1;
            setPixelRatio(ratio);
            query = matchMedia(`(resolution: ${ratio}dppx)`);
            query.addEventListener("change", refresh);
        };
        refresh();
        window.addEventListener("resize", refresh, { passive: true });
        return () => { window.removeEventListener("resize", refresh); query?.removeEventListener("change", refresh); };
    }, []);
    // The raster follows the side the canvas is actually shown at, never more than `size`: a host
    // stylesheet may shrink the canvas (the compact 48px avatar beside a question), and drawing
    // the full-size raster there costs many times the pixels for the same picture. The side is
    // rounded up to 16px steps and a later change waits until the size has been steady for 150ms,
    // so a fluid canvas (a window being dragged) rebuilds its renderer once, not on every frame.
    // `undefined` = not measured yet (no renderer is built before the first measurement, so a
    // shrunken canvas is never built twice on mount); 0 = not laid out, use `size`.
    const [shown, setShown] = useState();
    useEffect(() => {
        const el = canvas.current;
        if (!el)
            return;
        let settle, first = true;
        const observer = new ResizeObserver(entries => {
            const box = entries[0]?.contentRect;
            const side = box ? Math.ceil(Math.min(box.width, box.height) / SHOWN_STEP) * SHOWN_STEP : 0;
            if (first) {
                first = false;
                setShown(side);
                return;
            }
            if (settle !== undefined)
                clearTimeout(settle);
            // A canvas that stops being laid out keeps its renderer until it is shown again.
            settle = side > 0 ? setTimeout(() => { settle = undefined; setShown(side); }, SHOWN_SETTLE_MS) : undefined;
        });
        observer.observe(el);
        return () => { observer.disconnect(); if (settle !== undefined)
            clearTimeout(settle); };
    }, []);
    // An invalid size or quality is reported through onError by the renderer effect (resolution 0).
    const raster = () => Math.min(avatarResolution(size, pixelRatio, quality), avatarResolution(Math.min(size, shown || size), pixelRatio, quality));
    let resolution = 0;
    try {
        resolution = raster();
    }
    catch { /* rethrown below, inside the effect */ }
    // Equal palette contents must not recreate a renderer on parent/audio updates.
    const paletteKey = palette ? JSON.stringify(palette) : "theme";
    useEffect(() => {
        const el = canvas.current;
        if (!el || !active || shown === undefined)
            return;
        const abort = new AbortController();
        let disposed = false, renderer, visible = true, lost = false;
        let timer, idle;
        let animationFrame, deadline;
        // Gaze exists only for the design that accepted it (catalog `gaze: "eyes"`): the drawn
        // `gaze` eases toward the pointer `target` and, after two idle seconds, back to centre.
        let gaze, target = [0, 0];
        let gazeDesign, tracking = false, eased = 0;
        const motion = matchMedia("(prefers-reduced-motion: reduce)");
        const clock = animationClock.current;
        let renderedPose;
        const clear = () => {
            if (timer !== undefined) {
                clearTimeout(timer);
                timer = undefined;
            }
            if (animationFrame !== undefined) {
                cancelAnimationFrame(animationFrame);
                animationFrame = undefined;
            }
        };
        const resetGaze = () => {
            if (idle !== undefined) {
                clearTimeout(idle);
                idle = undefined;
            }
            tracking = false;
            gaze = undefined;
            target = [0, 0];
            gazeDesign = undefined;
        };
        const fail = (reason) => {
            if (disposed)
                return;
            clear();
            resetGaze();
            el.getContext("2d")?.clearRect(0, 0, el.width, el.height);
            setError(true);
            errorHandler.current?.(reason instanceof Error ? reason : new Error(String(reason)));
        };
        const draw = () => {
            clear();
            const s = latest.current;
            if (renderedPose !== s.pose) {
                deadline = undefined;
                renderedPose = s.pose;
            }
            if (!animated || motion.matches || !visible || lost || document.hidden || s.pose !== "ready" || gazeDesign !== s.design)
                resetGaze();
            if (disposed || !renderer || !visible || lost || document.hidden) {
                clock.previous = undefined;
                deadline = undefined;
                return;
            }
            try {
                const moving = animated && !motion.matches, now = performance.now();
                if (moving && clock.previous !== undefined)
                    clock.elapsed = (clock.elapsed + Math.min(1, (now - clock.previous) / 1000)) % 86400;
                clock.previous = moving ? now : undefined;
                if (gaze) {
                    const k = 1 - Math.exp(-Math.min(250, now - eased) / 150);
                    eased = now;
                    gaze = [gaze[0] + (target[0] - gaze[0]) * k, gaze[1] + (target[1] - gaze[1]) * k];
                    if (idle === undefined && Math.hypot(gaze[0], gaze[1]) < .01)
                        resetGaze();
                }
                renderer.renderFrame({ schema_version: 1, style: s.design, state: s.pose, level: s.level,
                    time: moving ? clock.elapsed : 0,
                    ...(gaze === undefined ? {} : { gaze }), ...(s.bands === undefined ? {} : { bands: s.bands }) });
                setError(false);
                if (animated && !motion.matches && s.pose !== "error") {
                    const period = avatarFrameInterval(quality, s.pose, tracking);
                    const finished = performance.now();
                    deadline = deadline === undefined ? now + period : deadline + period;
                    // Skip missed deadlines instead of catching up with bursts.
                    if (deadline < finished)
                        deadline = finished + period;
                    timer = setTimeout(() => {
                        timer = undefined;
                        animationFrame = requestAnimationFrame(() => { animationFrame = undefined; draw(); });
                    }, Math.max(0, deadline - finished));
                }
                else
                    deadline = undefined;
            }
            catch (e) {
                fail(e);
            }
        };
        const move = (event) => {
            const design = latest.current.design;
            if (!renderer || !visible || lost || document.hidden || !animated || motion.matches || latest.current.pose !== "ready")
                return;
            const pointer = avatarGazeTarget(renderer.designs.find(d => d.id === design), event, el.getBoundingClientRect());
            if (!pointer)
                return;
            if (!gaze) {
                gaze = [0, 0];
                eased = performance.now();
            }
            target = pointer;
            gazeDesign = design;
            const wasTracking = tracking;
            tracking = true;
            if (idle !== undefined)
                clearTimeout(idle);
            idle = setTimeout(() => { idle = undefined; target = [0, 0]; }, 2000);
            // Later movements only change the sampled target, never reset the draw clock.
            if (!wasTracking)
                deadline = undefined;
            if (!wasTracking)
                draw();
        };
        const down = (event) => {
            // Observe the click; the host keeps focus, selection and activation.
            move(event);
        };
        const observer = new IntersectionObserver(entries => { visible = entries[0]?.isIntersecting ?? false; draw(); });
        observer.observe(el);
        motion.addEventListener("change", draw);
        document.addEventListener("visibilitychange", draw);
        el.addEventListener("avatar-update", draw);
        if (followCursor) {
            window.addEventListener("pointermove", move, { passive: true });
            window.addEventListener("pointerdown", down, { passive: true });
        }
        const contextLost = (event) => { event.preventDefault(); lost = true; clear(); resetGaze(); setError(true); };
        const contextRestored = () => { lost = false; draw(); };
        el.addEventListener("contextlost", contextLost);
        el.addEventListener("contextrestored", contextRestored);
        const theme = new MutationObserver(() => {
            if (renderer && !palette) {
                try {
                    renderer.setPalette(avatarPaletteFromCss(el));
                    draw();
                }
                catch (e) {
                    fail(e);
                }
            }
        });
        if (!palette) {
            const options = { attributes: true, attributeFilter: ["data-theme", "data-af-theme", "class", "style"] };
            theme.observe(document.documentElement, options);
            if (document.body)
                theme.observe(document.body, options);
        }
        Promise.resolve().then(() => {
            if (disposed)
                return;
            const side = resolution || raster();
            return AvatarRenderer.create(el, { width: side, height: side, palette: palette ?? avatarPaletteFromCss(el), signal: abort.signal });
        }).then(r => {
            if (!r)
                return;
            if (disposed) {
                r.dispose();
                return;
            }
            renderer = r;
            setError(false);
            draw();
        }).catch(fail);
        return () => {
            disposed = true;
            abort.abort();
            clock.previous = undefined;
            clear();
            resetGaze();
            observer.disconnect();
            theme.disconnect();
            motion.removeEventListener("change", draw);
            document.removeEventListener("visibilitychange", draw);
            el.removeEventListener("avatar-update", draw);
            window.removeEventListener("pointermove", move);
            window.removeEventListener("pointerdown", down);
            el.removeEventListener("contextlost", contextLost);
            el.removeEventListener("contextrestored", contextRestored);
            renderer?.dispose();
        };
    }, [resolution, shown === undefined, quality, paletteKey, animated, active, followCursor]);
    useEffect(() => { canvas.current?.dispatchEvent(new Event("avatar-update")); }, [design, pose]);
    // Audio producers cannot reset or outrun the clock; reduced motion allows explicit data updates.
    useEffect(() => {
        if (!animated || matchMedia("(prefers-reduced-motion: reduce)").matches)
            canvas.current?.dispatchEvent(new Event("avatar-update"));
    }, [level, bands, animated]);
    return _jsx("canvas", { ref: canvas, className: className, style: { width: size, height: size, visibility: active ? "visible" : "hidden" }, "aria-hidden": !active, role: "img", "aria-label": error ? "Avatar unavailable" : label ?? `${design} · ${pose}` });
}
