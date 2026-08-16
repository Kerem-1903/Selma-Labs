import React from "react";
import {AbsoluteFill,Easing,interpolate,Sequence,useCurrentFrame,useVideoConfig} from "remotion";
import {LabHostV2} from "./LabHostV2";

const Spark:React.FC<{x:number;y:number;delay:number;color:string}>=({x,y,delay,color})=>{const frame=useCurrentFrame();const p=interpolate(frame,[delay,delay+10,delay+28],[0,1,0],{extrapolateLeft:"clamp",extrapolateRight:"clamp"});return <div style={{position:"absolute",left:x,top:y,width:14,height:52,borderRadius:8,background:color,opacity:p,scale:interpolate(p,[0,1],[.4,1]),rotate:`${(x+y)%70-35}deg`,boxShadow:`0 0 18px ${color}`}}/>};

const BeatCard:React.FC<{from:number;title:string;accent:string}>=({from,title,accent})=>{const frame=useCurrentFrame()-from;const {fps}=useVideoConfig();return <div style={{position:"absolute",left:690,top:250,color:"white",opacity:interpolate(frame,[0,8,75,88],[0,1,1,0],{extrapolateLeft:"clamp",extrapolateRight:"clamp"}),translate:`${interpolate(frame,[0,12],[90,0],{extrapolateLeft:"clamp",extrapolateRight:"clamp",easing:Easing.out(Easing.cubic)})}px 0`}}><div style={{font:"1000 32px Arial",color:"#101824",background:accent,display:"inline-block",padding:"10px 18px",rotate:"-2deg"}}>MASKOT HAREKET TESTİ</div><div style={{font:"1000 94px/.95 Arial",marginTop:25,textShadow:"0 8px 0 rgba(0,0,0,.35)",maxWidth:1050}}>{title}</div></div>};

export const MascotAnimationDemo:React.FC=()=>{const frame=useCurrentFrame();const pose=frame<105?"idea":frame<210?"explain":frame<315?"point":"surprise";const bgX=interpolate(frame,[0,450],[0,-120]);return <AbsoluteFill style={{background:"radial-gradient(circle at 30% 25%,#21415A,#0B1625 58%,#040913)",overflow:"hidden",fontFamily:"Arial"}}>
  <div style={{position:"absolute",inset:-150,backgroundImage:"radial-gradient(circle,rgba(81,228,245,.24) 2px,transparent 3px)",backgroundSize:"62px 62px",translate:`${bgX}px 0`,opacity:.35}}/>
  <div style={{position:"absolute",left:120,bottom:42,width:410,height:45,borderRadius:"50%",background:"rgba(0,0,0,.42)",filter:"blur(13px)",scale:`${1+Math.sin(frame/18)*.03} 1`}}/>
  <LabHostV2 pose={pose} scale={1.05}/>
  <Sequence from={0} durationInFrames={105}><BeatCard from={0} title="PARMAK VURGUSU" accent="#FFD51F"/></Sequence>
  <Sequence from={105} durationInFrames={105}><BeatCard from={105} title="KONUŞMA RİTMİ" accent="#51E4F5"/></Sequence>
  <Sequence from={210} durationInFrames={105}><BeatCard from={210} title="TAKİP EDEN KAFA" accent="#FF5364"/></Sequence>
  <Sequence from={315} durationInFrames={135}><BeatCard from={315} title="TEPKİ + IŞIK MİMİĞİ" accent="#FFD51F"/></Sequence>
  {[0,1,2,3,4,5].map(i=><Spark key={i} x={545+Math.cos(i)*85} y={120+Math.sin(i*1.7)*85} delay={18+i*3} color={i%2?"#FFD51F":"#51E4F5"}/>)}
  {frame%105>62&&frame%105<86&&<div style={{position:"absolute",left:520,top:120,color:"#FFD51F",font:"1000 68px Arial",rotate:"9deg",textShadow:"0 0 18px rgba(255,213,31,.7)"}}>!</div>}
  <div style={{position:"absolute",left:690,right:100,bottom:120,height:8,borderRadius:9,background:"rgba(255,255,255,.12)"}}><div style={{height:"100%",width:`${frame/450*100}%`,background:"linear-gradient(90deg,#51E4F5,#FFD51F)",borderRadius:9}}/></div>
</AbsoluteFill>};
