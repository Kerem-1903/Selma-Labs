import React from "react";
import {Audio} from "@remotion/media";
import {AbsoluteFill, Easing, Interactive, interpolate, Sequence, Series, staticFile, useCurrentFrame, useVideoConfig} from "remotion";
import {phantomCaptions} from "./captions";
import {FootageScene} from "./FootageScene";
import {PhantomCaptions} from "./PhantomCaptions";

const yellow = "#FFD52A";
const cyan = "#66E8F2";

const AlertCard: React.FC = () => {
  const frame = useCurrentFrame();
  return <Interactive.Div name="Boş bildirim kartı" style={{position: "absolute", top: 310, left: 95, right: 95, padding: "34px 38px", borderRadius: 32, background: "rgba(248,250,255,.96)", color: "#101725", boxShadow: "0 30px 80px rgba(0,0,0,.55)", translate: `0 ${interpolate(frame,[0,12],[-55,0],{extrapolateRight:"clamp",easing:Easing.bezier(.16,1,.3,1)})}px`}}>
    <div style={{font: "900 28px Arial", color: "#7B8498", letterSpacing: 2}}>BİLDİRİMLER</div>
    <div style={{marginTop: 10, font: "1000 68px Arial"}}>HİÇBİR ŞEY YOK.</div>
  </Interactive.Div>;
};

