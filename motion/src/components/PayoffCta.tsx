import React from "react";
import {interpolate, spring, useCurrentFrame, useVideoConfig} from "remotion";
import {StrangeThingsMark} from "./StrangeThingsMark";

export const PayoffCta: React.FC<{
  text: string;
  active: string;
  science: string;
  durationFrames: number;
}> = ({text, active, science, durationFrames}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const settle = spring({frame, fps, config: {damping: 17, stiffness: 175}});

  return (
    <div
      style={{
        position: "absolute",
        top: 500,
        left: 90,
        right: 90,
        display: "flex",
        justifyContent: "center",
        opacity: interpolate(
          frame,
          [0, 5, Math.max(6, durationFrames - 7), Math.max(7, durationFrames - 1)],
          [0, 1, 1, 0],
          {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          },
        ),
        translate: `0 ${interpolate(settle, [0, 1], [24, 0])}px`,
      }}
    >
      <div
        style={{
          maxWidth: 860,
          display: "flex",
          alignItems: "center",
          gap: 22,
          padding: "18px 28px 20px 18px",
          borderRadius: 28,
          background: "rgba(2, 6, 15, 0.82)",
          border: `2px solid ${active}`,
          boxShadow: `0 12px 44px rgba(0,0,0,.42), 0 0 30px ${active}33`,
          color: "white",
          fontFamily: "Arial Black, Arial, sans-serif",
          fontSize: 42,
          lineHeight: 1.02,
          letterSpacing: -1.5,
          textAlign: "center",
          textTransform: "uppercase",
          whiteSpace: "nowrap",
        }}
      >
        <StrangeThingsMark size={78} science={science} active={active} />
        <div>
          <div style={{fontFamily: "Arial, sans-serif", fontSize: 13, letterSpacing: 4, color: science, marginBottom: 7}}>
            STRANGE THINGS
          </div>
          {text}
        </div>
      </div>
    </div>
  );
};
