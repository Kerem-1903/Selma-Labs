import React from "react";
import {AbsoluteFill, Img, staticFile} from "remotion";

export const InternetOutageThumbnail: React.FC = () => <AbsoluteFill style={{background:"#050b14",overflow:"hidden",fontFamily:"Arial,sans-serif"}}>
  <Img src={staticFile("internet-outage/istanbul-network-outage.png")} style={{width:"100%",height:"100%",objectFit:"cover",scale:1.04}}/>
  <AbsoluteFill style={{background:"linear-gradient(90deg,rgba(2,7,14,.98) 0%,rgba(2,7,14,.84) 48%,rgba(2,7,14,.16) 76%),linear-gradient(180deg,rgba(0,0,0,.08),rgba(0,0,0,.55))"}}/>
  <div style={{position:"absolute",left:56,top:68,width:720,color:"white",font:"1000 102px/.88 Arial",letterSpacing:-4,textShadow:"0 9px 28px #000"}}>24 SAAT<br/><span style={{color:"#ff3d5f"}}>İNTERNET</span><br/>YOK</div>
  <div style={{position:"absolute",right:106,top:82,width:340,height:560,borderRadius:52,background:"linear-gradient(145deg,#202936,#05080e)",border:"13px solid #05070a",boxShadow:"0 25px 55px rgba(0,0,0,.72),0 0 0 4px rgba(255,255,255,.22)",rotate:"7deg"}}>
    <div style={{position:"absolute",left:85,top:13,width:145,height:19,borderRadius:12,background:"#030406"}}/>
    <div style={{position:"absolute",inset:22,borderRadius:34,background:"radial-gradient(circle at 55% 32%,#17344c,#07101a 65%)",display:"grid",placeItems:"center"}}>
      <div style={{position:"relative",width:170,height:170,borderRadius:"50%",border:"13px solid #ff3d5f",boxShadow:"0 0 30px rgba(255,61,95,.6)"}}><div style={{position:"absolute",left:69,top:-24,width:25,height:192,background:"#ff3d5f",rotate:"-45deg",boxShadow:"0 0 15px rgba(255,61,95,.55)"}}/></div>
      <div style={{position:"absolute",left:0,right:0,bottom:92,textAlign:"center",color:"white",font:"1000 30px Arial",letterSpacing:1}}>BAĞLANTI YOK</div>
    </div>
  </div>
  <div style={{position:"absolute",right:410,top:78,width:0,height:0,borderLeft:"70px solid transparent",borderRight:"70px solid transparent",borderBottom:"125px solid #ff3d5f",filter:"drop-shadow(0 10px 18px rgba(0,0,0,.65))",rotate:"-10deg"}}><div style={{position:"absolute",left:-8,top:48,color:"white",font:"1000 66px Arial"}}>!</div></div>
</AbsoluteFill>;
