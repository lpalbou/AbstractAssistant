import { jsx as _jsx } from "react/jsx-runtime";
import { useEffect, useRef, useState } from "react";
import { AvatarRenderer, avatarPaletteFromCss } from "./avatar_renderer.js";
/** Presentation only; a host can wrap this in its own accessible activation control. */
export function ActivityAvatar({ design = "halo", pose = "ready", level = 0, bands, size = 128, animated = true, active = true, followCursor = false, palette, className, label, onError }) {
    const canvas = useRef(null), latest = useRef({ design, pose, level, bands });
    latest.current = { design, pose, level, bands };
    const [error, setError] = useState(false), errorHandler = useRef(onError);
    errorHandler.current = onError;
    // Equal palette contents must not recreate a renderer on parent/audio updates.
    const paletteKey = palette ? JSON.stringify(palette) : "theme";
    useEffect(() => {
        const el = canvas.current;
        if (!el || !active)
            return;
        let disposed = false, renderer, visible = true, lost = false;
        let timer, idle;
        let gaze = [0, 0], tracking = false;
        const motion = matchMedia("(prefers-reduced-motion: reduce)");
        let elapsed = 0, previous;
        const clear = () => {
            if (timer !== undefined) {
                clearTimeout(timer);
                timer = undefined;
            }
        };
        const resetGaze = () => {
            if (idle !== undefined) {
                clearTimeout(idle);
                idle = undefined;
            }
            tracking = false;
            gaze = [0, 0];
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
            if (!animated || motion.matches || !visible || lost || document.hidden || s.pose !== "ready")
                resetGaze();
            if (disposed || !renderer || !visible || lost || document.hidden) {
                previous = undefined;
                return;
            }
            try {
                const moving = animated && !motion.matches, now = performance.now();
                if (moving && previous !== undefined)
                    elapsed = (elapsed + Math.min(1, (now - previous) / 1000)) % 86400;
                previous = moving ? now : undefined;
                renderer.renderFrame({ schema_version: 1, style: s.design, state: s.pose, level: s.level,
                    time: moving ? elapsed : 0,
                    gaze, ...(s.bands === undefined ? {} : { bands: s.bands }) });
                setError(false);
                if (animated && !motion.matches && s.pose !== "error") {
                    timer = setTimeout(draw, s.pose === "ready" && !tracking ? 500 : s.pose === "waiting" ? 167 : 84);
                }
            }
            catch (e) {
                fail(e);
            }
        };
        const move = (event) => {
            if (!renderer || !visible || lost || document.hidden || !animated || motion.matches || latest.current.pose !== "ready" || event.pointerType === "touch")
                return;
            const bounds = el.getBoundingClientRect();
            if (!bounds.width || !bounds.height)
                return;
            const clamp = (v) => Math.max(-1, Math.min(1, v));
            gaze = [clamp((event.clientX - bounds.x - bounds.width / 2) / (bounds.width / 2)), clamp((event.clientY - bounds.y - bounds.height / 2) / (bounds.height / 2))];
            const wasTracking = tracking;
            tracking = true;
            if (idle !== undefined)
                clearTimeout(idle);
            idle = setTimeout(() => { resetGaze(); draw(); }, 2000);
            // Later movements only change the sampled target, never reset the draw clock.
            if (!wasTracking)
                draw();
        };
        const observer = new IntersectionObserver(entries => { visible = entries[0]?.isIntersecting ?? false; draw(); });
        observer.observe(el);
        motion.addEventListener("change", draw);
        document.addEventListener("visibilitychange", draw);
        el.addEventListener("avatar-update", draw);
        if (followCursor)
            window.addEventListener("pointermove", move, { passive: true });
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
        const resolution = Math.min(256, Math.round(size * (devicePixelRatio || 1)));
        Promise.resolve().then(() => AvatarRenderer.create(el, { width: resolution, height: resolution, palette: palette ?? avatarPaletteFromCss(el) })).then(r => {
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
            clear();
            resetGaze();
            observer.disconnect();
            theme.disconnect();
            motion.removeEventListener("change", draw);
            document.removeEventListener("visibilitychange", draw);
            el.removeEventListener("avatar-update", draw);
            window.removeEventListener("pointermove", move);
            el.removeEventListener("contextlost", contextLost);
            el.removeEventListener("contextrestored", contextRestored);
            renderer?.dispose();
        };
    }, [size, paletteKey, animated, active, followCursor]);
    useEffect(() => { canvas.current?.dispatchEvent(new Event("avatar-update")); }, [design, pose]);
    // Audio producers cannot reset or outrun the clock; reduced motion allows explicit data updates.
    useEffect(() => {
        if (!animated || matchMedia("(prefers-reduced-motion: reduce)").matches)
            canvas.current?.dispatchEvent(new Event("avatar-update"));
    }, [level, bands, animated]);
    return _jsx("canvas", { ref: canvas, className: className, style: { width: size, height: size, visibility: active ? "visible" : "hidden" }, "aria-hidden": !active, role: "img", "aria-label": error ? "Avatar unavailable" : label ?? `${design} · ${pose}` });
}
