import React from "react";
import {interpolate, spring, useCurrentFrame, useVideoConfig} from "remotion";
import {StrangeThingsMark} from "./StrangeThingsMark";

export const BrandSting: React.FC<{
  text: string;
  science: string;
  active: string;
  durationFrames: number;
}> = ({text, science, active, durationFrames}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const settle = spring({frame, fps, config: {damping: 18, stiffness: 150}});
  const fadeOutStart = Math.max(8, durationFrames - 8);
  const opacity = interpolate(frame, [0, 4, fadeOutStart, durationFrames - 1], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        position: "absolute",
        top: 128,
        left: 0,
        right: 0,
        display: "flex",
        justifyContent: "center",
        opacity,
        translate: `0 ${interpolate(settle, [0, 1], [18, 0])}px`,
      }}
    >
      <div
        style={{
          position: "relative",
          overflow: "hidden",
          display: "flex",
          alignItems: "center",
          gap: 16,
          padding: "10px 24px 10px 12px",
          borderRadius: 999,
          background: "rgba(3, 8, 18, 0.76)",
          border: "1px solid rgba(255,255,255,0.20)",
          color: "white",
          fontFamily: "Arial, sans-serif",
          fontWeight: 800,
          fontSize: 32,
          letterSpacing: 6,
          textTransform: "uppercase",
        }}
      >
        <StrangeThingsMark size={66} science={science} active={active} />
        <div>
          <div>{text}</div>
          <div style={{fontFamily: "Arial, sans-serif", fontSize: 12, letterSpacing: 4, color: `${science}`, marginTop: 3}}>
            ODD SCIENCE • FUTURE
          </div>
        </div>
        <div
          style={{
            position: "absolute",
            top: 0,
            bottom: 0,
            width: 90,
            left: interpolate(frame, [2, Math.max(12, durationFrames - 5)], [-120, 620]),
            transform: "skewX(-20deg)",
            background: `linear-gradient(90deg, transparent, ${science}99, transparent)`,
          }}
        />
      </div>
    </div>
  );
};
