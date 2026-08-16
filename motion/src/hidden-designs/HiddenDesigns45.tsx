import React, {useMemo} from "react";
import {AbsoluteFill, Audio, Easing, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig} from "remotion";
import data from "../../public/hidden-designs-45/data.json";
import {MascotMotion, MascotRigV2} from "./MascotRigV2";

type Chapter={id:string;title:string;icon:string;fact:string;startMs:number;endMs:number};
type Word={text:string;startMs:number;endMs:number};
const chapters=data.chapters as Chapter[];
const words=data.words as Word[];
const accents=["#FFD42A","#4CDEFF","#FF5268","#86F2A4"];
const motions:MascotMotion[]=["wave","scan","write","recoil","peek","celebrate"];

const palette=(index:number)=>{
  const hues=[[206,247],[252,276],[155,205],[12,42],[322,354]];
  const [a,b]=hues[index%hues.length];
  return `radial-gradient(circle at 78% 28%,hsla(${b},75%,42%,.46),transparent 37%),linear-gradient(135deg,hsl(${a} 54% 11%),hsl(${b} 47% 18%))`;
};

const captionWords=(now:number)=>{
  const i=words.findIndex(w=>now>=w.startMs&&now<=w.endMs+120);
  if(i<0)return [];
  return words.slice(Math.floor(i/7)*7,Math.floor(i/7)*7+7);
};

const Captions:React.FC<{now:number}>=({now})=>{
  const active=useMemo(()=>captionWords(now),[now]);
  if(!active.length)return null;
  return <div style={{position:"absolute",left:105,right:105,bottom:30,zIndex:80,textAlign:"center",font:"1000 39px/1.16 Arial",textTransform:"uppercase",filter:"drop-shadow(0 4px 0 #000) drop-shadow(0 0 10px #000)"}}>{active.map((w,i)=><React.Fragment key={`${w.startMs}-${i}`}><span style={{color:now>=w.startMs&&now<=w.endMs?"#FFD42A":"white"}}>{w.text}</span>{i<active.length-1?" ":""}</React.Fragment>)}</div>;
};

const Host:React.FC<{index:number;local:number;duration:number}>=({index,local,duration})=>{
  if(index%4!==0&&local>2500)return null;
  const enter=interpolate(local,[0,330],[0,1],{extrapolateLeft:"clamp",extrapolateRight:"clamp",easing:Easing.bezier(.16,1,.3,1)});
  const exit=interpolate(local,[Math.min(2500,duration-650),Math.min(3100,duration)],[1,0],{extrapolateLeft:"clamp",extrapolateRight:"clamp"});
  const motion=motions[index%motions.length];
  const rightPose=motion==="write"?"marker":motion==="recoil"?"stop":motion==="celebrate"?"thumbs-up":motion==="wave"||motion==="peek"?"present":"pointer";
  return <div style={{position:"absolute",left:1325,top:130,width:620,height:710,zIndex:45,opacity:Math.min(enter,exit),translate:`${(1-enter)*120}px 0`,filter:"drop-shadow(0 24px 28px rgba(0,0,0,.45))"}}><MascotRigV2 leftPose={motion==="celebrate"?"thumbs-up":"present"} rightPose={rightPose} mood={motion==="recoil"?"surprise":motion==="celebrate"?"idea":"explain"} motion={motion} actionFrame={Math.max(0,Math.round(local*.03))} scale={.5}/></div>;
};

const Intro:React.FC<{chapter:Chapter;now:number}>=({chapter,now})=>{
  const local=now-chapter.startMs;
  const bounce=1+Math.sin(local/210)*.025;
  return <AbsoluteFill style={{background:palette(0),overflow:"hidden"}}>
    <div style={{position:"absolute",left:95,top:125,color:"white",font:"1000 92px/.9 Arial",maxWidth:1120,textShadow:"0 7px 0 #000"}}>HER GÜN<br/>GÖRÜYORSUN.<br/><span style={{color:"#FFD42A"}}>AMA NEDEN VAR?</span></div>
    <div style={{position:"absolute",left:100,top:520,background:"#4CDEFF",color:"#07111E",padding:"13px 22px",font:"1000 38px Arial",boxShadow:"10px 11px 0 #000"}}>45 NESNE • 45 GİZLİ AMAÇ</div>
    <div style={{position:"absolute",right:130,top:110,fontSize:260,scale:bounce,filter:"drop-shadow(0 20px 22px #000)"}}>✨</div>
    <Host index={0} local={local} duration={chapter.endMs-chapter.startMs}/>
  </AbsoluteFill>;
};

