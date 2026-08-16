import React from "react";
import {Video} from "@remotion/media";
import {AbsoluteFill, Img, Series, staticFile} from "remotion";

const navy = "#071A2E";
const cyan = "#23D5E8";
const yellow = "#FFD83D";
const red = "#FF453A";

const Shade: React.FC = () => (
  <AbsoluteFill style={{background: "linear-gradient(180deg,rgba(2,11,23,.48),rgba(2,11,23,.04) 42%,rgba(2,11,23,.82) 100%)"}}/>
);

export const Film: React.FC<{file: string; trimBefore?: number; brightness?: number; position?: string}> = ({file, trimBefore = 0, brightness = .7, position = "center"}) => (
  <AbsoluteFill style={{background: navy}}>
    <Video
      src={staticFile(file)}
      muted
      loop
      trimBefore={trimBefore}
      style={{position: "absolute", top: 0, bottom: 0, left: "50%", width: "auto", minWidth: "100%", maxWidth: "none", height: "100%", translate: "-50% 0", objectFit: "cover", objectPosition: position, filter: `brightness(${brightness}) contrast(1.1) saturate(.92)`}}
    />
    <Shade/>
  </AbsoluteFill>
);

const Photo: React.FC<{file: string; credit: string; position?: string; zoom?: number}> = ({file, credit, position = "center", zoom = 1}) => (
  <AbsoluteFill style={{background: navy}}>
    <Img src={staticFile(file)} style={{width: "100%", height: "100%", objectFit: "cover", objectPosition: position, scale: zoom, filter: "brightness(.7) contrast(1.1) saturate(.9)"}}/>
    <Shade/>
    <div style={{position: "absolute", left: 38, top: 128, padding: "8px 12px", borderRadius: 8, background: "rgba(2,11,23,.76)", color: "rgba(255,255,255,.72)", font: "700 18px Arial"}}>{credit}</div>
  </AbsoluteFill>
);

const Headline: React.FC<{children: React.ReactNode; top?: number; accent?: "cyan" | "yellow" | "red"}> = ({children, top = 300, accent = "cyan"}) => {
  const color = accent === "yellow" ? yellow : accent === "red" ? red : cyan;
  return (
    <div style={{position: "absolute", top, left: 54, right: 54, padding: "26px 28px", background: "rgba(2,13,27,.86)", borderLeft: `12px solid ${color}`, color: "white", textAlign: "center", font: "1000 68px/.94 Arial Black", letterSpacing: -2.5, boxShadow: "0 16px 45px rgba(0,0,0,.44)"}}>{children}</div>
  );
};

export const HookScene: React.FC = () => (
  <AbsoluteFill>
    <Film file="airplane-lavatory/footage/airplane_flying.mp4" trimBefore={15} brightness={.74}/>
    <div style={{position: "absolute", top: 245, left: 54, right: 54, textAlign: "center"}}>
      <div style={{display: "inline-block", padding: "10px 18px", background: yellow, color: navy, font: "1000 32px Arial Black", letterSpacing: 2}}>UÇAK TUVALETİ</div>
      <div style={{marginTop: 15, color: "white", font: "1000 82px/.91 Arial Black", letterSpacing: -4, textShadow: "0 8px 28px #000"}}>ATIKLARI<br/><span style={{color: cyan, fontSize: 99}}>AŞAĞI MI</span><br/>BIRAKIYOR?</div>
    </div>
  </AbsoluteFill>
);

export const LavatoryReveal: React.FC = () => (
  <AbsoluteFill>
    <Photo file="airplane-lavatory/stills/aircraft_lavatory.jpg" credit="Gerçek uçak tuvaleti · Wikimedia Commons / Public Domain" position="38% center"/>
    <Headline top={350} accent="red"><span style={{color: red, fontSize: 116}}>HAYIR!</span></Headline>
  </AbsoluteFill>
);

export const VacuumDiagram: React.FC = () => (
  <Series>
    <Series.Sequence durationInFrames={92}>
      <Film file="airplane-lavatory/footage/toilet_flush_hand.mp4" trimBefore={20} brightness={.68}/>
      <Headline><span style={{color: yellow}}>SİFONA BASINCA</span><br/>SİSTEM DEVREYE GİRER</Headline>
    </Series.Sequence>
    <Series.Sequence durationInFrames={92}>
      <Photo file="airplane-lavatory/stills/aircraft_toilet_blue_water.jpg" credit="Gerçek uçak tuvaleti · Wikimedia Commons / Public Domain" position="center 58%"/>
      <Headline><span style={{color: cyan}}>GÜÇLÜ VAKUM</span><br/>ATIĞI BORUYA ÇEKER</Headline>
    </Series.Sequence>
  </Series>
);

export const WhooshScene: React.FC = () => (
  <AbsoluteFill>
    <Photo file="airplane-lavatory/stills/aircraft_toilet_blue_water.jpg" credit="Gerçek uçak tuvaleti · Wikimedia Commons / Public Domain" position="center 64%" zoom={1.08}/>
    <Headline top={330}><span style={{color: cyan, fontSize: 108}}>“FOŞ!”</span><br/>O SES VAKUMDAN GELİR</Headline>
  </AbsoluteFill>
);

export const LockedTankScene: React.FC = () => (
  <AbsoluteFill>
    <Film file="airplane-lavatory/footage/airplane_cabin.mp4" trimBefore={50} brightness={.58}/>
    <Headline top={330}>ATIK UÇUŞ BOYUNCA<br/><span style={{color: yellow, fontSize: 88}}>KAPALI TANKTA</span></Headline>
  </AbsoluteFill>
);

export const GroundServiceScene: React.FC = () => (
  <Series>
    <Series.Sequence durationInFrames={70}>
      <Photo file="airplane-lavatory/stills/service_hose_connection.jpg" credit="U.S. Air Force / Timothy Taylor · Public Domain" position="52% center"/>
      <Headline top={265}>İNİŞTEN SONRA<br/><span style={{color: cyan}}>HORTUM BAĞLANIR</span></Headline>
    </Series.Sequence>
    <Series.Sequence durationInFrames={65}>
      <Film file="airplane-lavatory/footage/ground_crew_working.mp4" trimBefore={45} brightness={.64}/>
      <Headline top={265}>YER EKİBİ<br/><span style={{color: cyan}}>UÇAĞI SERVİSE ALIR</span></Headline>
    </Series.Sequence>
    <Series.Sequence durationInFrames={70}>
      <Photo file="airplane-lavatory/stills/lavatory_service.jpg" credit="U.S. Air Force / Greg L. Davis · Public Domain" position="58% center"/>
      <Headline top={265}>ATIK<br/><span style={{color: yellow}}>SERVİS ARACINA</span><br/>BOŞALTILIR</Headline>
    </Series.Sequence>
  </Series>
);

export const FinaleScene: React.FC = () => (
  <AbsoluteFill>
    <Film file="airplane-lavatory/footage/airplane_flying.mp4" trimBefore={180} brightness={.58}/>
    <div style={{position: "absolute", top: 315, left: 50, right: 50, textAlign: "center"}}>
      <div style={{color: "white", font: "1000 69px/.92 Arial Black", textShadow: "0 9px 30px #000"}}>GÖKYÜZÜNE AÇILAN<br/>BİR DELİK DEĞİL</div>
      <div style={{marginTop: 28, padding: "25px 20px", background: yellow, color: navy, font: "1000 78px/.9 Arial Black", boxShadow: `14px 14px 0 ${cyan}`}}>UÇAN, MÜHÜRLÜ<br/>BİR SİSTEM</div>
    </div>
  </AbsoluteFill>
);
