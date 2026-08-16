import React from "react";
import {Img, interpolate, staticFile, useCurrentFrame} from "remotion";
import {colors, ComicDots, WebCorners} from "./shared";

const items = ["tobey.png", "andrew.jpg", "tom.jpg", "iron.jpg", "miles.jpg", "symbiote.jpg"];

export const IdentityScene: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <div style={{position: "absolute", inset: 0, overflow: "hidden", background: "linear-gradient(155deg,#15356b,#080b13 50%,#71131e)"}}>
      <ComicDots opacity={.16} />
      <WebCorners />
      <div style={{position: "absolute", top: 150, left: 55, right: 55, display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 15}}>
        {items.map((file, index) => <div key={file} style={{height: 395, overflow: "hidden", borderRadius: 24, border: `4px solid ${index % 2 ? colors.blue : colors.red}`, translate: `0 ${Math.sin((frame + index * 8) / 12) * 8}px`}}><Img src={staticFile(`spiderman-emblems/${file}`)} style={{width: "100%", height: "100%", objectFit: "cover"}} /></div>)}
      </div>
      <div style={{position: "absolute", top: 1040, left: 60, right: 60, padding: "43px 26px", borderRadius: 40, background: "rgba(2,4,9,.92)", border: `4px solid ${colors.yellow}`, boxShadow: `12px 14px 0 ${colors.red}88`, textAlign: "center", opacity: interpolate(frame, [5, 17], [0, 1], {extrapolateRight: "clamp"})}}>
        <div style={{font: "900 53px Arial Black, Arial", color: "white"}}>SADECE LOGO DEĞİL</div>
        <div style={{font: "900 88px/.98 Arial Black, Arial", color: colors.yellow, marginTop: 16}}>KİMLİK KARTI</div>
        <div style={{font: "800 36px Arial", color: "#C8D6FF", marginTop: 24}}>EVRENİ + DÖNEMİ ELE VERİYOR</div>
      </div>
    </div>
  );
};
