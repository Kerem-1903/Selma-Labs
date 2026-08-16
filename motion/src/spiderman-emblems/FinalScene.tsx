import React from "react";
import {Img, interpolate, staticFile, useCurrentFrame} from "remotion";
import {colors, ComicDots, Sticker, WebCorners} from "./shared";

const items = ["tobey.png", "andrew.jpg", "tom.jpg", "iron.jpg", "miles.jpg", "symbiote.jpg"];

export const FinalScene: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <div style={{position: "absolute", inset: 0, overflow: "hidden", background: "linear-gradient(145deg,#71131e,#090b12 55%,#123270)"}}>
      <ComicDots opacity={.18} />
      <WebCorners />
      <Sticker top={105} left={70} color={colors.yellow} rotate={-4}>SON SORU</Sticker>
      <div style={{position: "absolute", top: 270, left: 40, right: 40, display: "flex", flexWrap: "wrap", gap: 14, justifyContent: "center"}}>
        {items.map((file, index) => <div key={file} style={{width: 300, height: 390, overflow: "hidden", borderRadius: 22, border: `4px solid ${index % 2 ? colors.blue : colors.red}`, opacity: interpolate(frame, [index * 3, index * 3 + 8], [0, 1], {extrapolateRight: "clamp"}), scale: interpolate(frame, [index * 3, index * 3 + 8], [.72, 1], {extrapolateRight: "clamp"})}}><Img src={staticFile(`spiderman-emblems/${file}`)} style={{width: "100%", height: "100%", objectFit: "cover"}} /></div>)}
      </div>
      <div style={{position: "absolute", left: 55, right: 55, top: 1125, padding: "40px 22px", borderRadius: 38, border: `4px solid ${colors.white}`, background: "rgba(3,5,10,.93)", textAlign: "center", boxShadow: `11px 13px 0 ${colors.red}99`}}>
        <div style={{font: "900 65px Arial Black, Arial", color: "white"}}>HANGİSİNİ</div>
        <div style={{font: "900 95px/.95 Arial Black, Arial", color: colors.yellow}}>TEK BAKIŞTA</div>
        <div style={{font: "900 70px Arial Black, Arial", color: "white"}}>TANIDIN?</div>
      </div>
    </div>
  );
};
