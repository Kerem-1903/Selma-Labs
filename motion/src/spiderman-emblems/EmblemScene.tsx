import React from "react";
import {interpolate, useCurrentFrame} from "remotion";
import {colors, ComicDots, Sticker, SuitImage, WebCorners} from "./shared";

export const EmblemScene: React.FC<{
  file: string;
  index: number;
  name: string;
  era: string;
  trait: string;
  accent: string;
  position?: string;
  startScale?: number;
  yOffset?: number;
}> = ({file, index, name, era, trait, accent, position, startScale, yOffset}) => {
  const frame = useCurrentFrame();
  return (
    <div style={{position: "absolute", inset: 0, overflow: "hidden"}}>
      <SuitImage file={file} position={position} startScale={startScale} endScale={(startScale ?? 1.07) + .14} darken={.3} yOffset={yOffset} />
      <ComicDots opacity={.1} />
      <WebCorners color={`${accent}70`} />
      <Sticker top={110} left={65} color={accent} rotate={-3}>{index} / 6</Sticker>
      <div style={{position: "absolute", top: 210, right: 60, padding: "18px 25px", borderRadius: 20, background: "rgba(2,4,9,.86)", border: `3px solid ${accent}`, color: "white", font: "900 38px Arial Black, Arial", opacity: interpolate(frame, [2, 10], [0, 1], {extrapolateRight: "clamp"})}}>TAHMİN ET</div>
      <div style={{position: "absolute", left: 55, right: 55, top: 1110, padding: "38px 28px 42px", borderRadius: 38, background: "rgba(2,4,9,.91)", border: `4px solid ${accent}`, boxShadow: `10px 12px 0 ${accent}66`, textAlign: "center", opacity: interpolate(frame, [12, 23], [0, 1], {extrapolateRight: "clamp"}), translate: `0 ${interpolate(frame, [10, 24], [55, 0], {extrapolateRight: "clamp"})}px`}}>
        <div style={{font: "900 72px/.95 Arial Black, Arial", color: accent}}>{name}</div>
        <div style={{font: "900 40px Arial", color: colors.white, marginTop: 18}}>{era}</div>
        <div style={{display: "inline-block", marginTop: 24, padding: "13px 20px", borderRadius: 15, background: accent, color: colors.black, font: "900 34px Arial Black, Arial"}}>{trait}</div>
      </div>
    </div>
  );
};
