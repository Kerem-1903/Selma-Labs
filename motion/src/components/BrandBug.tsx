import React from "react";
import {interpolate, useCurrentFrame} from "remotion";
import {StrangeThingsMark} from "./StrangeThingsMark";

export const BrandBug: React.FC<{science: string; active: string}> = ({science, active}) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        position: "absolute",
        left: 54,
        top: 76,
        opacity: interpolate(frame, [0, 8], [0, 0.74], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        }),
        filter: "drop-shadow(0 8px 18px rgba(0,0,0,.48))",
      }}
    >
      <StrangeThingsMark size={66} science={science} active={active} />
    </div>
  );
};
