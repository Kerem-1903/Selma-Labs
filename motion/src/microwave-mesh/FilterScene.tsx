import React from "react";
import {interpolate, useCurrentFrame} from "remotion";
import {FullImage, palette} from "./shared";

const Wave: React.FC<{top: number; color: string; direction: "in" | "out"; speed: number}> = ({top, color, direction, speed}) => {
  const frame = useCurrentFrame();
  const x = interpolate((frame * speed) % 80, [0, 80], direction === "in" ? [-260, 250] : [250, -260]);
  return <div style={{position: "absolute", top, left: 180, width: 280, height: 12, borderRadius: 8, background: color, boxShadow: `0 0 22px ${color}`, translate: `${x}px 0`}} />;
};

export const FilterScene: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <div style={{position: "absolute", inset: 0, overflow: "hidden"}}>
      <FullImage file="door-mesh.png" darken={0.78} startScale={1.28} endScale={1.42} />
      <div style={{position: "absolute", top: 155, left: 70, right: 70, padding: "24px 22px", borderRadius: 30, background: "rgba(2,5,9,.9)", border: `3px solid ${palette.yellow}`, textAlign: "center", color: "white", font: "900 57px Arial Black, Arial"}}>AYNI AĞ, İKİ SONUÇ</div>
      <div style={{position: "absolute", top: 510, left: 60, width: 960, height: 370, borderRadius: 46, background: "rgba(2,5,9,.86)", border: `3px solid ${palette.amber}`, overflow: "hidden"}}>
        <Wave top={115} color={palette.amber} direction="in" speed={1.25} />
        <Wave top={200} color={palette.amber} direction="out" speed={1.05} />
        <div style={{position: "absolute", left: 493, top: 0, bottom: 0, width: 28, background: palette.amber, boxShadow: `0 0 28px ${palette.amber}`}} />
        <div style={{position: "absolute", left: 35, top: 25, width: 420, textAlign: "center", color: palette.yellow, font: "900 35px Arial Black, Arial", opacity: interpolate(frame, [14, 28], [0, 1], {extrapolateRight: "clamp"})}}>GERİ YANSIR</div>
        <div style={{position: "absolute", right: 35, top: 72, width: 385, textAlign: "center", color: palette.red, font: "900 88px/.95 Arial Black, Arial", opacity: interpolate(frame, [20, 34], [0, 1], {extrapolateRight: "clamp"})}}>✕<br /><span style={{fontSize: 45, color: "white"}}>GEÇEMEZ</span></div>
      </div>
      <div style={{position: "absolute", top: 980, left: 60, width: 960, height: 370, borderRadius: 46, background: "rgba(2,5,9,.86)", border: `3px solid ${palette.cyan}`, overflow: "hidden"}}>
        {[0, 1, 2, 3, 4].map((index) => <Wave key={index} top={82 + index * 48} color={palette.cyan} direction="in" speed={1.4 + index * .08} />)}
        <div style={{position: "absolute", left: 493, top: 0, bottom: 0, width: 28, background: palette.cyan, boxShadow: `0 0 26px ${palette.cyan}`}} />
        <div style={{position: "absolute", right: 25, top: 115, width: 410, textAlign: "center", color: palette.cyan, font: "900 55px/1.05 Arial Black, Arial", opacity: interpolate(frame, [14, 28], [0, 1], {extrapolateRight: "clamp"})}}>IŞIK<br />GEÇER</div>
      </div>
    </div>
  );
};
