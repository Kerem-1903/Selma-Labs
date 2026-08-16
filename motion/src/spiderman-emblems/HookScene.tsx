import React from "react";
import {Img, interpolate, staticFile, useCurrentFrame} from "remotion";
import {colors, ComicDots, Sticker, WebCorners} from "./shared";

const items = ["tobey.png", "andrew.jpg", "tom.jpg", "iron.jpg", "miles.jpg", "symbiote.jpg"];

export const HookScene: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <div style={{position: "absolute", inset: 0, overflow: "hidden", background: "linear-gradient(145deg,#09152b,#05070c 56%,#2a080d)"}}>
      <ComicDots opacity={0.15} />
      <WebCorners />
      <div style={{position: "absolute", top: 125, left: 42, right: 42, height: 970, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, rotate: "-2deg", scale: interpolate(frame, [0, 150], [1.04, 1.16], {extrapolateRight: "clamp"})}}>
        {items.map((file, index) => (
          <div key={file} style={{overflow: "hidden", borderRadius: 22, border: `5px solid ${index % 2 ? colors.blue : colors.red}`, boxShadow: "0 12px 25px rgba(0,0,0,.5)"}}>
            <Img src={staticFile(`spiderman-emblems/${file}`)} style={{width: "100%", height: "100%", objectFit: "cover", objectPosition: "center"}} />
          </div>
        ))}
      </div>
      <div style={{position: "absolute", top: 1140, left: 55, right: 55, padding: "38px 24px 43px", background: "rgba(3,5,10,.92)", borderRadius: 36, border: `4px solid ${colors.white}`, textAlign: "center", boxShadow: "12px 14px 0 rgba(241,59,59,.8)", opacity: interpolate(frame, [4, 13], [0, 1], {extrapolateRight: "clamp"}), scale: interpolate(frame, [3, 14], [.8, 1], {extrapolateRight: "clamp"})}}>
        <div style={{font: "900 57px Arial Black, Arial", color: colors.white}}>YÜZÜNÜ GÖRMEDEN</div>
        <div style={{font: "900 83px/.98 Arial Black, Arial", color: colors.yellow, marginTop: 12}}>HANGİ SPIDER-MAN?</div>
      </div>
      <Sticker top={80} left={55} color={colors.yellow} rotate={-4}>ÖRÜMCEK TESTİ</Sticker>
    </div>
  );
};
