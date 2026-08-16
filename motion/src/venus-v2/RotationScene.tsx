import React from "react";
import {interpolate, useCurrentFrame} from "remotion";
import {colors, FullBleedImage, InfoPill} from "./shared";

export const RotationScene: React.FC = () => {
  const frame = useCurrentFrame();
  const angle = interpolate(frame, [0, 207], [-25, 120]);
  return (
    <div style={{position: "absolute", inset: 0, overflow: "hidden"}}>
      <FullBleedImage file="magellan_global.jpg" darken={0.44} startScale={1.1} endScale={1.24} objectPosition="48% center" />
      <div
        style={{
          position: "absolute",
          width: 750,
          height: 750,
          left: 165,
          top: 350,
          border: `8px solid ${colors.cyan}`,
          borderLeftColor: "transparent",
          borderRadius: "50%",
          rotate: `${angle}deg`,
          filter: "drop-shadow(0 0 15px rgba(119,229,255,.55))",
        }}
      />
      <InfoPill text="KENDİ EKSENİNDE" top={145} width={520} />
      {frame > 120 ? <InfoPill text="YILDIZ GÜNÜ" top={250} width={390} /> : null}
      <div style={{position: "absolute", top: 1000, left: 80, right: 80, background: "rgba(3,7,13,.86)", border: `3px solid ${colors.gold}`, borderRadius: 44, padding: "36px 40px", textAlign: "center", boxShadow: "0 20px 55px rgba(0,0,0,.45)"}}>
        <div style={{font: "900 205px/.9 Arial Black, Arial", color: colors.gold}}>243</div>
        <div style={{font: "900 48px Arial", color: "white"}}>DÜNYA GÜNÜ</div>
      </div>
    </div>
  );
};
