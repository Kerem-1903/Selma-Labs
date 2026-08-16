import React from "react";
import type {Caption} from "@remotion/captions";
import {Easing, Interactive, interpolate, spring, useCurrentFrame, useVideoConfig} from "remotion";

export const PhantomCaptions: React.FC<{captions: Caption[]}> = ({captions}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const nowMs = (frame / fps) * 1000;
  const caption = captions.find((item) => nowMs >= item.startMs && nowMs < item.endMs);
  if (!caption) return null;
  const localFrame = frame - (caption.startMs / 1000) * fps;
  const entrance = spring({frame: localFrame, fps, config: {damping: 16, stiffness: 220, mass: 0.65}});
  const words = caption.text.split(" ");

  return (
    <Interactive.Div
      name="Kinetik altyazı"
      style={{
        position: "absolute",
        left: 76,
        right: 76,
        bottom: 300,
        display: "flex",
        justifyContent: "center",
        opacity: interpolate(nowMs, [caption.startMs, caption.startMs + 90, caption.endMs - 120, caption.endMs], [0, 1, 1, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
          easing: Easing.bezier(0.16, 1, 0.3, 1),
        }),
        translate: `0 ${interpolate(entrance, [0, 1], [24, 0])}px`,
      }}
    >
      <div style={{width: "100%", maxWidth: 930, boxSizing: "border-box", padding: "22px 30px 26px", borderRadius: 30, background: "rgba(4,8,18,.82)", boxShadow: "0 20px 60px rgba(0,0,0,.55)", textAlign: "center"}}>
        {words.map((word, index) => (
          <span key={`${word}-${index}`} style={{display: "inline-block", color: index === words.length - 1 ? "#FFD52A" : "#F7FAFF", fontFamily: "Arial Black, Arial, sans-serif", fontSize: 58, lineHeight: 1.08, letterSpacing: -2, marginRight: 14, textShadow: "0 5px 0 #050914"}}>
            {word}
          </span>
        ))}
      </div>
    </Interactive.Div>
  );
};
