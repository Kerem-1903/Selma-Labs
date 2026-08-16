import React from "react";
import type {Caption} from "@remotion/captions";
import {Audio, Video} from "@remotion/media";
import {
  AbsoluteFill,
  Easing,
  Interactive,
  interpolate,
  Sequence,
  Series,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {vlahovicCaptions} from "./captions";

const red = "#F04438";
const yellow = "#FFD52A";

const Film: React.FC<{
  file: string;
  trimBefore?: number;
  scale?: number;
  source?: string;
  brightness?: number;
}> = ({file, trimBefore = 0, scale = 1.04, source, brightness = 0.78}) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill>
      <Video
        src={staticFile(file)}
        muted
        trimBefore={trimBefore}
        loop
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          scale: interpolate(frame, [0, 210], [scale, scale + 0.055], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.linear,
          }),
          filter: `brightness(${brightness}) contrast(1.13) saturate(.9)`,
        }}
      />
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(180deg,rgba(0,0,0,.5) 0%,transparent 27%,transparent 54%,rgba(0,0,0,.92) 94%),linear-gradient(90deg,rgba(0,0,0,.2),transparent 55%)",
        }}
      />
      {source ? (
        <div style={{position: "absolute", top: 76, left: 46, padding: "9px 14px", background: "rgba(0,0,0,.68)", color: "rgba(255,255,255,.82)", font: "700 20px Arial", letterSpacing: 0.4}}>
          {source}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

const CaptionLayer: React.FC<{captions: Caption[]}> = ({captions}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const nowMs = (frame / fps) * 1000;
  const caption = captions.find((item) => nowMs >= item.startMs && nowMs < item.endMs);
  if (!caption) return null;
  const localFrame = frame - (caption.startMs / 1000) * fps;
  const enter = spring({frame: localFrame, fps, config: {damping: 18, stiffness: 250, mass: 0.6}});
  const words = caption.text.split(" ");
  const hotWord = words.findIndex((word) => /DOMATES|DEĞİLDİ|BEŞİKTAŞ|KASA|GOL/.test(word));
  return (
    <Interactive.Div
      name="Altyazı"
      style={{
        position: "absolute",
        left: 54,
        right: 54,
        bottom: 280,
        display: "flex",
        justifyContent: "center",
        opacity: interpolate(nowMs, [caption.startMs, caption.startMs + 80, caption.endMs - 90, caption.endMs], [0, 1, 1, 0], {extrapolateLeft: "clamp", extrapolateRight: "clamp"}),
        transform: `translateY(${interpolate(enter, [0, 1], [26, 0])}px)`,
      }}
    >
      <div style={{maxWidth: 970, padding: "22px 26px 25px", background: "rgba(0,0,0,.8)", borderRadius: 22, borderBottom: `7px solid ${red}`, textAlign: "center", boxShadow: "0 18px 55px rgba(0,0,0,.55)"}}>
        {words.map((word, index) => (
          <span key={`${word}-${index}`} style={{display: "inline-block", marginRight: 13, color: index === hotWord ? yellow : "white", font: "1000 57px/.99 Arial Black, Arial, sans-serif", letterSpacing: -2.5, textShadow: "0 4px 0 #000"}}>
            {word}
          </span>
        ))}
      </div>
    </Interactive.Div>
  );
};

const HookOverlay: React.FC = () => {
  const frame = useCurrentFrame();
  const slam = spring({frame, fps: 30, config: {damping: 13, stiffness: 260, mass: 0.58}});
  return (
    <Interactive.Div name="Açılış sorusu" style={{position: "absolute", top: 250, left: 58, right: 58, transform: `scale(${interpolate(slam, [0, 1], [1.03, 1])}) rotate(-1.4deg)`, transformOrigin: "center"}}>
      <div style={{display: "inline-block", padding: "10px 18px", background: red, color: "white", font: "1000 34px Arial Black", letterSpacing: 2}}>VLAHOVİĆ</div>
      <div style={{marginTop: 10, color: "white", font: "1000 78px/.9 Arial Black, Arial", letterSpacing: -4, textShadow: "0 9px 25px #000"}}>2 KASA<br/><span style={{color: yellow, fontSize: 112}}>DOMATESLE</span><br/>Mİ GELDİ?</div>
    </Interactive.Div>
  );
};

const CrateFocus: React.FC = () => {
  const frame = useCurrentFrame();
  const pop = spring({frame, fps: 30, config: {damping: 12, stiffness: 220}});
  return (
    <>
      <Film file="vlahovic-tomato/sources/arrival.mp4" trimBefore={25} scale={1.13} source="Viral görüntü: etocast / YouTube" />
      <div style={{position: "absolute", left: 150, top: 870, width: 675, height: 14, background: red, borderRadius: 10, transform: `rotate(8deg) scaleX(${interpolate(pop, [0, 1], [.05, 1])})`, transformOrigin: "left", boxShadow: "0 5px 15px rgba(0,0,0,.65)"}} />
      <div style={{position: "absolute", left: 782, top: 920, width: 0, height: 0, borderTop: "30px solid transparent", borderBottom: "30px solid transparent", borderLeft: `58px solid ${red}`, transform: "rotate(8deg)"}} />
      <div style={{position: "absolute", top: 760, left: 125, padding: "13px 24px", background: red, color: "white", font: "1000 54px Arial Black", transform: `rotate(-3deg) scale(${interpolate(pop, [0, 1], [.65, 1])})`}}>2 KASA?</div>
    </>
  );
};

const NotHis: React.FC = () => {
  const frame = useCurrentFrame();
  const slash = interpolate(frame, [8, 22], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(.16, 1, .3, 1)});
  return (
    <>
      <Film file="vlahovic-tomato/sources/vlahovic-fans.mp4" trimBefore={18} scale={1.11} source="Görüntü: Beşiktaş Donanması / YouTube" />
      <div style={{position: "absolute", top: 360, left: 65, right: 65, padding: "28px 20px", background: "rgba(0,0,0,.82)", border: "5px solid white", color: "white", textAlign: "center", font: "1000 76px/.95 Arial Black", transform: "rotate(-1deg)"}}>KASALAR<br/><span style={{color: yellow, fontSize: 102}}>ONUN DEĞİLDİ</span></div>
      <div style={{position: "absolute", top: 505, left: 150, width: 780 * slash, height: 18, background: red, transform: "rotate(-8deg)", transformOrigin: "left", boxShadow: "0 6px 18px #000"}} />
    </>
  );
};

const SourceCard: React.FC = () => {
  const frame = useCurrentFrame();
  const slide = spring({frame, fps: 30, config: {damping: 18, stiffness: 180}});
  return (
    <>
      <Film file="vlahovic-tomato/footage/airport_luggage.mp4" trimBefore={45} scale={1.03} />
      <Interactive.Div name="Kaynak kartı" style={{position: "absolute", top: 260, left: 58, right: 58, padding: "40px 40px 46px", background: "rgba(8,8,8,.9)", color: "white", borderLeft: `13px solid ${red}`, boxShadow: "18px 20px 0 rgba(240,68,56,.32)", transform: `translateX(${interpolate(slide, [0, 1], [-120, 0])}px)`}}>
        <div style={{font: "900 27px Arial", letterSpacing: 3, color: "rgba(255,255,255,.64)"}}>ERTAN SÜZGÜN'ÜN AKTARDIĞINA GÖRE</div>
        <div style={{marginTop: 20, font: "1000 67px/.98 Arial Black", letterSpacing: -3}}>DOMATESLER<br/><span style={{color: yellow}}>BEŞİKTAŞ HEYETİNE</span><br/>AİTTİ</div>
      </Interactive.Div>
    </>
  );
};

const Finale: React.FC = () => {
  const frame = useCurrentFrame();
  const tomato = spring({frame, fps: 30, config: {damping: 9, stiffness: 190, mass: .55}});
  return (
    <>
      <Film file="vlahovic-tomato/footage/tomatoes.mp4" trimBefore={85} scale={1.08} brightness={0.7} />
      <div style={{position: "absolute", inset: 0, background: "repeating-linear-gradient(118deg,transparent 0,transparent 100px,rgba(255,255,255,.05) 101px,rgba(255,255,255,.05) 107px)"}} />
      <div style={{position: "absolute", top: 330, left: 50, right: 50, textAlign: "center", transform: `scale(${interpolate(tomato, [0, 1], [.65, 1])})`}}>
        <div style={{font: "1000 73px/.92 Arial Black", color: "white", textShadow: "0 8px 28px #000"}}>İLK GİZEM</div>
        <div style={{marginTop: 22, display: "inline-block", padding: "22px 34px", background: yellow, color: "#080808", font: "1000 82px/.9 Arial Black", transform: "rotate(-2deg)", boxShadow: `16px 16px 0 ${red}`}}>GOL DEĞİL,<br/>DOMATES!</div>
      </div>
    </>
  );
};

export const VlahovicTomatoShort: React.FC = () => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  return (
    <AbsoluteFill style={{background: "#050505", overflow: "hidden", fontFamily: "Arial, sans-serif"}}>
      <Series>
        <Series.Sequence durationInFrames={117}><Film file="vlahovic-tomato/sources/arrival.mp4" trimBefore={2} scale={1.1} source="Viral görüntü: etocast / YouTube"/><HookOverlay/></Series.Sequence>
        <Series.Sequence durationInFrames={96}><CrateFocus/></Series.Sequence>
        <Series.Sequence durationInFrames={69}><NotHis/></Series.Sequence>
        <Series.Sequence durationInFrames={210}><SourceCard/></Series.Sequence>
        <Series.Sequence durationInFrames={150}><Film file="vlahovic-tomato/footage/restaurant.mp4" trimBefore={30} scale={1.04}/><div style={{position:"absolute",top:300,left:70,right:70,padding:"28px",background:"rgba(0,0,0,.78)",borderTop:`8px solid ${yellow}`,font:"1000 70px/.94 Arial Black",color:"white",textAlign:"center"}}>YEMEKTE ÇOK<br/><span style={{color:yellow,fontSize:92}}>BEĞENDİLER</span></div></Series.Sequence>
        <Series.Sequence durationInFrames={150}><Film file="vlahovic-tomato/footage/tomatoes.mp4" trimBefore={20} scale={1.08}/><div style={{position:"absolute",top:310,left:85,right:85,padding:"25px",background:red,color:"white",font:"1000 76px/.92 Arial Black",textAlign:"center",transform:"rotate(-1.5deg)",boxShadow:"13px 13px 0 rgba(0,0,0,.75)"}}>İKİ KASAYI<br/><span style={{color:yellow}}>YANLARINA ALDILAR</span></div></Series.Sequence>
        <Series.Sequence durationInFrames={174}><Film file="vlahovic-tomato/footage/airport_luggage.mp4" trimBefore={110} scale={1.04}/><div style={{position:"absolute",top:310,left:64,right:64,padding:"30px",background:"rgba(0,0,0,.83)",border:`5px solid ${red}`,color:"white",font:"1000 63px/.96 Arial Black",textAlign:"center"}}>BAGAJLARLA<br/>YAN YANA OLUNCA<br/><span style={{color:yellow,fontSize:79}}>YANLIŞ ANLAŞILDI</span></div></Series.Sequence>
        <Series.Sequence durationInFrames={114}><Finale/></Series.Sequence>
      </Series>

      <div style={{position: "absolute", top: 72, right: 48, color: "rgba(255,255,255,.88)", font: "900 22px Arial", letterSpacing: 3}}>STRANGE THINGS LAB</div>
      <CaptionLayer captions={vlahovicCaptions}/>
      <div style={{position: "absolute", bottom: 0, left: 0, height: 10, width: `${(frame / durationInFrames) * 100}%`, background: `linear-gradient(90deg,${red},${yellow})`}} />

      <Audio src={staticFile("vlahovic-tomato/narration.mp3")} volume={1}/>
      <Audio src={staticFile("hidden-designs/music-v2-future-tech.mp3")} trimBefore={210} volume={(f) => interpolate(f, [0, 15, 930, 1079], [0, .17, .16, .25], {extrapolateLeft: "clamp", extrapolateRight: "clamp"})}/>
      <Sequence from={0}><Audio src={staticFile("phantom-vibration/impact.wav")} volume={.58}/></Sequence>
      <Sequence from={111}><Audio src={staticFile("phantom-vibration/whoosh.wav")} volume={.52}/></Sequence>
      <Sequence from={210}><Audio src={staticFile("phantom-vibration/impact.wav")} volume={.5}/></Sequence>
      <Sequence from={282}><Audio src={staticFile("phantom-vibration/whoosh.wav")} volume={.42}/></Sequence>
      <Sequence from={492}><Audio src={staticFile("phantom-vibration/whoosh.wav")} volume={.4}/></Sequence>
      <Sequence from={642}><Audio src={staticFile("phantom-vibration/impact.wav")} volume={.38}/></Sequence>
      <Sequence from={807}><Audio src={staticFile("phantom-vibration/whoosh.wav")} volume={.42}/></Sequence>
      <Sequence from={966}><Audio src={staticFile("phantom-vibration/impact.wav")} volume={.54}/></Sequence>
    </AbsoluteFill>
  );
};
