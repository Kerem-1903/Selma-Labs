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
import type {AnimeAnimaticClip, AnimeAnimaticProps} from "./types";

const Clip: React.FC<{clip: AnimeAnimaticClip}> = ({clip}) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{backgroundColor: "#111217", overflow: "hidden"}}>
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
      <div style={{position: "absolute", top: 38, left: 48, color: "#D89A43",
        fontFamily: "Arial, sans-serif", fontSize: 25, letterSpacing: 2}}>
        {clip.shotId}
      </div>
      {clip.dialogue ? <div style={{position: "absolute", bottom: 54, left: 180,
        right: 180, padding: "20px 28px", color: "#D8D5CF", background: "#111217DD",
        textAlign: "center", fontFamily: "Arial, sans-serif", fontSize: 38}}>
        {clip.dialogue}
      </div> : null}
      {clip.audioSrc ? <Audio src={staticFile(clip.audioSrc)} /> : null}
    </AbsoluteFill>
  );
};

export const AnimeAnimatic: React.FC<AnimeAnimaticProps> = ({clips}) => (
  <AbsoluteFill style={{backgroundColor: "#111217"}}>
    {clips.map((clip) => (
      <Sequence key={clip.shotId} from={clip.startFrame}
        durationInFrames={clip.durationFrames} premountFor={12}>
        <Clip clip={clip} />
      </Sequence>
    ))}
  </AbsoluteFill>
);
