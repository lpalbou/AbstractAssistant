import React from "react";
import { type AvatarPalette, type AvatarPose } from "./avatar_renderer.js";
import { type AvatarQuality } from "./avatar_quality.js";
export type { AvatarQuality } from "./avatar_quality.js";
export interface ActivityAvatarProps {
    design?: string;
    pose?: AvatarPose;
    level?: number;
    bands?: readonly number[];
    size?: number;
    quality?: AvatarQuality;
    animated?: boolean;
    active?: boolean;
    followCursor?: boolean;
    palette?: AvatarPalette;
    className?: string;
    label?: string;
    onError?: (error: Error) => void;
}
/** Presentation only; a host can wrap this in its own accessible activation control. */
export declare function ActivityAvatar({ design, pose, level, bands, size, quality, animated, active, followCursor, palette, className, label, onError }: ActivityAvatarProps): React.ReactElement;
//# sourceMappingURL=activity_avatar.d.ts.map