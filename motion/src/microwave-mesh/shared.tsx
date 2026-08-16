import React from "react";
import {AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame} from "remotion";

export const palette = {
  amber: "#FFB23E",
  yellow: "#FFE45E",
  cyan: "#6EEBFF",
  white: "#FFF8E9",
  ink: "#05070B",
  red: "#FF5C57",
};

export const FullImage: React.FC<{
  file: string;
  darken?: number;
  startScale?: number;
  endScale?: number;
  objectPosition?: string;
}> = ({file, darken = 0.35, startScale = 1.04, endScale = 1.14, objectPosition = "center"}) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{overflow: "hidden", background: palette.ink}}>
      <Img
        src={staticFile(`microwave-mesh/${file}`)}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          objectPosition,
          scale: interpolate(frame, [0, 210], [startScale, endScale], {
            extrapolateRight: "clamp",
          }),
          translate: `${interpolate(frame, [0, 210], [-8, 14], {extrapolateRight: "clamp"})}px 0`,
        }}
      />
      <AbsoluteFill
        style={{
          background: `linear-gradient(180deg, rgba(3,5,8,${darken * 0.65}), rgba(3,5,8,${darken}) 55%, rgba(3,5,8,${Math.min(0.9, darken + 0.3)}) 100%)`,
        }}
      />
    </AbsoluteFill>
  );
};

export const InfoPill: React.FC<{
  children: React.ReactNode;
  top: number;
  left?: number;
  color?: string;
}> = ({children, top, left = 88, color = palette.cyan}) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        position: "absolute",
        top,
        left,
        display: "flex",
        alignItems: "center",
        opacity: interpolate(frame, [1, 10], [0, 1], {extrapolateRight: "clamp"}),
        translate: `${interpolate(frame, [0, 12], [-35, 0], {extrapolateRight: "clamp"})}px 0`,
      }}
    >
      <div style={{width: 17, height: 17, borderRadius: 50, background: color, boxShadow: `0 0 20px ${color}`, marginRight: 18}} />
      <div
        style={{
          padding: "18px 28px",
          borderRadius: 22,
          border: `2px solid ${color}99`,
          background: "rgba(2,5,9,.88)",
          boxShadow: "0 14px 34px rgba(0,0,0,.42)",
          color: palette.white,
          font: "900 40px Arial Black, Arial",
          letterSpacing: -0.8,
        }}
      >
        {children}
      </div>
    </div>
  );
};

export const NumberCard: React.FC<{
  number: string;
  label: string;
  color?: string;
  top: number;
}> = ({number, label, color = palette.yellow, top}) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        position: "absolute",
        left: 90,
        right: 90,
        top,
        padding: "48px 30px 42px",
        borderRadius: 44,
        background: "rgba(3,6,11,.86)",
        border: `3px solid ${color}`,
        textAlign: "center",
        boxShadow: `0 0 38px ${color}26, 0 16px 45px rgba(0,0,0,.5)`,
        opacity: interpolate(frame, [4, 14], [0, 1], {extrapolateRight: "clamp"}),
        scale: interpolate(frame, [2, 15], [0.82, 1], {extrapolateRight: "clamp"}),
      }}
    >
      <div style={{font: "900 188px/.88 Arial Black, Arial", color}}>{number}</div>
      <div style={{font: "900 42px Arial", color: palette.white, letterSpacing: 3}}>{label}</div>
    </div>
  );
};

export const MeshPattern: React.FC<{opacity?: number; hole?: number}> = ({opacity = 0.7, hole = 20}) => (
  <AbsoluteFill
    style={{
      opacity,
      backgroundImage: `radial-gradient(circle, transparent 0 ${hole}px, rgba(3,5,8,.96) ${hole + 2}px)`,
      backgroundSize: `${hole * 2.7}px ${hole * 2.7}px`,
    }}
  />
);
