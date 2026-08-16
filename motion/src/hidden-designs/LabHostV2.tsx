import React from "react";
import {Easing, interpolate, spring, useCurrentFrame, useVideoConfig} from "remotion";

type Pose = "idea" | "explain" | "point" | "surprise";

const clamp = {extrapolateLeft: "clamp" as const, extrapolateRight: "clamp" as const};

const ExpressiveHead: React.FC<{expression: Pose; size?: number}> = ({expression, size = 250}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const blinkPhase = frame % Math.round(fps * 4.4);
  const blink = blinkPhase > fps * 4.15 ? interpolate(blinkPhase, [fps * 4.15, fps * 4.28, fps * 4.4], [1, .18, 1], clamp) : 1;
  const pulse = 1 + Math.sin(frame / fps * Math.PI * 2.1) * .025;
  const shapes: Record<Pose, {cyan: string; yellow: string}> = {
    idea: {cyan: "M18 63 A39 39 0 0 1 73 17", yellow: "M82 37 A39 39 0 0 1 27 84"},
    explain: {cyan: "M18 59 A38 38 0 0 1 73 18", yellow: "M82 40 A38 38 0 0 1 28 82"},
    point: {cyan: "M19 67 A42 42 0 0 1 74 15", yellow: "M82 36 A36 36 0 0 1 30 83"},
    surprise: {cyan: "M24 42 A30 30 0 0 1 67 18", yellow: "M78 51 A28 28 0 0 1 42 80"},
  };
  return <svg width={size} height={size} viewBox="0 0 100 100" style={{overflow:"visible",scale:pulse}}>
    <defs>
      <radialGradient id="host-core" cx="42%" cy="35%" r="70%"><stop offset="0" stopColor="#1E304A"/><stop offset=".68" stopColor="#09111F"/><stop offset="1" stopColor="#02060D"/></radialGradient>
      <filter id="host-glow" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="2.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    </defs>
    <circle cx="50" cy="50" r="46" fill="url(#host-core)" stroke="#253A50" strokeWidth="3"/>
    <circle cx="50" cy="50" r="41.5" fill="none" stroke="rgba(255,255,255,.08)"/>
    <path d={shapes[expression].cyan} fill="none" stroke="#2AD4EE" strokeLinecap="round" strokeWidth={5 * blink} filter="url(#host-glow)"/>
    <path d={shapes[expression].yellow} fill="none" stroke="#FFD51F" strokeLinecap="round" strokeWidth={4.6 * blink} filter="url(#host-glow)"/>
    <text x="50" y="62" fill="white" fontFamily="Arial Black,Arial" fontWeight="900" fontSize="32" letterSpacing="-3" textAnchor="middle">ST</text>
  </svg>;
};

const Arm: React.FC<{side: "left" | "right"; angle: number; raisedFinger?: boolean; handRotation?: number}> = ({side, angle, raisedFinger, handRotation = 0}) => {
  const mirror = side === "left";
  return <div style={{position:"absolute",left:mirror?70:300,top:310,width:72,height:265,rotate:`${angle}deg`,transformOrigin:"36px 26px",zIndex:mirror?2:7}}>
    <div style={{position:"absolute",left:5,top:0,width:62,height:172,borderRadius:34,background:"linear-gradient(90deg,#CFD9E6,#FFFFFF 48%,#C4D0DE)",border:"6px solid #101B2B"}}/>
    <div style={{position:"absolute",left:12,top:155,width:49,height:35,borderRadius:16,background:"#101B2B",border:"5px solid #263B50"}}/>
    <div style={{position:"absolute",left:9,top:178,width:58,height:62,borderRadius:"45%",background:"#121F31",border:"6px solid #07101D",rotate:`${handRotation}deg`}}>
      {raisedFinger&&<div style={{position:"absolute",left:18,top:-64,width:25,height:82,borderRadius:16,background:"#121F31",border:"6px solid #07101D"}}/>}
    </div>
  </div>;
};

