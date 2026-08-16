import React from "react";
import {AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame} from "remotion";

export const colors = {
  red: "#F13B3B",
  blue: "#2E7BFF",
  yellow: "#FFD94A",
  white: "#FFF9EE",
  black: "#05070C",
};

export const SuitImage: React.FC<{
  file: string;
  position?: string;
  startScale?: number;
  endScale?: number;
  darken?: number;
  yOffset?: number;
}> = ({file, position = "center", startScale = 1.06, endScale = 1.16, darken = 0.28, yOffset = 0}) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{overflow: "hidden", background: colors.black}}>
      <Img
        src={staticFile(`spiderman-emblems/${file}`)}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          objectPosition: position,
          scale: interpolate(frame, [0, 220], [startScale, endScale], {extrapolateRight: "clamp"}),
          translate: `${interpolate(frame, [0, 220], [-10, 14], {extrapolateRight: "clamp"})}px ${yOffset}px`,
        }}
      />
      <AbsoluteFill style={{background: `linear-gradient(180deg, rgba(3,5,10,${darken * .65}), transparent 38%, rgba(3,5,10,${Math.min(.92, darken + .42)}) 100%)`}} />
    </AbsoluteFill>
  );
};

export const ComicDots: React.FC<{opacity?: number}> = ({opacity = 0.12}) => (
  <AbsoluteFill
    style={{
      pointerEvents: "none",
      opacity,
      backgroundImage: "radial-gradient(circle, #fff 0 2px, transparent 2.6px)",
      backgroundSize: "22px 22px",
      mixBlendMode: "overlay",
    }}
  />
);

export const Sticker: React.FC<{
  children: React.ReactNode;
  top: number;
  left?: number;
  right?: number;
  color?: string;
  rotate?: number;
}> = ({children, top, left, right, color = colors.yellow, rotate = -2}) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        position: "absolute",
        top,
        left,
        right,
        padding: "17px 25px",
        borderRadius: 19,
        background: color,
        color: colors.black,
        font: "900 40px Arial Black, Arial",
        letterSpacing: 1,
        rotate: `${rotate}deg`,
        border: "4px solid #05070C",
        boxShadow: "8px 9px 0 rgba(0,0,0,.72)",
        opacity: interpolate(frame, [0, 7], [0, 1], {extrapolateRight: "clamp"}),
        scale: interpolate(frame, [0, 8], [.72, 1], {extrapolateRight: "clamp"}),
      }}
    >
      {children}
    </div>
  );
};

export const WebCorners: React.FC<{color?: string}> = ({color = "rgba(255,255,255,.35)"}) => (
  <>
    <div style={{position: "absolute", top: -100, right: -100, width: 430, height: 430, borderRadius: "50%", border: `5px solid ${color}`}} />
    <div style={{position: "absolute", top: -5, right: 45, width: 300, height: 5, background: color, rotate: "45deg"}} />
    <div style={{position: "absolute", bottom: -120, left: -120, width: 420, height: 420, borderRadius: "50%", border: `5px solid ${color}`}} />
  </>
);
