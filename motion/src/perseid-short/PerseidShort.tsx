import React, {useMemo} from "react";
import {Audio, Video} from "@remotion/media";
import {AbsoluteFill, Easing, interpolate, staticFile, useCurrentFrame, useVideoConfig} from "remotion";
import data from "../../public/perseid-short/data.json";
import {MascotRigV2} from "../hidden-designs/MascotRigV2";

type Word = {text: string; startMs: number; endMs: number};
const words = data.words as Word[];
const YELLOW = "#FFD42A";
const CYAN = "#50E8FF";

const Footage: React.FC<{name: string; frame: number; dark?: number; position?: string}> = ({name, frame, dark = 0.28, position = "center"}) => (
  <AbsoluteFill style={{overflow: "hidden", background: "#02050C"}}>
    <Video src={staticFile(`perseid-short/footage/${name}.mp4`)} loop muted style={{width: "100%", height: "100%", objectFit: "cover", objectPosition: position, scale: 1.04 + frame / 24000}} />
    <AbsoluteFill style={{background: `linear-gradient(180deg,rgba(0,0,0,.48),transparent 25%,transparent 62%,rgba(0,0,0,.8)),rgba(2,5,12,${dark})`}} />
  </AbsoluteFill>
);

const ShootingStars: React.FC<{frame: number; count?: number}> = ({frame, count = 5}) => (
  <>
    {Array.from({length: count}).map((_, index) => {
      const cycle = (frame + index * 47) % 128;
      const visible = interpolate(cycle, [0, 10, 34, 45], [0, 1, 1, 0], {extrapolateLeft: "clamp", extrapolateRight: "clamp"});
      return <div key={index} style={{position: "absolute", left: -180 + cycle * 14 + (index % 2) * 180, top: 170 + index * 235, width: 340, height: 7, borderRadius: 8, rotate: "-28deg", background: "linear-gradient(90deg,transparent,#FFFFFF,#86EFFF)", opacity: visible * 0.9, filter: "drop-shadow(0 0 14px #5EE9FF)"}} />;
    })}
  </>
);

const Mascot: React.FC<{frame: number; pose?: "pointer" | "present" | "thumbs-up"}> = ({frame, pose = "pointer"}) => {
  const entrance = interpolate(frame, [0, 18], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(0.16, 1, 0.3, 1)});
  return <div style={{position: "absolute", left: -115, bottom: 120, width: 760, height: 850, scale: 0.62, opacity: entrance, translate: `${(1 - entrance) * -40}px 0`, filter: "drop-shadow(0 24px 30px rgba(0,0,0,.75))"}}><MascotRigV2 leftPose="present" rightPose={pose} previousLeftPose="relaxed" previousRightPose="relaxed" mood={pose === "thumbs-up" ? "idea" : "explain"} motion={pose === "thumbs-up" ? "celebrate" : "scan"} actionFrame={frame} /></div>;
};

const Caption: React.FC<{now: number}> = ({now}) => {
  const active = useMemo(() => {
    const index = words.findIndex((word) => now >= word.startMs && now <= word.endMs + 90);
    if (index < 0) return [];
    return words.slice(Math.floor(index / 4) * 4, Math.floor(index / 4) * 4 + 4);
  }, [now]);
  if (!active.length) return null;
  return <div style={{position: "absolute", left: 76, right: 76, bottom: 150, zIndex: 90, textAlign: "center", font: "1000 66px/1.1 Arial", textTransform: "uppercase", textShadow: "0 6px 0 #000,0 0 18px #000"}}>{active.map((word, index) => <React.Fragment key={word.startMs}><span style={{color: now >= word.startMs && now <= word.endMs ? YELLOW : "white"}}>{word.text}</span>{index < active.length - 1 ? " " : ""}</React.Fragment>)}</div>;
};

const BigText: React.FC<{children: React.ReactNode; color?: string; top?: number; size?: number}> = ({children, color = "white", top = 170, size = 112}) => (
  <div style={{position: "absolute", left: 70, right: 70, top, color, font: `1000 ${size}px/.94 Arial`, textTransform: "uppercase", textAlign: "center", textShadow: "0 8px 0 rgba(0,0,0,.75),0 0 24px #000"}}>{children}</div>
);

