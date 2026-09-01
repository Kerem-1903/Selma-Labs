import React from "react";
import {AbsoluteFill, interpolate, useCurrentFrame} from "remotion";

const DROPS = Array.from({length: 72}, (_, index) => ({
  left: (index * 37 + 11) % 100,
  length: 26 + ((index * 17) % 48),
  opacity: 0.12 + ((index * 13) % 24) / 100,
  speed: 17 + ((index * 7) % 19),
  offset: (index * 29) % 180,
}));

export const RainLayer: React.FC<{intensity?: number}> = ({intensity = 1}) => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill style={{overflow: "hidden", pointerEvents: "none"}}>
      {DROPS.map((drop, index) => {
        const travel = (frame * drop.speed + drop.offset) % 1250;
        return (
          <div
            key={index}
            style={{
              position: "absolute",
              left: `${drop.left}%`,
              top: -120,
              width: 2,
              height: drop.length,
              borderRadius: 999,
              background:
                "linear-gradient(180deg, transparent, rgba(185,220,255,0.9))",
              opacity: drop.opacity * intensity,
              translate: `${-travel * 0.08}px ${travel}px`,
              rotate: "8deg",
              filter: "blur(0.45px)",
            }}
          />
        );
      })}
      <AbsoluteFill
        style={{
          opacity: interpolate(frame % 90, [0, 8, 45, 90], [0.08, 0.2, 0.08, 0.08]),
          background:
            "radial-gradient(circle at 52% 22%, rgba(120,180,220,0.08), transparent 44%)",
        }}
      />
    </AbsoluteFill>
  );
};
