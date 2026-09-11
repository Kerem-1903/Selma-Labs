import React from "react";
import {Audio} from "@remotion/media";
import {
  AbsoluteFill,
  CanvasImage,
  Easing,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";
import type {AnimeAnimaticAudioCue, AnimeAnimaticClip, AnimeAnimaticProps} from "./types";

const Clip: React.FC<{clip: AnimeAnimaticClip}> = ({clip}) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{backgroundColor: "#111217", overflow: "hidden"}}>
      {clip.imageSrc.startsWith("placeholder://") ? (
        <div style={{
          width: "100%", height: "100%", display: "flex", alignItems: "center",
          justifyContent: "center", background: "#3b2028", color: "#ffb4a8",
          fontFamily: "Arial, sans-serif", fontSize: 48, letterSpacing: 4,
        }}>
          PLACEHOLDER
        </div>
      ) : (
      <CanvasImage
        src={staticFile(clip.imageSrc)}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "contain",
          scale: interpolate(frame, [0, clip.durationFrames], [1, 1.035], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.bezier(0.33, 0, 0.67, 1),
          }),
        }}
      />
      )}
      <div style={{position: "absolute", top: 38, left: 48, color: "#D89A43",
        fontFamily: "Arial, sans-serif", fontSize: 25, letterSpacing: 2}}>
        {clip.shotId}
      </div>
      {clip.dialogue ? <div style={{position: "absolute", bottom: 54, left: 180,
        right: 180, padding: "20px 28px", color: "#D8D5CF", background: "#111217DD",
        textAlign: "center", fontFamily: "Arial, sans-serif", fontSize: 38}}>
        {clip.dialogue}
      </div> : null}
      {clip.warning ? <div style={{position: "absolute", top: 86, left: 48,
        right: 48, padding: "12px 18px", color: "#ffd1c9", background: "#5b1e2aE6",
        fontFamily: "Arial, sans-serif", fontSize: 24, textAlign: "center",
        letterSpacing: 1}}>{clip.warning}</div> : null}
      {clip.audioSrc ? <Audio src={staticFile(clip.audioSrc)} /> : null}
    </AbsoluteFill>
  );
};

const AudioCue: React.FC<{cue: AnimeAnimaticAudioCue}> = ({cue}) => (
  <Sequence from={cue.start_frame} durationInFrames={cue.end_frame - cue.start_frame}>
    <Audio volume={(frame) => {
      const local = frame + (cue.trim_before_frames ?? 0);
      const fadeIn = cue.fade_in_frames > 0 ? Math.min(1, local / cue.fade_in_frames) : 1;
      const remaining = (cue.source_duration_frames ?? cue.end_frame - cue.start_frame) - local;
      const fadeOut = cue.fade_out_frames > 0 ? Math.min(1, remaining / cue.fade_out_frames) : 1;
      const duck = Math.pow(10, cue.ducking_db / 20);
      return Math.pow(10, cue.gain_db / 20) * fadeIn * fadeOut * duck;
    }} src={staticFile(cue.storage_key)} trimBefore={cue.trim_before_frames ?? 0} />
  </Sequence>
);

export const AnimeAnimatic: React.FC<AnimeAnimaticProps> = ({clips, audioCues}) => (
  <AbsoluteFill style={{backgroundColor: "#111217"}}>
    {clips.map((clip) => (
      <Sequence key={clip.shotId} from={clip.startFrame}
        durationInFrames={clip.durationFrames} premountFor={12}>
        <Clip clip={clip} />
      </Sequence>
    ))}
    {audioCues.map((cue) => <AudioCue key={cue.cue_id} cue={cue} />)}
  </AbsoluteFill>
);
