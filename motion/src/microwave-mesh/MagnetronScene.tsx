import React from "react";
import {interpolate, useCurrentFrame} from "remotion";
import {FullImage, InfoPill, palette} from "./shared";

export const MagnetronScene: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <div style={{position: "absolute", inset: 0, overflow: "hidden"}}>
      <FullImage file="inside-waves.png" darken={0.42} startScale={1.06} endScale={1.17} objectPosition="center" />
      <InfoPill top={145} color={palette.amber}>DALGAYI ÜRETEN PARÇA</InfoPill>
      <div style={{position: "absolute", top: 395, left: 0, right: 0, textAlign: "center"}}>
        <div style={{font: "900 61px Arial Black, Arial", color: "white", letterSpacing: 5}}>MAGNETRON</div>
      </div>
      <div style={{position: "absolute", left: 95, right: 95, top: 675, padding: "55px 25px 45px", borderRadius: 48, border: `3px solid ${palette.amber}`, background: "rgba(3,5,8,.82)", textAlign: "center", boxShadow: "0 18px 48px rgba(0,0,0,.5)", opacity: interpolate(frame, [12, 24], [0, 1], {extrapolateRight: "clamp"}), scale: interpolate(frame, [9, 25], [0.82, 1], {extrapolateRight: "clamp"})}}>
        <div style={{font: "900 164px/.9 Arial Black, Arial", color: palette.yellow}}>2,45</div>
        <div style={{font: "900 55px Arial", color: "white", letterSpacing: 5}}>GIGAHERTZ</div>
      </div>
    </div>
  );
};
