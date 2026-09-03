export type AnimeAnimaticClip = {
  shotId: string;
  startFrame: number;
  durationFrames: number;
  imageSrc: string;
  dialogue: string;
  audioSrc: string;
};

export type AnimeAnimaticProps = {
  title: string;
  fps: number;
  durationInFrames: number;
  clips: AnimeAnimaticClip[];
};
