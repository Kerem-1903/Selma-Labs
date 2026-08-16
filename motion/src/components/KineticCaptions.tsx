import React from "react";
import {interpolate, spring, useCurrentFrame, useVideoConfig} from "remotion";
import type {CaptionCueSpec} from "../types";

export const KineticCaptions: React.FC<{
  cues: CaptionCueSpec[];
  foreground: string;
  active: string;
}> = ({cues, foreground, active}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const cue = cues.find((item) => frame >= item.startFrame && frame < item.endFrame);
  if (!cue) return null;
  const localFrame = frame - cue.startFrame;
  const entrance = spring({frame: localFrame, fps, config: {damping: 18, stiffness: 190}});
  const exitOpacity = interpolate(frame, [cue.endFrame - 5, cue.endFrame], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        position: "absolute",
        left: 110,
        right: 110,
        bottom: 330,
        display: "flex",
        justifyContent: "center",
        opacity: exitOpacity,
        translate: `0 ${interpolate(entrance, [0, 1], [20, 0])}px`,
      }}
    >
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          columnGap: 22,
          rowGap: 8,
          padding: "18px 28px 24px",
          borderRadius: 28,
          background: "rgba(2, 6, 15, 0.66)",
          boxShadow: "0 14px 50px rgba(0,0,0,0.36)",
        }}
      >
        {cue.words.map((word, index) => {
          const isActive = frame >= word.startFrame && frame < word.endFrame;
          const wordSpring = spring({
            frame: Math.max(0, frame - word.startFrame),
            fps,
            config: {damping: 14, stiffness: 240, mass: 0.55},
          });
          return (
            <span
              key={`${word.text}-${index}`}
              style={{
                color: isActive ? active : foreground,
                fontFamily: "Arial Black, Arial, sans-serif",
                fontSize: 72,
                lineHeight: 1.08,
                letterSpacing: -2,
                textShadow: "0 4px 0 #090b12, 0 0 18px rgba(0,0,0,0.9)",
                // Vertical-only emphasis preserves the exact horizontal word
                // spacing while still giving the active word a kinetic pop.
                scale: isActive
                  ? `1 ${interpolate(wordSpring, [0, 1], [1, 1.06])}`
                  : "1 1",
                transformOrigin: "center bottom",
              }}
            >
              {word.text}
            </span>
          );
        })}
      </div>
    </div>
  );
};