const Item:React.FC<{chapter:Chapter;now:number;index:number}>=({chapter,now,index})=>{
  const local=now-chapter.startMs;
  const duration=chapter.endMs-chapter.startMs;
  const progress=local/duration;
  const accent=accents[index%accents.length];
  const factIn=interpolate(progress,[.37,.55],[0,1],{extrapolateLeft:"clamp",extrapolateRight:"clamp",easing:Easing.bezier(.16,1,.3,1)});
  return <AbsoluteFill style={{background:palette(index),overflow:"hidden"}}>
    <Img src={staticFile(`hidden-designs-45/item-${String(index).padStart(2,"0")}.jpg`)} style={{position:"absolute",inset:0,width:"100%",height:"100%",objectFit:"cover",scale:1.03+progress*.07,filter:"contrast(1.08) saturate(1.06) brightness(.68)"}}/>
    <AbsoluteFill style={{background:"linear-gradient(90deg,rgba(4,10,20,.92),rgba(4,10,20,.23) 67%),linear-gradient(0deg,rgba(4,10,20,.72),transparent 48%)"}}/>
    <div style={{position:"absolute",left:0,top:0,bottom:0,width:18,background:accent,opacity:.9}}/>
    <div style={{position:"absolute",left:55,top:62,color:"#07111E",background:accent,padding:"10px 18px",font:"1000 28px Arial",boxShadow:"8px 9px 0 #000"}}>{index} / 45</div>
    <div style={{position:"absolute",left:80,top:168,maxWidth:1120,color:"white",font:"1000 72px/.92 Arial",textShadow:"0 6px 0 #000",opacity:1-factIn,translate:`${-factIn*35}px 0`}}>{chapter.title.toUpperCase()}</div>
    <div style={{position:"absolute",right:95,top:78,fontSize:102,scale:1.01+Math.sin(local/230)*.035,rotate:`${Math.sin(local/390)*3}deg`,filter:"drop-shadow(0 12px 14px rgba(0,0,0,.6))"}}>{chapter.icon}</div>
    <div style={{position:"absolute",left:78,right:78,bottom:145,opacity:factIn,translate:`0 ${(1-factIn)*35}px`}}><div style={{display:"inline-block",maxWidth:1430,color:"#07111E",background:accent,padding:"17px 25px",font:"1000 50px/.98 Arial",boxShadow:"11px 13px 0 #000"}}>{chapter.fact.toUpperCase()}</div></div>
    <Host index={index} local={local} duration={duration}/>
  </AbsoluteFill>;
};

const Outro:React.FC<{chapter:Chapter;now:number}>=({chapter,now})=>{
  const local=now-chapter.startMs;
  return <AbsoluteFill style={{background:palette(3),overflow:"hidden"}}><div style={{position:"absolute",left:440,right:85,top:210,textAlign:"center",color:"white",font:"1000 87px/.95 Arial",textShadow:"0 7px 0 #000"}}>KAÇ TANESİNİ<br/><span style={{color:"#FFD42A"}}>BİLİYORDUN?</span></div><div style={{position:"absolute",left:650,top:520,color:"#07111E",background:"#4CDEFF",padding:"17px 28px",font:"1000 45px Arial",boxShadow:"10px 12px 0 #000"}}>YORUMLARA SAYINI YAZ</div><div style={{position:"absolute",left:-55,top:-72}}><MascotRigV2 leftPose="present" rightPose="thumbs-up" mood="idea" motion="celebrate" actionFrame={Math.round(local*.03)} scale={.66}/></div></AbsoluteFill>;
};

export const HiddenDesigns45:React.FC=()=>{
  const frame=useCurrentFrame();
  const {fps}=useVideoConfig();
  const now=frame/fps*1000;
  const chapter=chapters.find(c=>now>=c.startMs&&now<c.endMs)??chapters[chapters.length-1];
  const index=chapters.findIndex(c=>c.id===chapter.id);
  return <AbsoluteFill style={{fontFamily:"Arial,sans-serif",background:"#07111E"}}>
    {chapter.id==="intro"?<Intro chapter={chapter} now={now}/>:chapter.id==="outro"?<Outro chapter={chapter} now={now}/>:<Item chapter={chapter} now={now} index={index}/>} 
    <div style={{position:"absolute",left:28,top:24,zIndex:90,color:"white",font:"900 18px Arial",letterSpacing:1.4,textShadow:"0 2px 6px #000"}}>STRANGE THINGS LAB</div>
    <Captions now={now}/>
    <Audio src={staticFile("hidden-designs-45/narration.mp3")}/>
    <Audio src={staticFile("hidden-designs/music-v2-future-tech.mp3")} volume={f=>interpolate(f,[0,45,300,360,14950,15080],[0,.06,.06,.045,.045,0],{extrapolateLeft:"clamp",extrapolateRight:"clamp"})}/>
  </AbsoluteFill>;
};
