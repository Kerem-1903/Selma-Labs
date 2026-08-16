import React from "react";
import {AbsoluteFill, interpolate, useCurrentFrame} from "remotion";
import type {TransitionKind} from "../types";

export const SemanticTransition: React.FC<{kind: TransitionKind; science: string}> = ({kind, science}) => {
  const frame = useCurrentFrame();
  if (kind === "hard") return null;
  const opacity = interpolate(frame, [0, 2, 5, 8], [0, 0.72, 0.30, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const translate = interpolate(frame, [0, 8], [-700, 1000]);
  return (
    <AbsoluteFill style={{pointerEvents: "none", opacity}}>
      <div
        style={{
          position: "absolute",
          top: -200,
          bottom: -200,
          left: translate,
          width: kind === "impact_flash" ? 1300 : 420,
          transform: "skewX(-16deg)",
          background: kind === "impact_flash"
            ? "rgba(255,255,255,.96)"
            : `linear-gradient(90deg, transparent, ${science}, transparent)`,
          filter: "blur(18px)",
        }}
      />
    </AbsoluteFill>
  );
};
