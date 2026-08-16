import React from "react";
import {AbsoluteFill, Audio, Sequence, staticFile} from "remotion";
import {BrandBug} from "../components/BrandBug";
import {CaptionLayer} from "./CaptionLayer";
import {FilterScene} from "./FilterScene";
import {FinalScene} from "./FinalScene";
import {HookScene} from "./HookScene";
import {MagnetronScene} from "./MagnetronScene";
import {ScaleScene} from "./ScaleScene";
import {ScreenScene} from "./ScreenScene";

export const MicrowaveMeshShort: React.FC = () => (
  <AbsoluteFill style={{background: "#030507"}}>
    <Sequence from={0} durationInFrames={139}><HookScene /></Sequence>
    <Sequence from={139} durationInFrames={105}><ScreenScene /></Sequence>
    <Sequence from={244} durationInFrames={153}><MagnetronScene /></Sequence>
    <Sequence from={397} durationInFrames={183}><ScaleScene /></Sequence>
    <Sequence from={580} durationInFrames={157}><FilterScene /></Sequence>
    <Sequence from={737} durationInFrames={223}><FinalScene /></Sequence>
    <Sequence from={42} durationInFrames={918}><BrandBug science="#6EEBFF" active="#FFE45E" /></Sequence>
    <CaptionLayer />
    <Audio src={staticFile("microwave-mesh/music.mp3")} loop volume={0.045} />
    <Audio src={staticFile("microwave-mesh/narration.mp3")} volume={1} />
  </AbsoluteFill>
);
