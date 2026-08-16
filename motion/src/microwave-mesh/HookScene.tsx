import React from "react";
import {interpolate, useCurrentFrame} from "remotion";
import {FullImage, palette} from "./shared";

export const HookScene: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <div style={{position: "absolute", inset: 0, overflow: "hidden"}}>
      <FullImage file="door-mesh.png" darken={0.38} startScale={1.06} endScale={1.22} objectPosition="50% center" />
      <div
        style={{
          position: "absolute",
          top: 205,
          left: 75,
          right: 75,
          padding: "44px 30px 48px",
          borderRadius: 42,
          background: "rgba(2,5,9,.84)",
          border: `3px solid ${palette.yellow}`,
          boxShadow: "0 20px 50px rgba(0,0,0,.48)",
          textAlign: "center",
          opacity: interpolate(frame, [0, 7], [0, 1], {extrapolateRight: "clamp"}),
          scale: interpolate(frame, [0, 10], [0.82, 1], {extrapolateRight: "clamp"}),
        }}
      >
        <div style={{font: "900 70px/.95 Arial Black, Arial", color: "white"}}>DALGALAR NEDEN</div>
        <div style={{font: "900 103px/.94 Arial Black, Arial", color: palette.yellow, marginTop: 12}}>ÇIKMIYOR?</div>
      </div>
      <div style={{position: "absolute", top: 740, left: 115, right: 115, height: 380, border: `7px solid ${palette.cyan}`, borderRadius: "50%", boxShadow: `0 0 34px ${palette.cyan}66`, opacity: 0.86 + Math.sin(frame / 5) * 0.08}} />
      <div style={{position: "absolute", left: 72, top: 1395, background: "rgba(3,5,8,.84)", borderRadius: 18, padding: "14px 22px", color: "white", font: "800 25px Arial", letterSpacing: 3}}>KAPAĞIN İÇİNDEKİ KALKAN</div>
    </div>
  );
};
