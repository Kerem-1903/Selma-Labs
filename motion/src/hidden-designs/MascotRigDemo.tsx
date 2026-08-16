import React from "react";
import {AbsoluteFill,interpolate,useCurrentFrame} from "remotion";
import {HandGesture,MascotRigV1} from "./MascotRigV1";

const clamp={extrapolateLeft:"clamp" as const,extrapolateRight:"clamp" as const};
const beats:{gesture:HandGesture;left:HandGesture;label:string;mood:"idea"|"talk"|"surprise"}[]=[
  {gesture:"point-up",left:"present",label:"PARMAK VURGUSU",mood:"idea"},
  {gesture:"point-right",left:"palm-up",label:"NESNEYİ GÖSTER",mood:"talk"},
  {gesture:"marker",left:"palm-up",label:"TAHTAYA YAZ",mood:"talk"},
  {gesture:"pointer",left:"present",label:"SUNUM YAP",mood:"talk"},
  {gesture:"thumbs-up",left:"fist",label:"ONAYLA",mood:"idea"},
  {gesture:"surprise",left:"palm-stop",label:"TEPKİ VER",mood:"surprise"},
];

export const MascotRigDemo:React.FC=()=>{
  const frame=useCurrentFrame();const beatLength=70;const index=Math.min(beats.length-1,Math.floor(frame/beatLength));const beat=beats[index];const local=frame%beatLength;
  const opacity=interpolate(local,[0,8,58,69],[0,1,1,0],clamp);const slide=interpolate(local,[0,12],[70,0],clamp);
  return <AbsoluteFill style={{background:"radial-gradient(circle at 28% 28%,#244B66,#0A1728 58%,#030812)",fontFamily:"Arial,sans-serif",overflow:"hidden"}}>
    <div style={{position:"absolute",inset:-100,backgroundImage:"radial-gradient(circle,rgba(73,226,246,.2) 2px,transparent 3px)",backgroundSize:"58px 58px",translate:`${-frame*.18}px 0`,opacity:.34}}/>
    <div style={{position:"absolute",left:70,top:120}}><MascotRigV1 rightGesture={beat.gesture} leftGesture={beat.left} mood={beat.mood} scale={1}/></div>
    <div style={{position:"absolute",left:860,right:85,top:300,color:"white",opacity,translate:`${slide}px 0`}}><div style={{font:"1000 76px/.96 Arial",textShadow:"0 7px 0 rgba(0,0,0,.5)"}}>{beat.label}</div><div style={{display:"inline-block",marginTop:35,color:"#07101B",background:index%2?"#51E4F5":"#FFD51F",padding:"13px 22px",font:"1000 28px Arial",rotate:"-2deg",boxShadow:"8px 9px 0 rgba(0,0,0,.45)"}}>EL VE KOL AYRI KATMAN</div></div>
    <div style={{position:"absolute",left:860,right:110,bottom:135,height:9,borderRadius:9,background:"rgba(255,255,255,.12)"}}><div style={{height:"100%",width:`${frame/420*100}%`,background:"linear-gradient(90deg,#51E4F5,#FFD51F,#FF5364)",borderRadius:9}}/></div>
  </AbsoluteFill>;
};
