import React from "react";
import {AbsoluteFill,Audio,interpolate,staticFile,useCurrentFrame,useVideoConfig} from "remotion";
import data from "../../public/internet-outage/data.json";
import {Captions} from "./Captions";
import {SceneRenderer} from "./SceneRenderer";
import {sceneSpecs} from "./scenes";
import type {Chapter,Word} from "./types";

const chapters=data.chapters as Chapter[]; const words=data.words as Word[];
export const InternetOutageVideo:React.FC<{qaStrideFrames?:number;includeAudio?:boolean}>=({qaStrideFrames=1,includeAudio=true})=>{const frame=useCurrentFrame();const {fps,durationInFrames}=useVideoConfig();const sourceFrame=frame*qaStrideFrames;const now=sourceFrame/fps*1000;const chapter=chapters.find(c=>now>=c.startMs&&now<c.endMs)??chapters[chapters.length-1];const spec=sceneSpecs[chapter.id]??sceneSpecs.outro;return <AbsoluteFill style={{background:"#050b14",fontFamily:"Arial,sans-serif"}}><SceneRenderer spec={spec} local={now-chapter.startMs} duration={chapter.endMs-chapter.startMs}/><Captions words={words} now={now}/>{includeAudio&&<><Audio src={staticFile("internet-outage/narration-mastered.mp3")}/><Audio src={staticFile("hidden-designs/music-v2-future-tech.mp3")} volume={(f)=>interpolate(f,[0,60,240,durationInFrames-180,durationInFrames-1],[0,.03,.03,.026,0],{extrapolateLeft:"clamp",extrapolateRight:"clamp"})}/></>}</AbsoluteFill>};
