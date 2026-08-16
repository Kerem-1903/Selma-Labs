import React from "react";
import {Video} from "@remotion/media";
import {AbsoluteFill,Easing,Img,interpolate,staticFile} from "remotion";
import {MascotRigV2} from "../hidden-designs/MascotRigV2";
import {Diagram} from "./Diagrams";
import {VisualSystem} from "./VisualSystems";
import type {SceneSpec} from "./types";

const C={ink:"#050b14",white:"#f8fbff",yellow:"#ffd42a"};
const poses={pointer:"pointer",marker:"marker",stop:"stop","thumbs-up":"thumbs-up"} as const;
export const SceneRenderer:React.FC<{spec:SceneSpec;local:number;duration:number}>=({spec,local,duration})=>{
 const p=Math.max(0,Math.min(1,local/duration)); const clipMs=spec.mode==="hook"?4600:9200; const beat=Math.floor(Math.max(0,local-(spec.mode==="hook"?9000:0))/clipMs)%Math.max(1,spec.clips.length); const intro=interpolate(local,[0,650],[0,1],{extrapolateLeft:"clamp",extrapolateRight:"clamp",easing:Easing.bezier(.16,1,.3,1)});
 const graphicPhase=(local/1000+spec.id.length*.83)%28;
 const hasDiagram=["network","local","payment","gps","calls","checklist","recovery"].includes(spec.mode);
 const showDiagram=hasDiagram&&graphicPhase>17&&graphicPhase<23;
 const mascotPhase=(local/1000+spec.id.length*1.7)%31;
 const mascotVisible=spec.mascot&&mascotPhase>20&&mascotPhase<27;
 const visualModes=["hook","network","payment","gps","calls","news","logistics","critical","evening","recovery","outro"];
 const hasVisual=visualModes.includes(spec.mode);
 const showVisual=hasVisual&&(spec.mode==="hook"?(local>14500&&local<32900):graphicPhase>4&&graphicPhase<14);
 const visualOpacity=spec.mode==="hook"?interpolate(local,[14500,15300,31600,32900],[0,1,1,0],{extrapolateLeft:"clamp",extrapolateRight:"clamp"}):interpolate(graphicPhase,[4,4.8,13.2,14],[0,1,1,0],{extrapolateLeft:"clamp",extrapolateRight:"clamp"});
 const titleFade=interpolate(local,[0,600,6200,7600],[0,1,1,.84],{extrapolateLeft:"clamp",extrapolateRight:"clamp"});
 const compact=showDiagram||showVisual||local>7600;
 const titleOnRight=["evening","checklist","outro"].includes(spec.mode)&&!showVisual&&!showDiagram;
 return <AbsoluteFill style={{background:C.ink,overflow:"hidden"}}>
  {spec.mode==="hook"&&local<15000?<Img src={staticFile("internet-outage/istanbul-network-outage.png")} style={{width:"100%",height:"100%",objectFit:"cover",transform:`scale(${1.03+local/170000})`}}/>:<Video key={`${spec.id}-${beat}`} src={staticFile(`internet-outage/footage/${spec.clips[beat]}.mp4`)} loop muted style={{width:"100%",height:"100%",objectFit:"cover",transform:`scale(${1.035+(local%clipMs)/120000})`}}/>}
  {spec.mode==="hook"&&local>9000&&<div style={{position:"absolute",right:75,top:160,width:560,display:"grid",gap:12,zIndex:18}}>{[["KARTLAR?",10500],["112?",16000],["GPS?",21500],["MARKETLER?",27000]].map(([label,start])=>{const visible=local>Number(start)&&local<Number(start)+4300;return visible?<div key={String(label)} style={{padding:"18px 24px",background:"rgba(3,9,17,.9)",borderRight:`8px solid ${spec.accent}`,color:C.white,font:"1000 45px Arial",textAlign:"right",boxShadow:"0 15px 35px rgba(0,0,0,.55)"}}>{label}</div>:null})}</div>}
  <AbsoluteFill style={{background:"linear-gradient(90deg,rgba(3,8,16,.97) 0%,rgba(3,8,16,.82) 38%,rgba(3,8,16,.18) 70%),linear-gradient(180deg,rgba(0,0,0,.4),transparent 30%,rgba(0,0,0,.68))"}}/>
  {showVisual&&<div style={{position:"absolute",inset:0,opacity:visualOpacity,zIndex:10}}><div style={{position:"absolute",inset:0,background:"radial-gradient(circle at 70% 45%,rgba(15,39,61,.97),rgba(3,8,15,.98) 64%)"}}/><div style={{position:"absolute",inset:0,zIndex:12}}><VisualSystem mode={spec.mode} local={local} accent={spec.accent} sceneId={spec.id}/></div></div>}
  {showDiagram&&!showVisual&&<><div style={{position:"absolute",left:540,top:230,width:1240,height:620,background:"rgba(3,9,17,.77)",border:"1px solid rgba(255,255,255,.18)",backdropFilter:"blur(12px)"}}/><Diagram mode={spec.mode} p={Math.min(1,(graphicPhase-17)/1.2)} local={local}/></>}
  <div style={{position:"absolute",left:titleOnRight?1050:80,top:92,width:titleOnRight?790:compact?430:980,opacity:intro,transform:`translateX(${(1-intro)*(titleOnRight?45:-45)}px)`,textAlign:titleOnRight?"right":"left",zIndex:20}}>
   <div style={{display:"inline-block",padding:"9px 15px",background:"rgba(0,0,0,.74)",borderLeft:titleOnRight?undefined:`8px solid ${spec.accent}`,borderRight:titleOnRight?`8px solid ${spec.accent}`:undefined,color:C.white,font:"1000 22px Arial",letterSpacing:2.4}}>{spec.eyebrow}</div>
   <div style={{marginTop:24,whiteSpace:"pre-line",color:C.white,font:`1000 ${titleOnRight?60:compact?48:spec.mode==="outro"?67:82}px/.93 Arial`,textShadow:"0 7px 25px #000",opacity:titleFade}}>{spec.headline}</div>
   {spec.metric&&<div style={{display:"inline-block",maxWidth:titleOnRight?700:compact?420:760,marginTop:compact?26:42,padding:compact?"14px 18px":"18px 24px",background:"rgba(3,10,19,.9)",borderLeft:titleOnRight?undefined:`9px solid ${spec.accent}`,borderRight:titleOnRight?`9px solid ${spec.accent}`:undefined,boxShadow:"0 17px 38px rgba(0,0,0,.45)"}}><div style={{color:spec.accent,font:`1000 ${compact?31:43}px Arial`}}>{spec.metric}</div><div style={{marginTop:5,color:C.white,font:`900 ${compact?18:22}px Arial`}}>{spec.metricLabel}</div></div>}
  </div>
  {mascotVisible&&<div style={{position:"absolute",right:-55,bottom:58,width:720,height:790,filter:"drop-shadow(0 25px 30px rgba(0,0,0,.75))",zIndex:70}}><MascotRigV2 leftPose="present" rightPose={poses[spec.mascot!]} mood={spec.mascot==="stop"?"surprise":spec.mascot==="thumbs-up"?"idea":"explain"} motion={spec.mascot==="marker"?"write":spec.mascot==="stop"?"recoil":spec.mascot==="thumbs-up"?"celebrate":"scan"} actionFrame={Math.floor(local/33)} scale={.63}/></div>}
  <div style={{position:"absolute",right:32,top:28,color:"rgba(255,255,255,.8)",font:"900 17px Arial",letterSpacing:1.8}}>STRANGE THINGS LAB</div>
  <div style={{position:"absolute",left:0,bottom:0,height:7,width:`${p*100}%`,background:spec.accent,boxShadow:`0 0 15px ${spec.accent}`}}/>
 </AbsoluteFill>;
};
