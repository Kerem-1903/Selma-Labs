import React from "react";
import {interpolate, useCurrentFrame} from "remotion";
import {colors, FullBleedImage, InfoPill} from "./shared";

const Stat: React.FC<{title: string; number: string; color: string}> = ({title, number, color}) => (
  <div style={{width: 410, height: 440, borderRadius: 46, border: `3px solid ${color}`, background: "rgba(10,13,20,.82)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", boxShadow: `0 0 35px ${color}25`}}>
    <div style={{font: "900 28px Arial", color, letterSpacing: 4, marginBottom: 22}}>{title}</div>
    <div style={{font: "900 150px/1 Arial Black, Arial", color}}>{number}</div>
    <div style={{font: "900 29px Arial", color: "white", letterSpacing: 2}}>DÜNYA GÜNÜ</div>
  </div>
);

export const CompareScene: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <div style={{position: "absolute", inset: 0, overflow: "hidden"}}>
      <FullBleedImage file="magellan_global.jpg" darken={0.64} startScale={1.5} endScale={1.68} objectPosition="55% center" />
      <InfoPill text="VENÜS'ÜN ZAMAN HATASI" top={145} width={720} />
      <div style={{position: "absolute", top: 405, left: 90, right: 90, display: "flex", gap: 80, translate: `0 ${Math.sin(frame / 11) * 7}px`}}>
        <Stat title="DÖNÜŞ" number="243" color={colors.cyan} />
        <Stat title="YIL" number="225" color={colors.gold} />
      </div>
      <div style={{position: "absolute", top: 1020, left: 0, right: 0, textAlign: "center", opacity: interpolate(frame, [24, 38], [0, 1], {extrapolateRight: "clamp"}), scale: interpolate(frame, [24, 42], [0.75, 1], {extrapolateRight: "clamp"}) * (1 + Math.sin(frame / 9) * 0.012)}}>
        <div style={{font: "900 210px/.9 Arial Black, Arial", color: colors.yellow}}>+18</div>
        <div style={{font: "900 55px Arial", color: "white"}}>DÜNYA GÜNÜ</div>
        <div style={{font: "800 38px Arial", color: "#B9C2D3", marginTop: 35}}>GÜNÜ, YILINDAN DAHA UZUN</div>
      </div>
    </div>
  );
};
