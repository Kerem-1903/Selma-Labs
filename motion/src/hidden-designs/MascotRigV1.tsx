import React from "react";
import {Img,interpolate,staticFile,useCurrentFrame,useVideoConfig} from "remotion";

export type HandGesture="point-up"|"point-right"|"palm-stop"|"palm-up"|"fist"|"thumbs-up"|"pinch"|"marker"|"pointer"|"surprise"|"neutral"|"present";
type Mood="neutral"|"talk"|"idea"|"surprise";
const file=(name:string)=>staticFile(`hidden-designs/maskot-rig-v1/${name}.png`);

const Hand:React.FC<{gesture:HandGesture;side:"left"|"right";rotate:number;x:number;y:number;scale?:number}>=({gesture,side,rotate,x,y,scale=1})=>{
  const actual=gesture==="neutral"?"hand-neutral":gesture==="present"?"hand-present":`hand-${gesture}`;
  return <Img src={file(actual)} style={{position:"absolute",left:x,top:y,width:240,height:300,objectFit:"contain",rotate:`${rotate}deg`,scale:`${side==="left"?-scale:scale} ${scale}`,filter:"drop-shadow(0 16px 16px rgba(0,0,0,.28))",transformOrigin:"center center",zIndex:8}}/>;
};

export const MascotRigV1:React.FC<{leftGesture?:HandGesture;rightGesture?:HandGesture;mood?:Mood;scale?:number;enter?:number}>=({leftGesture="present",rightGesture="point-up",mood="idea",scale=1,enter=1})=>{
  const frame=useCurrentFrame();const {fps}=useVideoConfig();
  const bob=Math.sin(frame/fps*Math.PI*1.7)*7;
  const talk=Math.sin(frame/fps*Math.PI*3.4);
  const idea=Math.max(0,Math.sin(frame/fps*Math.PI*2.1));
  const surprise=mood==="surprise"?Math.abs(Math.sin(frame/fps*Math.PI*3))*9:0;
  const headTilt=mood==="idea"?-5-idea*2:mood==="surprise"?talk*4:talk*1.5;
  const leftArmRot=mood==="talk"?8+talk*7:mood==="surprise"?-18-talk*6:4+talk*2;
  const rightArmRot=mood==="idea"?-16-idea*7:mood==="surprise"?18+talk*6:-5-talk*3;
  const glow=.9+Math.sin(frame/fps*Math.PI*2.4)*.12;
  const orbitX=Math.cos(frame/fps*Math.PI*.9)*30;
  const orbitY=Math.sin(frame/fps*Math.PI*.9)*18;
  return <div style={{position:"relative",width:720,height:820,scale:scale*enter,translate:`0 ${bob-surprise}px`,transformOrigin:"center bottom"}}>
    <Img src={file("hover-ring")} style={{position:"absolute",left:220,top:700,width:280,height:59,objectFit:"contain",scale:`${1+Math.sin(frame/11)*.05} ${.85+Math.sin(frame/11)*.02}`,opacity:.88,filter:`brightness(${glow}) drop-shadow(0 0 15px rgba(81,228,245,.5))`}}/>
    <Img src={file("torso")} style={{position:"absolute",left:225,top:405,width:270,height:253,objectFit:"contain",scale:`${1+talk*.008} 1`,filter:"drop-shadow(0 25px 25px rgba(0,0,0,.3))",zIndex:4}}/>
    <Img src={file("arm-cyan")} style={{position:"absolute",left:105,top:365,width:175,height:289,objectFit:"contain",rotate:`${leftArmRot}deg`,scale:`1 ${1+talk*.025}`,transformOrigin:"right top",filter:`brightness(${glow}) drop-shadow(0 0 12px rgba(81,228,245,.45))`,zIndex:3}}/>
    <Img src={file("arm-yellow")} style={{position:"absolute",left:440,top:365,width:175,height:290,objectFit:"contain",rotate:`${rightArmRot}deg`,scale:`1 ${1-talk*.025}`,transformOrigin:"left top",filter:`brightness(${glow}) drop-shadow(0 0 12px rgba(255,213,31,.4))`,zIndex:3}}/>
    <Img src={file("collar")} style={{position:"absolute",left:175,top:315,width:370,height:165,objectFit:"contain",zIndex:6,filter:"drop-shadow(0 14px 14px rgba(0,0,0,.22))"}}/>
    <Img src={file("head-front")} style={{position:"absolute",left:219,top:78,width:282,height:281,objectFit:"contain",rotate:`${headTilt}deg`,transformOrigin:"center bottom",filter:`brightness(${glow}) drop-shadow(0 18px 20px rgba(0,0,0,.3))`,zIndex:7}}/>
    <Hand gesture={leftGesture} side="left" x={-50} y={435+talk*5} rotate={-14+leftArmRot*.55} scale={.88}/>
    <Hand gesture={rightGesture} side="right" x={530} y={415-talk*6-idea*10} rotate={10+rightArmRot*.5} scale={.88}/>
    <Img src={file("particle-cyan")} style={{position:"absolute",left:75+orbitX,top:285+orbitY,width:88,height:96,objectFit:"contain",scale:`${.9+idea*.16}`,filter:"drop-shadow(0 0 12px #51E4F5)",zIndex:9}}/>
    <Img src={file("particle-yellow")} style={{position:"absolute",right:55-orbitX,top:245-orbitY,width:90,height:90,objectFit:"contain",scale:`${.9+idea*.16}`,filter:"drop-shadow(0 0 12px #FFD51F)",zIndex:9}}/>
    {mood==="surprise"&&<Img src={file("accent")} style={{position:"absolute",right:48,top:70,width:120,height:106,objectFit:"contain",scale:`${.8+idea*.35}`,zIndex:10}}/>}
  </div>;
};
