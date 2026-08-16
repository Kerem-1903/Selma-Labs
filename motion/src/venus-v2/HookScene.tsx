import React from "react";
import {AbsoluteFill, interpolate, useCurrentFrame} from "remotion";
import {colors, FullBleedImage} from "./shared";

export const HookScene: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{background: "#03050A"}}>
      <FullBleedImage file="mariner_venus_single.jpg" darken={0.3} startScale={1.25} endScale={1.48} objectPosition="50% 40%" />
      <AbsoluteFill style={{background: "radial-gradient(circle at 50% 37%, transparent 0 25%, rgba(1,3,7,.18) 55%, rgba(1,3,7,.8) 100%)"}} />
      <div
        style={{
          position: "absolute",
          left: 74,
          right: 74,
          top: 650,
          fontFamily: "Arial Black, Arial, sans-serif",
          fontWeight: 900,
          color: "white",
          fontSize: 96,
          lineHeight: 0.94,
          letterSpacing: -5,
          textAlign: "center",
          textShadow: "0 8px 32px rgba(0,0,0,.95)",
          background: "rgba(2,5,10,.82)",
          border: `3px solid ${colors.yellow}`,
          borderRadius: 40,
          padding: "48px 25px 42px",
          opacity: interpolate(frame, [2, 10], [0, 1], {extrapolateRight: "clamp"}),
          translate: `0 ${interpolate(frame, [0, 12], [45, 0], {extrapolateRight: "clamp"})}px`,
        }}
      >
        BİR GÜNÜ BİTMEDEN
        <div style={{color: colors.yellow, fontSize: 130, marginTop: 12}}>YILI BİTİYOR</div>
      </div>
      <div style={{position: "absolute", top: 1220, left: 90, color: "white", font: "900 35px Arial", letterSpacing: 5, background: "rgba(2,5,10,.72)", borderRadius: 20, padding: "16px 24px"}}>
        NASA / MARINER 10
      </div>
    </AbsoluteFill>
  );
};
