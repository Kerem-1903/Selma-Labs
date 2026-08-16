import React from "react";
import {interpolate, useCurrentFrame} from "remotion";
import {colors, FullBleedImage, InfoPill} from "./shared";

export const OrbitScene: React.FC = () => {
  const frame = useCurrentFrame();
  const angle = interpolate(frame, [0, 124], [-85, 255]);
  const radiusX = 395;
  const radiusY = 250;
  const x = 540 + Math.cos((angle * Math.PI) / 180) * radiusX;
  const y = 590 + Math.sin((angle * Math.PI) / 180) * radiusY;
  return (
    <div style={{position: "absolute", inset: 0, overflow: "hidden"}}>
      <FullBleedImage file="magellan_north.jpg" darken={0.57} startScale={1.05} endScale={1.18} />
      <InfoPill text="GÜNEŞ'İN ÇEVRESİNDE" top={145} width={610} />
      <div style={{position: "absolute", width: 900, height: 570, left: 90, top: 410, border: "5px solid rgba(255,255,255,.62)", borderRadius: "50%", rotate: "-12deg", boxShadow: "0 0 25px rgba(255,255,255,.12)"}} />
      <div style={{position: "absolute", width: 270, height: 270, left: 405, top: 545, borderRadius: "50%", background: "radial-gradient(circle at 40% 40%, #FFF8B8, #FFB21E 42%, #E75B00 76%)", boxShadow: "0 0 85px #FF9C24"}} />
      <div style={{position: "absolute", width: 105, height: 105, left: x - 52, top: y - 52, borderRadius: "50%", background: "radial-gradient(circle at 35% 35%, #FFF0C4, #D98A2D 62%, #5A210E)", boxShadow: `0 0 25px ${colors.gold}`}} />
      <div style={{position: "absolute", top: 1090, left: 100, right: 100, background: "rgba(3,7,13,.86)", borderRadius: 44, padding: "30px", textAlign: "center", border: `3px solid ${colors.yellow}`}}>
        <div style={{font: "900 195px/.9 Arial Black, Arial", color: colors.yellow}}>225</div>
        <div style={{font: "900 45px Arial", color: "white"}}>DÜNYA GÜNÜ</div>
      </div>
    </div>
  );
};