export const PerseidShort: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const now = frame / fps * 1000;
  const scene = now < 5200 ? 0 : now < 11300 ? 1 : now < 19000 ? 2 : now < 26700 ? 3 : now < 32600 ? 4 : 5;
  const localFrame = Math.max(0, frame - [0, 156, 339, 570, 801, 978][scene]);

  return <AbsoluteFill style={{background: "#02050C", fontFamily: "Arial, sans-serif"}}>
    {scene === 0 ? <><Footage name="meteor" frame={frame} dark={0.36} /><ShootingStars frame={frame} count={6} /><BigText top={175}>BU GECE<br /><span style={{color: CYAN}}>GÖKYÜZÜNE BAK</span></BigText><div style={{position: "absolute", left: 190, right: 190, top: 485, background: "#FF3C5A", color: "white", padding: "24px 30px", font: "1000 60px Arial", textAlign: "center", boxShadow: "12px 14px 0 #000"}}>AMA ONLAR YILDIZ DEĞİL</div><Mascot frame={localFrame} /></> : null}
    {scene === 1 ? <><Footage name="stars" frame={frame} dark={0.45} /><div style={{position: "absolute", left: 70, right: 70, top: 165, background: "rgba(0,0,0,.72)", borderLeft: `12px solid ${YELLOW}`, padding: "28px 30px"}}><div style={{color: YELLOW, font: "1000 79px/.95 Arial"}}>SWIFT–TUTTLE</div><div style={{color: "white", font: "900 49px/1.05 Arial", marginTop: 14}}>ARDINDA TOZ VE TAŞ PARÇALARI BIRAKIYOR</div></div><ShootingStars frame={frame} count={3} /><Mascot frame={localFrame} pose="present" /></> : null}
    {scene === 2 ? <><Footage name="meteor" frame={frame} dark={0.5} /><ShootingStars frame={frame} count={8} /><BigText top={155} size={100}>ATMOSFERE<br /><span style={{color: YELLOW}}>59 km/sn</span><br />HIZLA GİRİYOR</BigText><div style={{position: "absolute", left: 135, right: 135, top: 570, background: "rgba(0,0,0,.8)", borderBottom: `8px solid ${CYAN}`, padding: "26px", color: "white", font: "1000 48px Arial", textAlign: "center"}}>ÇOĞU KUM TANESİ KADAR</div><Mascot frame={localFrame} /></> : null}
    {scene === 3 ? <><Footage name="meteor" frame={frame} dark={0.32} /><ShootingStars frame={frame} count={7} /><BigText top={175} size={96}>HAVA SIKIŞIR<br /><span style={{color: CYAN}}>ISINIR</span><br />VE PARLAR</BigText><div style={{position: "absolute", left: 165, right: 165, top: 570, background: YELLOW, color: "#06101B", padding: "22px", font: "1000 48px Arial", textAlign: "center", rotate: "-2deg", boxShadow: "11px 13px 0 #000"}}>YILDIZ KAYMIYOR!</div><Mascot frame={localFrame} pose="present" /></> : null}
    {scene === 4 ? <><Footage name="stargazer" frame={frame} dark={0.16} position="center" /><BigText top={155} size={91}>ZİRVE GEÇTİ<br /><span style={{color: YELLOW}}>AMA GÖSTERİ<br />BİTMEDİ</span></BigText><div style={{position: "absolute", left: 120, right: 120, top: 525, background: "rgba(0,0,0,.78)", borderLeft: `10px solid ${CYAN}`, padding: "26px", color: "white", font: "900 44px/1.15 Arial", textAlign: "center"}}>KARANLIK BİR YERDE<br />ŞANSIN HÂLÂ VAR</div></> : null}
    {scene === 5 ? <><Footage name="stars" frame={frame} dark={0.4} /><BigText top={120} size={84}>NASIL İZLENİR?</BigText><div style={{position: "absolute", left: 90, right: 90, top: 330, display: "grid", gap: 20}}>{["ŞEHİR IŞIKLARINDAN UZAKLAŞ", "GENİŞ GÖKYÜZÜNÜ İZLE", "20 DAKİKA BEKLE", "TELESKOP GEREKMİYOR"].map((item, index) => <div key={item} style={{background: index === 3 ? YELLOW : "rgba(4,14,26,.9)", color: index === 3 ? "#04101A" : "white", borderLeft: index === 3 ? "none" : `10px solid ${CYAN}`, padding: "25px 27px", font: "1000 42px Arial", boxShadow: "8px 10px 0 rgba(0,0,0,.7)"}}>✓ {item}</div>)}</div><Mascot frame={localFrame} pose="thumbs-up" /></> : null}
    <div style={{position: "absolute", left: 26, top: 34, zIndex: 100, color: "white", font: "1000 20px Arial", letterSpacing: 1.7, textShadow: "0 3px 8px #000"}}>STRANGE THINGS LAB</div>
    <Caption now={now} />
    <Audio src={staticFile("perseid-short/narration.mp3")} />
    <Audio src={staticFile("hidden-designs/music-v2-future-tech.mp3")} volume={(audioFrame) => interpolate(audioFrame, [0, 20, 1100, 1168], [0, 0.055, 0.045, 0], {extrapolateLeft: "clamp", extrapolateRight: "clamp"})} />
  </AbsoluteFill>;
};
