import React from "react";
import {AbsoluteFill,Easing,Img,interpolate,spring,staticFile,useCurrentFrame,useVideoConfig} from "remotion";

type View="front"|"three"|"side"|"back"|"finger";
const crop:Record<View,{x:number;y:number;w:number;h:number}>={
  front:{x:45,y:135,w:310,h:570},
  three:{x:405,y:135,w:310,h:570},
  side:{x:785,y:135,w:205,h:570},
  back:{x:1070,y:135,w:300,h:570},
  finger:{x:1390,y:135,w:365,h:570},
};
const clamp={extrapolateLeft:"clamp" as const,extrapolateRight:"clamp" as const};

const Character:React.FC<{view:View;opacity?:number;scale?:number;rotate?:number;x?:number;y?:number}>=({view,opacity=1,scale=1,rotate=0,x=0,y=0})=>{
  const c=crop[view];
  return <div style={{position:"absolute",left:0,top:0,width:c.w,height:c.h,overflow:"hidden",opacity,scale,rotate:`${rotate}deg`,translate:`${x}px ${y}px`,transformOrigin:"center bottom",filter:"drop-shadow(0 28px 22px rgba(0,0,0,.35))"}}>
    <Img src={staticFile("hidden-designs/maskot-turnaround-v3-alpha.png")} style={{position:"absolute",left:-c.x,top:-c.y,width:1774,height:887,maxWidth:"none"}}/>
  </div>;
};

const Turntable:React.FC=()=>{
  const frame=useCurrentFrame();
  const local=frame-145;
  const views:View[]=["three","side","back","side","three"];
  const index=Math.min(4,Math.max(0,Math.floor(local/24)));
  const next=Math.min(4,index+1);
  const mix=interpolate(local-index*24,[13,24],[0,1],clamp);
  return <div style={{position:"absolute",left:250,top:210,width:420,height:650}}>
    <Character view={views[index]} opacity={1-mix} scale={1.08} x={views[index]==="side"?55:0}/>
    <Character view={views[next]} opacity={mix} scale={1.08} x={views[next]==="side"?55:0}/>
  </div>;
};

const Accent:React.FC<{angle:number;delay:number;color:string}>=({angle,delay,color})=>{
  const frame=useCurrentFrame();
  const p=interpolate(frame,[delay,delay+8,delay+23],[0,1,0],clamp);
  return <div style={{position:"absolute",left:575,top:120,width:13,height:70,borderRadius:9,background:color,opacity:p,rotate:`${angle}deg`,translate:`${Math.cos(angle)*55}px ${Math.sin(angle)*35}px`,scale:interpolate(p,[0,1],[.4,1]),boxShadow:`0 0 20px ${color}`}}/>;
};

export const MascotIllustratedDemo:React.FC=()=>{
  const frame=useCurrentFrame();
  const {fps}=useVideoConfig();
  const enter=spring({frame,fps,config:{damping:11,stiffness:120}});
  const fingerBeat=frame<140?Math.sin(frame/fps*Math.PI*2.8)*2:0;
  const showTurn=frame>=145&&frame<270;
  const pointingOpacity=showTurn?0:1;
  const pointReturn=spring({frame:frame-270,fps,config:{damping:10,stiffness:150}});
  const title=showTurn?"ÖN • YAN • ARKA":frame<145?"AYNI ÇİZİM. GERÇEK HAREKET.":"BURAYA DİKKAT!";
  return <AbsoluteFill style={{background:"radial-gradient(circle at 26% 30%,#294D68,#0B1728 58%,#040914)",overflow:"hidden",fontFamily:"Arial,sans-serif"}}>
    <div style={{position:"absolute",inset:-100,backgroundImage:"radial-gradient(circle,rgba(73,222,245,.2) 2px,transparent 3px)",backgroundSize:"58px 58px",translate:`${-frame*.18}px 0`,opacity:.4}}/>
    <div style={{position:"absolute",left:155,bottom:98,width:520,height:55,borderRadius:"50%",background:"rgba(0,0,0,.45)",filter:"blur(18px)",scale:`${1+Math.sin(frame/15)*.025} 1`}}/>
    {!showTurn&&<div style={{position:"absolute",left:115,top:155,width:570,height:700,opacity:pointingOpacity,translate:`${interpolate(enter,[0,1],[-150,0])}px ${interpolate(enter,[0,1],[80,0])+Math.sin(frame/17)*5}px`,scale:frame>=270?.82+pointReturn*.18:1,rotate:`${fingerBeat}deg`}}><Character view="finger" scale={1.14}/></div>}
    {showTurn&&<Turntable/>}
    <div style={{position:"absolute",left:780,right:90,top:260,color:"white",font:"1000 76px/.95 Arial",textShadow:"0 7px 0 rgba(0,0,0,.5)"}}>{title}</div>
    <div style={{position:"absolute",left:780,top:470,color:"#07101A",background:showTurn?"#51E4F5":"#FFD51F",padding:"13px 22px",font:"1000 31px Arial",rotate:"-2deg",boxShadow:"8px 9px 0 rgba(0,0,0,.45)"}}>{showTurn?"KARAKTER DÖNÜŞÜ":"PARMAK + GÖVDE + GİRİŞ + TEPKİ"}</div>
    {[[-35,18,"#51E4F5"],[0,21,"#FFD51F"],[36,24,"#51E4F5"],[72,27,"#FFD51F"]].map(([a,d,c])=><Accent key={String(a)} angle={Number(a)} delay={Number(d)} color={String(c)}/>)}
    {frame>285&&<div style={{position:"absolute",left:620,top:150,color:"#FFD51F",font:"1000 105px Arial",opacity:interpolate(frame,[285,294,330,345],[0,1,1,0],clamp),scale:interpolate(frame,[285,300],[.3,1],{...clamp,easing:Easing.out(Easing.back(1.7))}),rotate:"8deg",textShadow:"0 0 24px rgba(255,213,31,.75)"}}>!</div>}
    <div style={{position:"absolute",left:780,right:120,bottom:135,height:9,borderRadius:9,background:"rgba(255,255,255,.12)"}}><div style={{height:"100%",width:`${frame/360*100}%`,borderRadius:9,background:"linear-gradient(90deg,#51E4F5,#FFD51F)"}}/></div>
  </AbsoluteFill>;
};