export const PhantomVibrationShort: React.FC = () => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  const ms = frame / 30 * 1000;
  const finalPhase = ms >= 23140;

  return (
    <AbsoluteFill style={{background: "#03060B", overflow: "hidden", fontFamily: "Arial, sans-serif"}}>
      <Series>
        <Series.Sequence durationInFrames={156} name="Cepte titreşim"><FootageScene file="pocket_check" trimBefore={45} label="AZ ÖNCE..."/></Series.Sequence>
        <Series.Sequence durationInFrames={84} name="Boş ekran"><FootageScene file="phone_closeup" trimBefore={60}/></Series.Sequence>
        <Series.Sequence durationInFrames={60} name="Hayalet titreşim"><FootageScene file="confused_check" trimBefore={55} label="BEYNİNİN SAHTE ALARMI"/></Series.Sequence>
        <Series.Sequence durationInFrames={108} name="Sürekli kontrol"><FootageScene file="daily_scroll" trimBefore={45} label="SİNYAL BEKLENTİSİ"/></Series.Sequence>
        <Series.Sequence durationInFrames={126} name="Kumaş ve kas"><FootageScene file="pocket_check" trimBefore={190}/></Series.Sequence>
        <Series.Sequence durationInFrames={150} name="Yanlış alarm"><FootageScene file="confused_check" trimBefore={170} label="BEYİN: YA KAÇIRIRSAM?"/></Series.Sequence>
        <Series.Sequence durationInFrames={132} name="Ters köşe"><FootageScene file="phone_closeup" trimBefore={180}/></Series.Sequence>
        <Series.Sequence durationInFrames={84} name="Yorum sorusu"><FootageScene file="daily_scroll" trimBefore={180}/></Series.Sequence>
      </Series>

      <div style={{position: "absolute", inset: 0, opacity: .15, backgroundImage: "repeating-linear-gradient(0deg,rgba(255,255,255,.12) 0,rgba(255,255,255,.12) 1px,transparent 1px,transparent 5px)"}} />
      <div style={{position: "absolute", top: 70, right: 65, color: "rgba(255,255,255,.8)", font: "900 21px Arial", letterSpacing: 3}}>STRANGE THINGS LAB</div>

      {ms < 3470 && <Interactive.Div name="Açılış kancası" style={{position: "absolute", top: 300, left: 75, right: 75, color: "white", font: "1000 92px/.92 Arial", letterSpacing: -4, textShadow: "0 10px 38px #000"}}>CEBİN<br/><span style={{color: yellow, fontSize: 132}}>TİTREDİ Mİ?</span></Interactive.Div>}
      {ms >= 3830 && ms < 5200 && <AlertCard/>}
      {ms >= 5620 && ms < 7850 && <Interactive.Div name="Sahte sinyal" style={{position: "absolute", top: 330, left: 70, right: 70, padding: "32px 22px", border: "4px solid #FF5362", background: "rgba(7,10,17,.82)", color: "white", font: "1000 83px/.92 Arial", textAlign: "center", boxShadow: "14px 14px 0 rgba(255,83,98,.45)", translate: `${Math.sin(frame*1.7)*3}px 0`}}>SAHTE<br/><span style={{color: "#FF6471"}}>BİLDİRİM</span></Interactive.Div>}
      {ms >= 8010 && ms < 9810 && <Interactive.Div name="Fenomen adı" style={{position: "absolute", top: 330, left: 70, right: 70, padding: "34px 28px", background: "rgba(4,9,16,.88)", borderLeft: `10px solid ${cyan}`, color: "white", font: "1000 78px/.94 Arial", boxShadow: "0 28px 75px rgba(0,0,0,.55)"}}>BUNUN ADI:<br/><span style={{color: cyan, fontSize: 94}}>HAYALET TİTREŞİM</span></Interactive.Div>}
      {ms >= 10040 && ms < 13530 && <Interactive.Div name="Beklenen sinyaller" style={{position: "absolute", top: 330, left: 80, right: 80}}>{[0,1,2].map((index)=><div key={index} style={{height: 92, marginBottom: 20, borderRadius: 20, border: `2px solid rgba(102,232,242,${.35+index*.2})`, background: "rgba(2,8,16,.76)", translate: `${interpolate(ms,[10040+index*300,10500+index*300],[140,0],{extrapolateLeft:"clamp",extrapolateRight:"clamp",easing:Easing.bezier(.16,1,.3,1)})}px 0`, display: "flex", alignItems: "center", padding: "0 28px", color: index===2?yellow:"white", font: "900 35px Arial"}}>YENİ BİLDİRİM BEKLENTİSİ</div>)}</Interactive.Div>}
      {ms >= 13840 && ms < 17810 && <Interactive.Div name="Yanlış yorumlanan duyumlar" style={{position: "absolute", top: 300, left: 75, right: 75, display: "flex", gap: 24}}><div style={{flex:1,padding:"42px 18px",background:"rgba(3,8,15,.82)",border:`3px solid ${cyan}`,color:"white",font:"1000 58px Arial",textAlign:"center"}}>KUMAŞ<br/><span style={{fontSize:32,color:cyan}}>SÜRTÜNMESİ</span></div><div style={{flex:1,padding:"42px 18px",background:"rgba(3,8,15,.82)",border:`3px solid ${yellow}`,color:"white",font:"1000 58px Arial",textAlign:"center"}}>KAS<br/><span style={{fontSize:32,color:yellow}}>HAREKETİ</span></div></Interactive.Div>}
      {ms >= 18080 && ms < 22780 && <Interactive.Div name="Yanlış alarm mantığı" style={{position: "absolute", top: 315, left: 70, right: 70}}><div style={{padding:"30px",background:"rgba(5,9,16,.86)",borderLeft:"10px solid #FF5B68",color:"white",font:"1000 54px Arial"}}>BİLDİRİMİ KAÇIRMA</div><div style={{height:6,margin:"32px 15px",background:`linear-gradient(90deg,#FF5B68,${yellow})`}}/><div style={{padding:"30px",background:"rgba(5,9,16,.86)",borderLeft:`10px solid ${yellow}`,color:"white",font:"1000 54px Arial"}}>GEREKİRSE YANLIŞ ALARM VER</div></Interactive.Div>}
      {finalPhase && <Interactive.Div name="Ters köşe ve soru" style={{position: "absolute", top: 270, left: 70, right: 70, padding: "38px 28px", background: "rgba(3,7,13,.84)", borderBottom: `9px solid ${yellow}`, color: "white", font: "1000 76px/.94 Arial", textAlign: "center", boxShadow:"0 30px 85px rgba(0,0,0,.62)"}}>TELEFONUN DEĞİL,<br/><span style={{color:yellow,fontSize:96}}>BEKLENTİN TİTRİYOR.</span>{ms>=25990&&<div style={{marginTop:42,paddingTop:28,borderTop:"2px solid rgba(255,255,255,.28)",fontSize:54,color:"white"}}>SEN DE YAŞADIN MI?</div>}</Interactive.Div>}

      <PhantomCaptions captions={phantomCaptions}/>
      <div style={{position:"absolute",left:0,bottom:0,height:9,width:`${frame/durationInFrames*100}%`,background:yellow}}/>

      <Audio src={staticFile("phantom-vibration/narration-elevenlabs.mp3")}/>
      <Audio src={staticFile("hidden-designs/music-v2-future-tech.mp3")} trimBefore={240} volume={(f)=>interpolate(f,[0,18,780,840,899],[0,.17,.15,.22,0],{extrapolateLeft:"clamp",extrapolateRight:"clamp"})}/>
      <Sequence from={0}><Audio src={staticFile("phantom-vibration/vibration.wav")} volume={0.42}/></Sequence>
      <Sequence from={108}><Audio src={staticFile("phantom-vibration/notification.wav")} volume={0.5}/></Sequence>
      <Sequence from={165}><Audio src={staticFile("phantom-vibration/whoosh.wav")} volume={0.52}/></Sequence>
      <Sequence from={240}><Audio src={staticFile("phantom-vibration/impact.wav")} volume={0.38}/></Sequence>
      <Sequence from={414}><Audio src={staticFile("phantom-vibration/whoosh.wav")} volume={0.42}/></Sequence>
      <Sequence from={690}><Audio src={staticFile("phantom-vibration/impact.wav")} volume={0.34}/></Sequence>
    </AbsoluteFill>
  );
};
