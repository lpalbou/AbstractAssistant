/** Presentation budgets; geometry and activity semantics belong to AbstractAvatar. */
export type AvatarQuality = "economy" | "balanced" | "high";
export declare function avatarResolution(size: number, pixelRatio: number, quality: AvatarQuality): number;
export declare function avatarFrameInterval(quality: AvatarQuality, pose: string, tracking: boolean): number;
//# sourceMappingURL=avatar_quality.d.ts.map