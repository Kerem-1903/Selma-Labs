import React from "react";
import {AbsoluteFill, Img, staticFile} from "remotion";

export const HiddenDesignsThumbnail: React.FC = () => (
  <AbsoluteFill style={{background:"#5B97E8",fontFamily:"Arial,sans-serif",overflow:"hidden"}}>
    <div style={{position:"absolute",left:0,top:0,bottom:0,width:790,overflow:"hidden",borderRight:"12px solid white"}}>
      <Img src={staticFile("hidden-designs/fuel-gauge.jpg")} style={{width:"100%",height:"100%",objectFit:"cover",objectPosition:"38% 45%",transform:"scale(1.23)",filter:"contrast(1.12) saturate(1.12)"}}/>
      <div style={{position:"absolute",left:270,top:235,width:155,height:155,border:"14px solid #FFD42A",borderRadius:"50%",boxShadow:"0 0 25px rgba(0,0,0,.5)"}}/>
      <div style={{position:"absolute",left:400,top:190,color:"#111",background:"#FFD42A",padding:"9px 16px",font:"1000 35px Arial",transform:"rotate(-3deg)"}}>BU OK!</div>
    </div>
    <div style={{position:"absolute",left:790,right:0,top:0,bottom:0,background:"#162235"}}/>
    <div style={{position:"absolute",left:835,top:65,color:"#111",background:"#FF4055",padding:"9px 17px",font:"1000 30px Arial",transform:"rotate(-2deg)"}}>GİZLİ AMAÇLARI</div>
    <div style={{position:"absolute",left:835,top:150,right:34,color:"white",font:"1000 65px/.94 Arial",textShadow:"0 6px 0 rgba(0,0,0,.55)"}}>HER GÜN<br/>GÖRÜYORSUN…</div>
    <div style={{position:"absolute",left:835,top:390,right:36,color:"#FFD42A",font:"1000 72px/.93 Arial",textShadow:"0 6px 0 rgba(0,0,0,.55)"}}>AMA NEDEN<br/>VARLAR?</div>
    <div style={{position:"absolute",left:835,bottom:45,color:"white",font:"900 28px Arial"}}>8 ŞAŞIRTICI TASARIM</div>
  </AbsoluteFill>
);
