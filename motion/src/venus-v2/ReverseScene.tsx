import React from "react";
import {interpolate, useCurrentFrame} from "remotion";
import {colors, FullBleedImage, InfoPill} from "./shared";

export const ReverseScene: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <div style={{position: "absolute", inset: 0, overflow: "hidden"}}>
      <FullBleedImage file="mariner_venus_single.jpg" darken={0.48} startScale={1.34} endScale={1.55} objectPosition="55% center" />
      <InfoPill text="ÇOĞU GEZEGENİN TERSİNE" top={145} width={690} />
      <div style={{position: "absolute", top: 760, left: 90, right: 90, background: "rgba(4,6,11,.88)", border: `3px solid ${colors.gold}`, borderRadius: 48, padding: "42px 46px", textAlign: "center", opacity: interpolate(frame, [8, 18], [0, 1], {extrapolateRight: "clamp"})}}>
        <div style={{font: "900 62px Arial Black, Arial", color: "white"}}>DOĞUDAN BATIYA</div>
        <div style={{font: "900 100px Arial", color: colors.yellow, marginTop: 15}}>↺</div>
        <div style={{font: "800 35px Arial", color: "#CBD3E0"}}>TERS YÖNDE DÖNÜYOR</div>
      </div>
    </div>
  );
};
