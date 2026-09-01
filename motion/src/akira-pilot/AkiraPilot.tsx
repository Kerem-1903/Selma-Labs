import React from "react";
import {AbsoluteFill, interpolate, Sequence, useCurrentFrame} from "remotion";
import {CloseupScene} from "./scenes/CloseupScene";
import {TurnScene} from "./scenes/TurnScene";
import {WalkScene} from "./scenes/WalkScene";

export const AkiraPilot: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill style={{backgroundColor: "#020409"}}>
      <Sequence durationInFrames={114} name="Approach">
        <WalkScene />
      </Sequence>
      <Sequence from={96} durationInFrames={114} name="Turn">
        <TurnScene />
      </Sequence>
      <Sequence from={192} durationInFrames={108} name="Resolve">
        <CloseupScene />
      </Sequence>
      <AbsoluteFill
        style={{
          backgroundColor: "#000",
          opacity: interpolate(frame, [0, 12, 282, 299], [1, 0, 0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
          pointerEvents: "none",
        }}
      />
      <AbsoluteFill
        style={{
          opacity: 0.05,
          backgroundImage:
            "repeating-linear-gradient(0deg, transparent 0px, transparent 3px, rgba(255,255,255,0.2) 4px)",
          mixBlendMode: "soft-light",
          pointerEvents: "none",
        }}
      />
    </AbsoluteFill>
  );
};
