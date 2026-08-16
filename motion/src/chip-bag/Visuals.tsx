import React from "react";
import {Video} from "@remotion/media";
import {AbsoluteFill, Img, staticFile} from "remotion";

export const amber = "#FFB000";
export const cream = "#FFF3D0";
export const red = "#F04438";
export const ink = "#160D05";

const Shade: React.FC = () => <AbsoluteFill style={{background: "linear-gradient(180deg,rgba(20,8,1,.48),rgba(20,8,1,.02) 40%,rgba(20,8,1,.84) 100%)"}}/>;

export const Film: React.FC<{file: string; trimBefore?: number; brightness?: number; position?: string}> = ({file, trimBefore = 0, brightness = .7, position = "center"}) => (
  <AbsoluteFill style={{background: ink}}>
    <Video src={staticFile(file)} muted loop trimBefore={trimBefore} style={{position: "absolute", top: 0, bottom: 0, left: "50%", width: "auto", minWidth: "100%", maxWidth: "none", height: "100%", translate: "-50% 0", objectFit: "cover", objectPosition: position, filter: `brightness(${brightness}) contrast(1.1) saturate(1.02)`}}/>
    <Shade/>
  </AbsoluteFill>
);

export const Photo: React.FC<{file: string; position?: string}> = ({file, position = "center"}) => (
  <AbsoluteFill style={{background: ink}}>
    <Img src={staticFile(file)} style={{width: "100%", height: "100%", objectFit: "cover", objectPosition: position, filter: "brightness(.72) contrast(1.1) saturate(1.02)"}}/>
    <Shade/>
  </AbsoluteFill>
);

export const Headline: React.FC<{children: React.ReactNode; top?: number; tone?: "amber" | "red"}> = ({children, top = 285, tone = "amber"}) => (
  <div style={{position: "absolute", top, left: 54, right: 54, padding: "27px 30px", background: "rgba(23,12,4,.88)", borderLeft: `12px solid ${tone === "red" ? red : amber}`, color: "white", textAlign: "center", font: "1000 68px/.94 Arial Black", letterSpacing: -2.5, boxShadow: "0 16px 45px rgba(0,0,0,.46)"}}>{children}</div>
);
