import React from "react";
import {interpolate, useCurrentFrame} from "remotion";
import {FullImage, palette} from "./shared";

export const ScaleScene: React.FC = () => {
  const frame = useCurrentFrame();
  const progress = interpolate(frame, [8, 38], [0, 1], {extrapolateRight: "clamp"});
  return (
    <div style={{position: "absolute", inset: 0, overflow: "hidden"}}>
      <FullImage file="door-mesh.png" darken={0.72} startScale={1.27} endScale={1.4} />
      <div style={{position: "absolute", top: 170, left: 75, right: 75, textAlign: "center"}}>
        <div style={{font: "900 51px Arial Black, Arial", color: "white"}}>DALGA BOYU</div>
        <div style={{font: "900 188px/.9 Arial Black, Arial", color: palette.yellow}}>12 CM</div>
      </div>
      <div style={{position: "absolute", left: 100, top: 630, width: 880, height: 34, borderRadius: 20, background: "rgba(255,255,255,.18)", overflow: "hidden"}}>
        <div style={{width: `${progress * 100}%`, height: "100%", background: `linear-gradient(90deg, ${palette.amber}, ${palette.yellow})`, boxShadow: `0 0 28px ${palette.yellow}`}} />
      </div>
      <div style={{position: "absolute", top: 815, left: 85, right: 85, display: "flex", alignItems: "center", gap: 36}}>
        <div style={{width: 440, height: 440, borderRadius: 60, border: `4px solid ${palette.cyan}`, background: "rgba(3,6,10,.8)", overflow: "hidden", position: "relative"}}>
          <div style={{position: "absolute", inset: -40}}><div style={{position: "absolute", inset: 0, opacity: .93, backgroundImage: "radial-gradient(circle, transparent 0 25px, #071017 27px)", backgroundSize: "76px 76px"}} /></div>
        </div>
        <div style={{flex: 1, padding: "44px 20px", borderRadius: 36, background: "rgba(3,6,10,.88)", border: `3px solid ${palette.cyan}`, textAlign: "center"}}>
          <div style={{font: "900 45px Arial", color: "white"}}>DELİKLER</div>
          <div style={{font: "900 72px/1 Arial Black, Arial", color: palette.cyan, marginTop: 14}}>BİRKAÇ</div>
          <div style={{font: "900 82px/1 Arial Black, Arial", color: palette.cyan}}>MM</div>
        </div>
      </div>
    </div>
  );
};