export const LabHostV2: React.FC<{pose?: Pose; scale?: number; enterAt?: number}> = ({pose="idea",scale=1,enterAt=0}) => {
  const frame=useCurrentFrame();
  const {fps}=useVideoConfig();
  const local=frame-enterAt;
  const entrance=spring({frame:local,fps,config:{damping:12,stiffness:130,mass:.7}});
  const bob=Math.sin(frame/fps*Math.PI*2)*5;
  const bodyBreath=1+Math.sin(frame/fps*Math.PI*1.5)*.012;
  const headTilt=pose==="idea"?-7:pose==="surprise"?interpolate(Math.sin(frame/fps*Math.PI*3),[-1,1],[-4,4]):pose==="point"?5:-2;
  const fingerBeat=pose==="idea"?Math.max(0,Math.sin((frame/fps)*Math.PI*2.6))*6:0;
  const rightAngle=pose==="idea"?-34-fingerBeat:pose==="point"?-68:pose==="surprise"?-110:-46;
  const leftAngle=pose==="surprise"?105:pose==="explain"?32:10;
  return <div style={{position:"absolute",width:500,height:820,left:80,bottom:35,scale:scale*(.7+entrance*.3),translate:`${interpolate(entrance,[0,1],[-120,0])}px ${bob+interpolate(entrance,[0,1],[100,0])}px`,opacity:interpolate(entrance,[0,.2],[0,1],clamp),transformOrigin:"bottom center"}}>
    <div style={{position:"absolute",left:144,top:10,zIndex:10,rotate:`${headTilt}deg`,transformOrigin:"125px 125px"}}><ExpressiveHead expression={pose}/></div>
    <div style={{position:"absolute",left:205,top:232,width:128,height:60,borderRadius:"0 0 28px 28px",background:"#111D2D",border:"5px solid #07101D",zIndex:4}}/>
    <Arm side="left" angle={leftAngle}/>
    <Arm side="right" angle={rightAngle} raisedFinger={pose==="idea"} handRotation={pose==="point"?-22:0}/>
    <div style={{position:"absolute",left:137,top:270,width:245,height:390,zIndex:5,scale:`${bodyBreath} 1`,transformOrigin:"center bottom"}}>
      <div style={{position:"absolute",left:34,top:15,width:180,height:330,clipPath:"polygon(35% 0,65% 0,100% 100%,0 100%)",background:"linear-gradient(90deg,#102136,#1E3853 52%,#0C1929)",border:"6px solid #091321"}}/>
      <div style={{position:"absolute",left:0,top:0,width:245,height:340,clipPath:"polygon(18% 0,38% 0,43% 17%,57% 17%,62% 0,82% 0,100% 18%,88% 100%,12% 100%,0 18%)",background:"linear-gradient(100deg,#D3DDE9,#FFFFFF 48%,#C8D3DF)",border:"6px solid #101B2B"}}/>
      <div style={{position:"absolute",left:72,top:37,width:102,height:275,clipPath:"polygon(36% 0,64% 0,100% 100%,0 100%)",background:"linear-gradient(90deg,#12243A,#234463,#0D1B2E)",border:"5px solid #0B1523"}}/>
      <div style={{position:"absolute",left:111,top:55,width:24,height:24,borderRadius:"50%",background:"#51E4F5",boxShadow:"0 0 22px #32DFF2"}}/>
      <div style={{position:"absolute",left:16,top:12,width:66,height:14,borderRadius:9,background:"rgba(255,255,255,.5)",rotate:"-22deg"}}/>
    </div>
    <div style={{position:"absolute",left:162,top:640,width:76,height:108,borderRadius:"20px 20px 34px 34px",background:"#E6ECF3",border:"6px solid #101B2B",zIndex:3}}/>
    <div style={{position:"absolute",left:287,top:640,width:76,height:108,borderRadius:"20px 20px 34px 34px",background:"#E6ECF3",border:"6px solid #101B2B",zIndex:3}}/>
    <div style={{position:"absolute",left:137,top:724,width:115,height:54,borderRadius:"34px 20px 17px 17px",background:"#111D2D",border:"6px solid #07101D",zIndex:8}}/>
    <div style={{position:"absolute",left:273,top:724,width:115,height:54,borderRadius:"20px 34px 17px 17px",background:"#111D2D",border:"6px solid #07101D",zIndex:8}}/>
  </div>;
};
