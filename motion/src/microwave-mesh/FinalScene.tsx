import React from "react";
import {interpolate, useCurrentFrame} from "remotion";
import {FullImage, palette} from "./shared";

export const FinalScene: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <div style={{position: "absolute", inset: 0, overflow: "hidden"}}>
      <FullImage file="door-mesh.png" darken={0.59} startScale={1.1} endScale={1.22} />
      <div style={{position: "absolute", top: 220, left: 75, right: 75, padding: "44px 25px", background: "rgba(2,5,9,.86)", borderRadius: 44, border: `3px solid ${palette.cyan}`, textAlign: "center", opacity: interpolate(frame, [2, 12], [0, 1], {extrapolateRight: "clamp"})}}>
        <div style={{font: "900 57px Arial Black, Arial", color: "white"}}>SEN YEMEĞİ</div>
        <div style={{font: "900 112px/.95 Arial Black, Arial", color: palette.cyan}}>GÖRÜRSÜN</div>
      </div>
      <div style={{position: "absolute", top: 765, left: 75, right: 75, padding: "44px 25px", background: "rgba(2,5,9,.88)", borderRadius: 44, border: `3px solid ${palette.yellow}`, textAlign: "center", opacity: interpolate(frame, [18, 30], [0, 1], {extrapolateRight: "clamp"})}}>
        <div style={{font: "900 54px Arial Black, Arial", color: "white"}}>MİKRODALGALAR</div>
        <div style={{font: "900 97px/.95 Arial Black, Arial", color: palette.yellow}}>İÇERİDE KALIR</div>
      </div>
      <div style={{position: "absolute", top: 1320, left: 90, right: 90, textAlign: "center", color: "white", textShadow: "0 8px 24px #000", opacity: interpolate(frame, [45, 60], [0, 1], {extrapolateRight: "clamp"})}}>
        <div style={{font: "900 49px Arial Black, Arial"}}>KÜÇÜK DELİKLER</div>
        <div style={{font: "900 72px Arial Black, Arial", color: palette.amber}}>BÜYÜK GÖREV</div>
      </div>
    </div>
  );
};
