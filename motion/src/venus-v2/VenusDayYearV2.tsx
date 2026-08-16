import React from "react";
import {AbsoluteFill, Audio, Sequence, staticFile} from "remotion";
import {BrandBug} from "../components/BrandBug";
import {CaptionLayer} from "./CaptionLayer";
import {CompareScene} from "./CompareScene";
import {HookScene} from "./HookScene";
import {OrbitScene} from "./OrbitScene";
import {ReverseScene} from "./ReverseScene";
import {RotationScene} from "./RotationScene";
import {SolarDayScene} from "./SolarDayScene";

export const VenusDayYearV2: React.FC = () => (
  <AbsoluteFill style={{background: "#03050A"}}>
    <Sequence from={0} durationInFrames={108}><HookScene /></Sequence>
    <Sequence from={108} durationInFrames={207}><RotationScene /></Sequence>
    <Sequence from={315} durationInFrames={124}><OrbitScene /></Sequence>
    <Sequence from={439} durationInFrames={116}><CompareScene /></Sequence>
    <Sequence from={555} durationInFrames={109}><ReverseScene /></Sequence>
    <Sequence from={664} durationInFrames={266}><SolarDayScene /></Sequence>
    <Sequence from={92} durationInFrames={838}><BrandBug science="#77E5FF" active="#FFE45E" /></Sequence>
    <CaptionLayer />
    <Audio src={staticFile("venus-v2/music.mp3")} loop volume={0.055} />
    <Audio src={staticFile("venus-v2/narration.mp3")} volume={1} />
  </AbsoluteFill>
);

