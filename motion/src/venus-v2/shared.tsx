import React from "react";
import {AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame} from "remotion";

export const colors = {
  gold: "#FFB547",
  yellow: "#FFE45E",
  cream: "#FFF4DA",
  ink: "#07090E",
  cyan: "#77E5FF",
};

export const FullBleedImage: React.FC<{
  file: string;
  darken?: number;
  startScale?: number;
  endScale?: number;
  objectPosition?: string;
}> = ({file, darken = 0.35, startScale = 1.05, endScale = 1.14, objectPosition = "center"}) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{overflow: "hidden", background: colors.ink}}>
      <Img
        src={staticFile(`venus-v2/${file}`)}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          objectPosition,
          scale: interpolate(frame, [0, 210], [startScale, endScale], {extrapolateRight: "clamp"}),
          translate: `${interpolate(frame, [0, 210], [-10, 16], {extrapolateRight: "clamp"})}px 0`,
        }}
      />
      <AbsoluteFill style={{background: `linear-gradient(180deg, rgba(2,4,8,${darken * 0.65}), rgba(2,4,8,${darken}) 55%, rgba(2,4,8,${Math.min(0.88, darken + 0.24)}) 100%)`}} />
    </AbsoluteFill>
  );
};

export const InfoPill: React.FC<{text: string; top: number; width?: number}> = ({text, top, width}) => {
  const frame = useCurrentFrame();
  return (
    <div style={{position: "absolute", left: 90, top, display: "flex", alignItems: "center", opacity: interpolate(frame, [2, 10], [0, 1], {extrapolateRight: "clamp"}), translate: `${interpolate(frame, [0, 12], [-35, 0], {extrapolateRight: "clamp"})}px 0`}}>
      <div style={{width: 18, height: 18, borderRadius: "50%", background: colors.cyan, boxShadow: `0 0 18px ${colors.cyan}`, marginRight: 18}} />
      <div style={{width, background: "rgba(3,7,13,.88)", border: `2px solid rgba(119,229,255,.58)`, borderRadius: 22, padding: "20px 28px", color: "white", font: "900 42px Arial Black, Arial", letterSpacing: -1, boxShadow: "0 12px 30px rgba(0,0,0,.34)"}}>{text}</div>
    </div>
  );
};

export const SpaceBackground: React.FC<{children?: React.ReactNode}> = ({children}) => (
  <AbsoluteFill
    style={{
      background:
        "radial-gradient(circle at 70% 20%, rgba(96,50,20,.32), transparent 35%), radial-gradient(circle at 20% 75%, rgba(31,78,105,.22), transparent 40%), #03050A",
      overflow: "hidden",
    }}
  >
    <AbsoluteFill
      style={{
        opacity: 0.6,
        backgroundImage:
          "radial-gradient(circle, rgba(255,255,255,.8) 0 1px, transparent 1.5px), radial-gradient(circle, rgba(119,229,255,.55) 0 1px, transparent 1.5px)",
        backgroundPosition: "0 0, 47px 71px",
        backgroundSize: "83px 83px, 127px 127px",
      }}
    />
    {children}
  </AbsoluteFill>
);

export const NasaPlanet: React.FC<{
  source?: "cloud" | "north" | "global";
  size: number;
  top: number;
  left: number;
  rotate?: number;
}> = ({source = "cloud", size, top, left, rotate = 0}) => {
  const frame = useCurrentFrame();
  const file =
    source === "cloud"
      ? "venus-v2/mariner_venus_single.jpg"
      : source === "north"
        ? "venus-v2/magellan_north.jpg"
        : "venus-v2/magellan_global.jpg";
  return (
    <div
      style={{
        position: "absolute",
        width: size,
        height: size,
        left,
        top,
        borderRadius: "50%",
        overflow: "hidden",
        rotate: `${rotate + frame * 0.035}deg`,
        filter: "drop-shadow(0 0 54px rgba(255,164,65,.35))",
      }}
    >
      <Img
        src={staticFile(file)}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          objectPosition: "center",
          scale: source === "cloud" ? 1.16 : 1.03,
        }}
      />
    </div>
  );
};

export const Eyebrow: React.FC<{children: React.ReactNode}> = ({children}) => (
  <div
    style={{
      color: colors.gold,
      fontFamily: "Arial, sans-serif",
      fontWeight: 800,
      fontSize: 34,
      letterSpacing: 7,
      textTransform: "uppercase",
    }}
  >
    {children}
  </div>
);

export const BigNumber: React.FC<{number: string; label: string; accent?: string}> = ({
  number,
  label,
  accent = colors.gold,
}) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        opacity: interpolate(frame, [0, 8], [0, 1], {extrapolateRight: "clamp"}),
        scale: interpolate(frame, [0, 10], [0.84, 1], {extrapolateRight: "clamp"}),
        textAlign: "center",
      }}
    >
      <div style={{fontFamily: "Arial Black, Arial", fontSize: 210, lineHeight: 0.9, color: accent}}>{number}</div>
      <div style={{fontFamily: "Arial, sans-serif", fontSize: 44, fontWeight: 900, color: colors.cream}}>{label}</div>
    </div>
  );
};
