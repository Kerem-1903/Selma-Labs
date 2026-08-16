import React from "react";
import {AbsoluteFill,Easing,Img,interpolate,spring,staticFile,useCurrentFrame,useVideoConfig} from "remotion";

type Pose="hero"|"front"|"side"|"back"|"explain"|"surprise";
const crops:Record<Pose,{x:number;y:number;w:number;h:number}>={
  hero:{x:55,y:10,w:525,h:565},front:{x:590,y:100,w:450,h:455},side:{x:1035,y:85,w:390,h:470},
  back:{x:80,y:570,w:430,h:445},explain:{x:500,y:560,w:525,h:460},surprise:{x:990,y:550,w:520,h:470},
};
const clamp={extrapolateLeft:"clamp" as const,extrapolateRight:"clamp" as const};

const Sprite:React.FC<{pose:Pose;opacity?:number;scale?:number;x?:number;y?:number;rotate?:number}>=({pose,opacity=1,scale=1,x=0,y=0,rotate=0})=>{
  const c=crops[pose];
  return <div style={{position:"absolute",width:c.w,height:c.h,overflow:"hidden",opacity,scale,translate:`${x}px ${y}px`,rotate:`${rotate}deg`,transformOrigin:"center bottom",filter:"drop-shadow(0 35px 30px rgba(0,0,0,.38))"}}><Img src={staticFile("hidden-designs/maskot-final-v5-alpha.png")} style={{position:"absolute",left:-c.x,top:-c.y,width:1536,height:1024,maxWidth:"none"}}/></div>;
};

const Pulse:React.FC<{x:number;y:number;color:string;delay:number}>=({x,y,color,delay})=>{const frame=useCurrentFrame();const p=interpolate(frame,[delay,delay+9,delay+30],[0,1,0],clamp);return <div style={{position:"absolute",left:x,top:y,width:24,height:24,borderRadius:"50%",border:`6px solid ${color}`,opacity:p,scale:interpolate(p,[0,1],[.4,2.2]),boxShadow:`0 0 18px ${color}`}}/>};

export const MascotFinalV5Demo:React.FC=()=>{
  const frame=useCurrentFrame();const {fps}=useVideoConfig();
  const enter=spring({frame,fps,config:{damping:10,stiffness:120,mass:.8}});
  const phase=frame<120?"hero":frame<235?"turn":frame<335?"explain":"surprise";
  const float=Math.sin(frame/14)*8;
  const pointBounce=Math.max(0,Math.sin(frame/8))*2.2;
  const turnLocal=frame-120;const turnPoses:Pose[]=["front","side","back","side","front"];const ti=Math.min(4,Math.max(0,Math.floor(turnLocal/23)));const tn=Math.min(4,ti+1);const mix=interpolate(turnLocal-ti*23,[12,23],[0,1],clamp);
  const explainIn=spring({frame:frame-235,fps,config:{damping:11,stiffness:140}});const surprise=spring({frame:frame-335,fps,config:{damping:7,stiffness:180}});
  const title=phase==="hero"?"BİR ŞEY FARK ETTİN Mİ?":phase==="turn"?"HER AÇIDAN AYNI KARAKTER":phase==="explain"?"ANLATIRKEN HEP CANLI":"VE TEPKİ VERİYOR!";
  return <AbsoluteFill style={{background:"radial-gradient(circle at 25% 25%,#244A65,#0B1728 58%,#030812)",fontFamily:"Arial,sans-serif",overflow:"hidden"}}>
    <div style={{position:"absolute",inset:-120,backgroundImage:"radial-gradient(circle,rgba(54,223,244,.2) 2px,transparent 3px)",backgroundSize:"58px 58px",translate:`${-frame*.22}px ${Math.sin(frame/25)*12}px`,opacity:.36}}/>
    <div style={{position:"absolute",left:130,bottom:115,width:565,height:52,borderRadius:"50%",background:"rgba(0,0,0,.38)",filter:"blur(18px)",scale:`${1+Math.sin(frame/12)*.04} 1`}}/>
    <div style={{position:"absolute",left:100,top:175,width:640,height:690}}>
      {phase==="hero"&&<Sprite pose="hero" scale={1.08+pointBounce*.006} x={interpolate(enter,[0,1],[-150,0])} y={interpolate(enter,[0,1],[90,0])+float} rotate={interpolate(enter,[0,1],[-8,0])}/>} 
      {phase==="turn"&&<><Sprite pose={turnPoses[ti]} opacity={1-mix} scale={1.12} x={turnPoses[ti]==="side"?80:30} y={float}/><Sprite pose={turnPoses[tn]} opacity={mix} scale={1.12} x={turnPoses[tn]==="side"?80:30} y={float}/></>}
      {phase==="explain"&&<Sprite pose="explain" scale={.86+explainIn*.2} x={20} y={float+interpolate(explainIn,[0,1],[70,0])} rotate={Math.sin(frame/16)*1.5}/>} 
      {phase==="surprise"&&<Sprite pose="surprise" scale={.9+surprise*.16} x={15} y={float+interpolate(surprise,[0,1],[100,-18])} rotate={Math.sin(frame/7)*1.3}/>} 
    </div>
    <div style={{position:"absolute",left:790,right:80,top:265,color:"white",font:"1000 72px/.96 Arial",textShadow:"0 7px 0 rgba(0,0,0,.48)"}}>{title}</div>
    <div style={{position:"absolute",left:790,top:485,color:"#06101B",background:phase==="surprise"?"#FF5364":phase==="turn"?"#51E4F5":"#FFD51F",padding:"13px 22px",font:"1000 30px Arial",rotate:"-2deg",boxShadow:"9px 10px 0 rgba(0,0,0,.45)"}}>{phase==="hero"?"PARMAK VURGUSU":phase==="turn"?"ÖN • YAN • ARKA":phase==="explain"?"ELLER + ENERJİ + PARÇACIK":"SIÇRAMA + NABIZ + IŞIK"}</div>
    {[0,1,2,3,4,5].map(i=><Pulse key={i} x={560+Math.cos(i)*105} y={130+Math.sin(i*1.8)*92} color={i%2?"#FFD51F":"#51E4F5"} delay={16+i*4}/>) }
    {phase==="surprise"&&<div style={{position:"absolute",left:640,top:90,color:"#FFD51F",font:"1000 110px Arial",opacity:interpolate(frame,[337,345,395,415],[0,1,1,0],clamp),scale:interpolate(frame,[337,350],[.25,1],{...clamp,easing:Easing.out(Easing.back(1.7))}),rotate:"8deg",textShadow:"0 0 25px rgba(255,213,31,.8)"}}>!</div>}
    <div style={{position:"absolute",left:790,right:110,bottom:125,height:9,borderRadius:9,background:"rgba(255,255,255,.12)"}}><div style={{height:"100%",width:`${frame/420*100}%`,background:"linear-gradient(90deg,#51E4F5,#FFD51F,#FF5364)",borderRadius:9}}/></div>
  </AbsoluteFill>;
};
