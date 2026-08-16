import React, {useMemo} from "react";
import {
  AbsoluteFill,
  Audio,
  Easing,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import data from "../../public/hidden-designs/data.json";
import {MascotMotion, MascotRigV2} from "./MascotRigV2";

type Chapter={id:string;title:string;startMs:number;endMs:number};
type Word={text:string;startMs:number;endMs:number};
const chapters=data.chapters as Chapter[];
const words=data.words as Word[];
const yellow="#FFD42A";
const cyan="#51DEFF";
const red="#FF3E55";

const visual:Record<string,{file:string;position:string;label:string;fact:string;accent:string;motion:MascotMotion}>={
  fuel:{file:"fuel-gauge.jpg",position:"37% 44%",label:"YAKIT GÖSTERGESİNDEKİ OK",fact:"OK NEREYİ GÖSTERİRSE KAPAK O TARAFTA",accent:yellow,motion:"scan"},
  pen:{file:"pen-holes-v3.png",position:"center",label:"KALEM KAPAĞINDAKİ DELİK",fact:"MÜREKKEP İÇİN DEĞİL • HAVA GEÇİŞİ İÇİN",accent:cyan,motion:"recoil"},
  keyboard:{file:"keyboard-fj-v4.png",position:"center",label:"F VE J TUŞLARINDAKİ ÇIKINTILAR",fact:"PARMAKLARIN KLAVYEDEKİ PUSULASI",accent:red,motion:"write"},
  escalator:{file:"escalator-brush-v2.png",position:"center",label:"YÜRÜYEN MERDİVEN FIRÇASI",fact:"TEMİZLEMEZ • AYAĞINI KENARDAN UZAK TUTAR",accent:yellow,motion:"recoil"},
  airplane:{file:"airplane-bleed-hole-v4.png",position:"center",label:"UÇAK CAMINDAKİ MİNİK DELİK",fact:"KATMANLAR ARASINDAKİ BASINCI DENGELER",accent:cyan,motion:"peek"},
  microwave:{file:"microwave-door.jpg",position:"center",label:"MİKRODALGA KAPAĞINDAKİ AĞ",fact:"IŞIK GEÇER • MİKRODALGA DIŞARIDA KALIR",accent:yellow,motion:"scan"},
  knife:{file:"knife.jpg",position:"center",label:"MAKET BIÇAĞINDAKİ ÇİZGİLER",fact:"HER ÇİZGİ KIRILINCA YENİ BİR UÇ",accent:red,motion:"recoil"},
  tape:{file:"tape-diamond-v2.png",position:"center",label:"MEZURADAKİ SİYAH ELMAS",fact:"19,2 İNÇLİK KİRİŞ ARALIĞINI GÖSTERİR",accent:yellow,motion:"celebrate"},
};

const captions=(now:number)=>{
  const i=words.findIndex(w=>now>=w.startMs&&now<=w.endMs+130);
  if(i<0)return [];
  const start=Math.floor(i/7)*7;
  return words.slice(start,start+7);
};

const Caption:React.FC<{now:number}>=({now})=>{
  const active=useMemo(()=>captions(now),[now]);
  if(!active.length)return null;
  return <div style={{position:"absolute",left:150,right:150,bottom:30,zIndex:60,textAlign:"center",font:"1000 37px/1.2 Arial",textTransform:"uppercase",filter:"drop-shadow(0 4px 0 #000) drop-shadow(0 0 9px #000)"}}>{active.map((w,i)=><React.Fragment key={`${w.startMs}-${w.text}`}><span style={{color:now>=w.startMs&&now<=w.endMs?yellow:"white"}}>{w.text}</span>{i<active.length-1?" ":""}</React.Fragment>)}</div>;
};

const Host:React.FC<{motion:MascotMotion;localMs:number;side?:"left"|"right";scale?:number;durationMs?:number}>=({motion,localMs,side="right",scale=.55,durationMs=2300})=>{
  const {fps}=useVideoConfig();
  const enter=interpolate(localMs,[0,360],[0,1],{extrapolateLeft:"clamp",extrapolateRight:"clamp",easing:Easing.bezier(.16,1,.3,1)});
  const exit=interpolate(localMs,[Math.max(360,durationMs-600),durationMs],[1,0],{extrapolateLeft:"clamp",extrapolateRight:"clamp"});
  const pose=motion==="write"?"marker":motion==="recoil"?"stop":motion==="celebrate"?"thumbs-up":motion==="wave"||motion==="peek"?"present":"pointer";
  return <div style={{position:"absolute",left:side==="left"?-90:1285,top:-95,width:720,height:820,zIndex:35,opacity:Math.min(enter,exit),translate:`${(1-enter)*(side==="left"?-110:110)}px 0`,filter:"drop-shadow(0 24px 30px rgba(0,0,0,.42))"}}><MascotRigV2 leftPose={motion==="celebrate"?"thumbs-up":"present"} rightPose={pose} previousLeftPose="relaxed" previousRightPose="relaxed" mood={motion==="recoil"?"surprise":motion==="celebrate"?"idea":"explain"} motion={motion} actionFrame={Math.max(0,Math.round(localMs/1000*fps))} scale={scale}/></div>;
};

const Hook:React.FC<{now:number}>=({now})=>{
  const local=now;
  const file=local<4900?"fuel-gauge.jpg":local<7000?"pen-holes-v3.png":"escalator-brush-v2.png";
  const motion:MascotMotion=local<3200?"wave":local<7000?"scan":"recoil";
  return <AbsoluteFill style={{background:"#07111E",overflow:"hidden"}}>
    <Img src={staticFile(`hidden-designs/${file}`)} style={{width:"100%",height:"100%",objectFit:"cover",filter:"brightness(.55) contrast(1.08)",scale:1.04+local*.000002}}/>
    <AbsoluteFill style={{background:"linear-gradient(90deg,rgba(4,12,22,.94),rgba(4,12,22,.18) 68%)"}}/>
    <div style={{position:"absolute",left:94,top:128,color:"white",font:"1000 88px/.9 Arial",maxWidth:1050,textShadow:"0 7px 0 #000"}}>HER GÜN<br/>GÖRÜYORSUN.<br/><span style={{color:yellow}}>AMA NEDEN VAR?</span></div>
    <div style={{position:"absolute",left:98,top:505,color:"#07111E",background:cyan,padding:"12px 20px",font:"1000 31px Arial",boxShadow:"9px 10px 0 rgba(0,0,0,.7)"}}>8 GÜNLÜK NESNE • 8 GİZLİ AMAÇ</div>
    <Host motion={motion} localMs={local} scale={.67} durationMs={10450}/>
  </AbsoluteFill>;
};

const IntroBoard:React.FC<{now:number}>=({now})=>{
  const local=now-10450;
  return <AbsoluteFill style={{background:"radial-gradient(circle at 75% 30%,#183C58,#06111E 64%)",overflow:"hidden"}}>
    <div style={{position:"absolute",left:96,top:135,width:1120,bottom:160,border:"7px solid #D6B47A",borderRadius:24,background:"#102722",boxShadow:"0 22px 55px rgba(0,0,0,.5)",padding:"60px 68px",color:"white"}}>
      <div style={{color:cyan,font:"1000 30px Arial",letterSpacing:2}}>STRANGE THINGS LAB</div>
      <div style={{marginTop:28,font:"1000 86px/.92 Arial"}}>NESNELERİN<br/><span style={{color:yellow}}>SAKLI İŞLERİ</span></div>
      <div style={{marginTop:35,font:"800 35px/1.3 Arial",maxWidth:840}}>Dersi uzatmıyoruz. Nesneyi gösterip doğrudan sırrına bakıyoruz.</div>
    </div>
    <Host motion="write" localMs={local} scale={.68} durationMs={10211}/>
  </AbsoluteFill>;
};

const ObjectScene:React.FC<{chapter:Chapter;now:number;index:number}>=({chapter,now,index})=>{
  const cfg=visual[chapter.id];
  const local=now-chapter.startMs;
  const duration=chapter.endMs-chapter.startMs;
  const progress=local/duration;
  const zoom=progress<.48?1.02+progress*.13:1.08+(progress-.48)*.14;
  const factIn=interpolate(progress,[.45,.58],[0,1],{extrapolateLeft:"clamp",extrapolateRight:"clamp",easing:Easing.bezier(.16,1,.3,1)});
  return <AbsoluteFill style={{background:"#081321",overflow:"hidden"}}>
    <Img src={staticFile(`hidden-designs/${cfg.file}`)} style={{width:"100%",height:"100%",objectFit:"cover",objectPosition:cfg.position,scale:zoom,filter:"contrast(1.08) saturate(1.06)"}}/>
    <AbsoluteFill style={{background:progress<.45?"linear-gradient(90deg,rgba(0,0,0,.72),rgba(0,0,0,.02) 70%)":"linear-gradient(0deg,rgba(0,0,0,.58),transparent 42%)"}}/>
    <div style={{position:"absolute",left:55,top:65,color:"#0A1420",background:cfg.accent,padding:"10px 17px",font:"1000 25px Arial",boxShadow:"7px 8px 0 rgba(0,0,0,.65)"}}>{index+1} / 8</div>
    <div style={{position:"absolute",left:55,top:133,maxWidth:1120,color:"white",font:"1000 59px/.96 Arial",textShadow:"0 5px 0 #000",opacity:1-factIn}}>{cfg.label}</div>
    <div style={{position:"absolute",left:70,right:70,bottom:142,opacity:factIn,translate:`0 ${(1-factIn)*35}px`}}><div style={{display:"inline-block",color:"#0A1420",background:cfg.accent,padding:"15px 24px",font:"1000 45px/.98 Arial",boxShadow:"10px 12px 0 rgba(0,0,0,.75)"}}>{cfg.fact}</div></div>
    {local<2800?<Host motion={cfg.motion} localMs={local} side={index%2===0?"right":"left"} durationMs={2800}/>:null}
  </AbsoluteFill>;
};

const Outro:React.FC<{now:number}>=({now})=>{
  const local=now-206512;
  const files=["fuel-gauge.jpg","pen-holes-v3.png","keyboard-fj-v4.png","escalator-brush-v2.png","airplane-bleed-hole-v4.png","microwave-door.jpg","knife.jpg","tape-diamond-v2.png"];
  return <AbsoluteFill style={{background:"#5B97E8",padding:12}}><div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gridTemplateRows:"repeat(2,1fr)",gap:10,height:"100%"}}>{files.map(f=><div key={f} style={{overflow:"hidden",border:"5px solid white"}}><Img src={staticFile(`hidden-designs/${f}`)} style={{width:"100%",height:"100%",objectFit:"cover"}}/></div>)}</div><AbsoluteFill style={{background:"rgba(0,0,0,.56)"}}/><div style={{position:"absolute",left:380,right:100,top:235,textAlign:"center",color:"white",font:"1000 75px/.95 Arial",textShadow:"0 6px 0 #000"}}>HANGİSİNİ<br/>İLK KEZ DUYDUN?</div><div style={{position:"absolute",left:600,top:520,color:"#07111E",background:yellow,padding:"17px 28px",font:"1000 44px Arial",boxShadow:"10px 12px 0 #07111E"}}>YORUMA NUMARASINI YAZ</div><div style={{position:"absolute",left:-65,top:-85}}><MascotRigV2 leftPose="present" rightPose="thumbs-up" mood="idea" motion="celebrate" actionFrame={Math.max(0,Math.round(local*.03))} scale={.64}/></div></AbsoluteFill>;
};

