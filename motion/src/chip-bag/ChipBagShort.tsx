import React from "react";
import type {Caption} from "@remotion/captions";
import {Audio} from "@remotion/media";
import {AbsoluteFill, interpolate, Sequence, Series, staticFile, useCurrentFrame, useVideoConfig} from "remotion";
import {chipBagCaptions} from "./captions";
import {amber} from "./Visuals";
import {HookScene} from "./scenes/HookScene";
import {NitrogenScene} from "./scenes/NitrogenScene";
import {FreshnessScene} from "./scenes/FreshnessScene";
import {CushionScene} from "./scenes/CushionScene";
import {FinaleScene} from "./scenes/FinaleScene";

const Captions: React.FC<{captions: Caption[]}> = ({captions}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const nowMs = frame / fps * 1000;
  const caption = captions.find((item) => nowMs >= item.startMs && nowMs < item.endMs);
  if (!caption) return null;
  const words = caption.text.split(" ");
  const hot = words.findIndex((word) => /YARISI|KANDIRMAK|AZOT|OKSİJEN|BAYATLAR|YASTIK|KIRILIP|İKİ|GRAMAJ/.test(word));
  return (
    <div style={{position: "absolute", left: 54, right: 54, bottom: 260, display: "flex", justifyContent: "center", opacity: interpolate(nowMs, [caption.startMs, caption.startMs + 70, caption.endMs - 80, caption.endMs], [0, 1, 1, 0], {extrapolateLeft: "clamp", extrapolateRight: "clamp"})}}>
      <div style={{maxWidth: 970, padding: "20px 24px 23px", borderRadius: 22, background: "rgba(20,9,2,.86)", borderBottom: `7px solid ${amber}`, color: "white", textAlign: "center", boxShadow: "0 18px 55px rgba(0,0,0,.55)"}}>
        {words.map((word, index) => <span key={`${word}-${index}`} style={{display: "inline-block", marginRight: 12, color: index === hot ? amber : "white", font: "1000 55px/.99 Arial Black, Arial", letterSpacing: -2.3, textShadow: "0 4px 0 #000"}}>{word}</span>)}
      </div>
    </div>
  );
};

export const ChipBagShort: React.FC = () => (
  <AbsoluteFill style={{background: "#160D05", overflow: "hidden", fontFamily: "Arial, sans-serif"}}>
    <Series>
      <Series.Sequence durationInFrames={112}><HookScene/></Series.Sequence>
      <Series.Sequence durationInFrames={93}><NitrogenScene/></Series.Sequence>
      <Series.Sequence durationInFrames={192}><FreshnessScene/></Series.Sequence>
      <Series.Sequence durationInFrames={203}><CushionScene/></Series.Sequence>
      <Series.Sequence durationInFrames={270}><FinaleScene/></Series.Sequence>
    </Series>
    <div style={{position: "absolute", top: 72, right: 48, color: "rgba(255,255,255,.88)", font: "900 22px Arial", letterSpacing: 3}}>STRANGE THINGS LAB</div>
    <Captions captions={chipBagCaptions}/>
    <Audio src={staticFile("chip-bag/narration.mp3")} volume={1}/>
    <Audio src={staticFile("hidden-designs/music-v2-future-tech.mp3")} trimBefore={520} volume={(f) => interpolate(f, [0, 18, 760, 869], [0, .18, .17, .24], {extrapolateLeft: "clamp", extrapolateRight: "clamp"})}/>
    <Sequence from={0}><Audio src={staticFile("phantom-vibration/impact.wav")} volume={.55}/></Sequence>
    <Sequence from={108}><Audio src={staticFile("phantom-vibration/whoosh.wav")} volume={.43}/></Sequence>
    <Sequence from={202}><Audio src={staticFile("phantom-vibration/impact.wav")} volume={.42}/></Sequence>
    <Sequence from={394}><Audio src={staticFile("phantom-vibration/whoosh.wav")} volume={.42}/></Sequence>
    <Sequence from={597}><Audio src={staticFile("phantom-vibration/impact.wav")} volume={.48}/></Sequence>
    <Sequence from={707}><Audio src={staticFile("phantom-vibration/whoosh.wav")} volume={.42}/></Sequence>
  </AbsoluteFill>
);
