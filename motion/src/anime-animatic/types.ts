export type AnimeAnimaticClip = {
  shotId: string;
  startFrame: number;
  durationFrames: number;
  imageSrc: string;
  dialogue: string;
  audioSrc: string;
  warning?: string;
};

export type AnimeAnimaticAudioCue = {
  cue_id: string;
  kind: "MUSIC" | "SFX";
  storage_key: string;
  start_frame: number;
  end_frame: number;
  gain_db: number;
  fade_in_frames: number;
  fade_out_frames: number;
  ducking_db: number;
  trim_before_frames?: number;
  source_duration_frames?: number;
};

export type AnimeAnimaticProps = {
  title: string;
  fps: number;
  durationInFrames: number;
  clips: AnimeAnimaticClip[];
  audioCues: AnimeAnimaticAudioCue[];
};