export const ReferenceStyleV3:React.FC=()=>{
  const frame=useCurrentFrame();
  const {fps}=useVideoConfig();
  const now=frame/fps*1000;
  const chapter=chapters.find(c=>now>=c.startMs&&now<c.endMs)??chapters[chapters.length-1];
  const objectChapters=chapters.filter(c=>visual[c.id]);
  const index=objectChapters.findIndex(c=>c.id===chapter.id);
  return <AbsoluteFill style={{background:"#081321",fontFamily:"Arial,sans-serif"}}>
    {now<10450?<Hook now={now}/>:now<20661?<IntroBoard now={now}/>:chapter.id==="outro"?<Outro now={now}/>:<ObjectScene chapter={chapter} now={now} index={index}/>} 
    <div style={{position:"absolute",left:28,top:24,zIndex:70,color:"white",font:"900 18px Arial",letterSpacing:1.4,textShadow:"0 2px 6px #000"}}>STRANGE THINGS LAB</div>
    <Caption now={now}/>
    <Audio src={staticFile("hidden-designs/narration.mp3")}/>
    <Audio src={staticFile("hidden-designs/music-v2-future-tech.mp3")} volume={f=>interpolate(f,[0,45,300,360,6460,6596],[0,.072,.072,.052,.052,0],{extrapolateLeft:"clamp",extrapolateRight:"clamp"})}/>
  </AbsoluteFill>;
};
