import React from "react";
import {AbsoluteFill, OffthreadVideo, staticFile} from "remotion";
import {BigNumber, colors, Eyebrow} from "./shared";

export const SolarDayScene: React.FC = () => (
  <AbsoluteFill style={{background: "#070604", overflow: "hidden"}}>
    <OffthreadVideo
      src={staticFile("venus-v2/venus_current_hd.mp4")}
      trimBefore={80}
      muted
      style={{width: "100%", height: "100%", objectFit: "cover", scale: 1.82}}
    />
    <AbsoluteFill style={{background: "linear-gradient(180deg, rgba(3,2,1,.15), rgba(3,2,1,.2) 40%, #050405 88%)"}} />
    <div style={{position: "absolute", top: 170, left: 0, right: 0, textAlign: "center"}}><Eyebrow>İKİ GÜN DOĞUMU ARASI</Eyebrow></div>
    <div style={{position: "absolute", top: 960, left: 0, right: 0}}><BigNumber number="117" label="DÜNYA GÜNÜ" accent={colors.yellow} /></div>
    <div style={{position: "absolute", top: 245, left: 0, right: 0, textAlign: "center", color: "rgba(255,255,255,.72)", font: "700 21px Arial", letterSpacing: 3}}>NASA GODDARD GÖRSELLEŞTİRMESİ</div>
  </AbsoluteFill>
);
