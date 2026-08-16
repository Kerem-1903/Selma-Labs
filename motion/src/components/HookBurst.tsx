import React from "react";
import {interpolate, spring, useCurrentFrame, useVideoConfig} from "remotion";

export const HookBurst: React.FC<{text: string; active: string}> = ({text, active}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const settle = spring({frame, fps, config: {damping: 13, stiffness: 230, mass: 0.7}});
  const opacity = interpolate(frame, [0, 3, 23, 29], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const scale = interpolate(settle, [0, 1], [1.32, 1]);
  const compactText = text.trim();
  const fontSize = compactText.length > 18 ? 82 : compactText.length > 13 ? 96 : 116;

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        opacity,
        transform: `scale(${scale})`,
        filter: `blur(${interpolate(frame, [0, 5], [8, 0], {extrapolateRight: "clamp"})}px)`,
      }}
    >
      <div
        style={{
          width: "min(840px, calc(100% - 160px))",
          boxSizing: "border-box",
          padding: "26px 42px 30px",
          borderRadius: 34,
          background: "rgba(4, 8, 20, 0.82)",
          border: `3px solid ${active}`,
          boxShadow: `0 0 70px ${active}66`,
          color: "white",
          fontFamily: "Arial Black, Arial, sans-serif",
          fontSize,
          lineHeight: 0.98,
          letterSpacing: fontSize >= 110 ? -5 : -3,
          textAlign: "center",
          textTransform: "uppercase",
        }}
      >
        {compactText}
      </div>
    </div>
  );
};
