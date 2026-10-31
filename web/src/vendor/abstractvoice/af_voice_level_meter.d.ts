import React from "react";
/** Anything that sends a live level 0..1: the value `useGatewayVoice` returns. */
export type VoiceLevelSource = {
    subscribe_level?: (fn: (level: number) => void) => () => void;
    subscribe_playback_level?: (fn: (level: number) => void) => () => void;
};
/** The live level of `source` (0 without one). Re-renders only the component that calls it. */
export declare function useVoiceLevel(source?: VoiceLevelSource | null, channel?: "microphone" | "playback"): number;
export type AfVoiceLevelMeterProps = {
    /** The live level's source (`voice` from `useGatewayVoice`). */
    source?: VoiceLevelSource | null;
    /** Microphone by default; playback observes reply output after volume and mute. */
    channel?: "microphone" | "playback";
    /** A level the host already has (0..1); wins over `source`. */
    level?: number;
    /** Accessible name (default "Microphone level"). */
    label?: string;
    /** Where the level comes from, for styling and checks ("live", "test"). */
    origin?: string;
    /** A span inside a line of controls instead of a block. */
    inline?: boolean;
    className?: string;
};
export declare function AfVoiceLevelMeter(p: AfVoiceLevelMeterProps): React.ReactElement;
//# sourceMappingURL=af_voice_level_meter.d.ts.map