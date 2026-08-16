export type TransitionKind =
  | "hard"
  | "push"
  | "match_zoom"
  | "mask_reveal"
  | "impact_flash";

export type MotionKind = "steady" | "fast-paced" | "slow-motion";

export type PatternInterruptKind =
  | "none"
  | "hook_burst"
  | "diagram"
  | "callout"
  | "scale_or_layout_change"
  | "payoff_card";

export type WordSpec = {
  text: string;
  startFrame: number;
  endFrame: number;
};

export type CaptionCueSpec = {
  startFrame: number;
  endFrame: number;
  words: WordSpec[];
};

export type SceneSpec = {
  startFrame: number;
  durationFrames: number;
  source?: string;
  sourceStartFrame?: number;
  motion: MotionKind;
  shotType: string;
  visualJob: string;
  labels: string[];
  transition: TransitionKind;
  patternInterrupt?: PatternInterruptKind;
  safeZone?: "center_subject_caption_clear";
  accentColor?: string;
  diagramKind?: "self_healing";
};

export type StrangeThingsProps = {
  fps: number;
  durationInFrames: number;
  title: string;
  hookText: string;
  brandSignature: string;
  brandStartFrame?: number;
  brandDurationFrames?: number;
  ctaText?: string;
  ctaStartFrame?: number;
  scenes: SceneSpec[];
  captions: CaptionCueSpec[];
  palette?: {
    background: string;
    foreground: string;
    active: string;
    science: string;
    danger: string;
  };
};
