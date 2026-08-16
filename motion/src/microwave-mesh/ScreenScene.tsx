import React from "react";
import {interpolate, useCurrentFrame} from "remotion";
import {FullImage, InfoPill, MeshPattern, palette} from "./shared";

export const ScreenScene: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <div style={{position: "absolute", inset: 0, overflow: "hidden"}}>
      <FullImage file="door-mesh.png" darken={0.55} startScale={1.42} endScale={1.62} objectPosition="48% center" />
      <InfoPill top={155} color={palette.red}>BOYA DEĞİL</InfoPill>
      <div style={{position: "absolute", top: 450, left: 75, right: 75, textAlign: "center", opacity: interpolate(frame, [10, 24], [0, 1], {extrapolateRight: "clamp"})}}>
        <div style={{font: "900 72px Arial Black, Arial", color: "white"}}>İNCE BİR</div>
        <div style={{font: "900 126px/.95 Arial Black, Arial", color: palette.cyan}}>METAL EKRAN</div>
      </div>
      <div style={{position: "absolute", top: 795, left: 180, width: 720, height: 520, overflow: "hidden", borderRadius: 70, border: `5px solid ${palette.cyan}`, background: "rgba(255,255,255,.07)", boxShadow: `0 0 44px ${palette.cyan}44`, scale: 1 + Math.sin(frame / 11) * 0.018}}>
        <MeshPattern opacity={0.85} hole={24} />
      </div>
    </div>
  );
};
