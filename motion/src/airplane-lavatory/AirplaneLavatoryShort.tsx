import React from "react";
import type {Caption} from "@remotion/captions";
import {Audio} from "@remotion/media";
import {AbsoluteFill, interpolate, Sequence, Series, staticFile, useCurrentFrame, useVideoConfig} from "remotion";
import {airplaneLavatoryCaptions} from "./captions";
import {FinaleScene, GroundServiceScene, HookScene, LavatoryReveal, LockedTankScene, VacuumDiagram, WhooshScene} from "./scenes";

const cyan = "#23D5E8";
const yellow = "#FFD83D";

const Captions: React.FC<{captions: Caption[]}> = ({captions}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const nowMs = frame / fps * 1000;
  const caption = captions.find((item) => nowMs >= item.startMs && nowMs < item.endMs);
  if (!caption) return null;
  const words = caption.text.split(" ");
  const hot = words.findIndex((word) => /ATIKLAR|AŞAĞI|HAYIR|VAKUM|TANKA|FOŞ|KİLİTLİ|HORTUM|ARACA|DELİK|MÜHÜRLÜ/.test(word));
  return (
    <div style={{position: "absolute", left: 54, right: 54, bottom: 260, display: "flex", justifyContent: "center", opacity: interpolate(nowMs, [caption.startMs, caption.startMs + 75, caption.endMs - 80, caption.endMs], [0, 1, 1, 0], {extrapolateLeft: "clamp", extrapolateRight: "clamp"})}}>
      <div style={{maxWidth: 970, padding: "20px 24px 23px", borderRadius: 22, background: "rgba(1,9,20,.84)", borderBottom: `7px solid ${cyan}`, color: "white", textAlign: "center", boxShadow: "0 18px 55px rgba(0,0,0,.55)"}}>
        {words.map((word, index) => <span key={`${word}-${index}`} style={{display: "inline-block", marginRight: 12, color: index === hot ? yellow : "white", font: "1000 55px/.99 Arial Black, Arial", letterSpacing: -2.3, textShadow: "0 4px 0 #000"}}>{word}</span>)}
      </div>
    </div>
  );
};

export const AirplaneLavatoryShort: React.FC = () => {
  return (
    <AbsoluteFill style={{background: "#071A2E", overflow: "hidden", fontFamily: "Arial, sans-serif"}}>
      <Series>
        <Series.Sequence durationInFrames={128}><HookScene/></Series.Sequence>
        <Series.Sequence durationInFrames={26}><LavatoryReveal/></Series.Sequence>
        <Series.Sequence durationInFrames={184}><VacuumDiagram/></Series.Sequence>
        <Series.Sequence durationInFrames={109}><WhooshScene/></Series.Sequence>
        <Series.Sequence durationInFrames={72}><LockedTankScene/></Series.Sequence>
        <Series.Sequence durationInFrames={205}><GroundServiceScene/></Series.Sequence>
        <Series.Sequence durationInFrames={206}><FinaleScene/></Series.Sequence>
      </Series>
      <div style={{position: "absolute", top: 72, right: 48, color: "rgba(255,255,255,.88)", font: "900 22px Arial", letterSpacing: 3}}>STRANGE THINGS LAB</div>
      <Captions captions={airplaneLavatoryCaptions}/>
      <Audio src={staticFile("airplane-lavatory/narration.mp3")} volume={1}/>
      <Audio src={staticFile("hidden-designs/music-v2-future-tech.mp3")} trimBefore={1180} volume={(f) => interpolate(f, [0, 18, 800, 929], [0, .18, .17, .25], {extrapolateLeft: "clamp", extrapolateRight: "clamp"})}/>
      <Sequence from={0}><Audio src={staticFile("phantom-vibration/impact.wav")} volume={.58}/></Sequence>
      <Sequence from={125}><Audio src={staticFile("phantom-vibration/whoosh.wav")} volume={.52}/></Sequence>
      <Sequence from={151}><Audio src={staticFile("phantom-vibration/impact.wav")} volume={.52}/></Sequence>
      <Sequence from={328}><Audio src={staticFile("phantom-vibration/whoosh.wav")} volume={.65}/></Sequence>
      <Sequence from={444}><Audio src={staticFile("phantom-vibration/impact.wav")} volume={.48}/></Sequence>
      <Sequence from={516}><Audio src={staticFile("phantom-vibration/whoosh.wav")} volume={.46}/></Sequence>
      <Sequence from={717}><Audio src={staticFile("phantom-vibration/impact.wav")} volume={.55}/></Sequence>
    </AbsoluteFill>
  );
};
