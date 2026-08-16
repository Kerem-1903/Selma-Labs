import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import data from "../../public/hidden-designs/data.json";
import {StrangeThingsMark} from "../components/StrangeThingsMark";
import {CaptionLayer} from "./CaptionLayer";
import {LabHost} from "./LabHost";

type Chapter = {
  id: string;
  kicker: string;
  title: string;
  image: string;
  startMs: number;
  endMs: number;
};

const cyan = "#57E6FF";
const yellow = "#FFD84E";
const red = "#FF5364";
const chapters = data.chapters as Chapter[];
const objectNames: Record<string, string> = {
  fuel: "YAKIT GÖSTERGESİ",
  pen: "KALEM KAPAĞI",
  keyboard: "KLAVYE",
  escalator: "YÜRÜYEN MERDİVEN",
  airplane: "UÇAK PENCERESİ",
  microwave: "MİKRODALGA KAPAĞI",
  knife: "MAKET BIÇAĞI",
  tape: "MEZURA",
};

const boardNotes: Record<string, {label: string; line1: string; line2: string; color: string}> = {
  fuel: {label: "İPUCU", line1: "OK = KAPAK", line2: "YANLIŞ TARAFA SON", color: yellow},
  pen: {label: "GÜVENLİK", line1: "DELİK → HAVA", line2: "SÜS DEĞİL", color: cyan},
  keyboard: {label: "DOKUN", line1: "F   +   J", line2: "ELLERİN PUSULASI", color: red},
  escalator: {label: "UYARI", line1: "FIRÇA ≠ TEMİZLİK", line2: "ORTAYA GEÇ", color: yellow},
  airplane: {label: "2 GÖREV", line1: "BASINÇ + NEM", line2: "KÜÇÜK AMA KRİTİK", color: cyan},
  microwave: {label: "FİLTRE", line1: "IŞIK ✓   DALGA ✕", line2: "METAL AĞ", color: yellow},
  knife: {label: "YEDEK", line1: "KIR → YENİ UÇ", line2: "HER ÇİZGİ BİR UÇ", color: red},
  tape: {label: "GİZLİ ÖLÇÜ", line1: "◆ = 19,2 İNÇ", line2: "48,8 SANTİMETRE", color: yellow},
};

const Marker: React.FC<{chapter: Chapter; progress: number}> = ({chapter, progress}) => {
  const pulse = 1 + Math.sin(progress * Math.PI * 8) * 0.05;
  if (chapter.id === "fuel") {
    return (
      <div style={{position: "absolute", left: "20%", top: "20%", width: 190, height: 190}}>
        <div style={{position: "absolute", inset: 0, border: `8px solid ${yellow}`, borderRadius: "50%", transform: `scale(${pulse})`, boxShadow: `0 0 35px ${yellow}`}} />
        <div style={{position: "absolute", right: -178, top: 72, color: yellow, font: "900 34px Arial"}}>← KAPAĞIN YÖNÜ</div>
      </div>
    );
  }
  if (chapter.id === "pen") {
    return (
      <div style={{position: "absolute", inset: 0}}>
        {[18, 40, 61, 82].map((left) => <div key={left} style={{position: "absolute", left: `${left}%`, top: "22%", width: 28, height: 28, borderRadius: "50%", border: `6px solid ${cyan}`, boxShadow: `0 0 25px ${cyan}`}} />)}
        <div style={{position: "absolute", left: "33%", top: "8%", color: cyan, font: "900 36px Arial"}}>HAVA GEÇİŞİ</div>
      </div>
    );
  }
  if (chapter.id === "keyboard") {
    return <div style={{position: "absolute", left: "13%", top: "67%", padding: "13px 24px", borderRadius: 999, background: red, color: "white", font: "900 31px Arial"}}>DOKUNARAK BUL</div>;
  }
  if (chapter.id === "escalator") {
    return (
      <div style={{position: "absolute", right: 55, top: 120, width: 520, padding: 24, borderRadius: 24, background: "rgba(3,7,16,.86)", border: `2px solid ${yellow}`}}>
        <div style={{height: 18, background: yellow, borderRadius: 9, marginBottom: 10}} />
        <div style={{display: "flex", gap: 6}}>{Array.from({length: 20}).map((_, i) => <div key={i} style={{width: 5, height: 72, background: yellow, transform: `rotate(${i % 2 ? -7 : 7}deg)`}} />)}</div>
        <div style={{color: "white", font: "900 29px Arial", marginTop: 13}}>AYAĞI BOŞLUKTAN UZAKLAŞTIRIR</div>
      </div>
    );
  }
  if (chapter.id === "airplane") {
    return (
      <div style={{position: "absolute", right: 80, top: 85, width: 480, padding: 25, borderRadius: 22, background: "rgba(3,7,16,.85)", border: `2px solid ${cyan}`}}>
        <div style={{display: "flex", alignItems: "center", gap: 12, marginBottom: 18}}><span style={{width: 18, height: 18, borderRadius: "50%", background: red, boxShadow: `0 0 22px ${red}`}} /><span style={{color: "white", font: "900 30px Arial"}}>KÜÇÜK DELİK, İKİ GÖREV</span></div>
        <div style={{color: cyan, font: "800 25px/1.5 Arial"}}>1. BASINCI DENGELER<br />2. NEMİ DIŞARI ATAR</div>
      </div>
    );
  }
  if (chapter.id === "microwave") {
    return (
      <div style={{position: "absolute", inset: 0, overflow: "hidden"}}>
        {Array.from({length: 5}).map((_, i) => {
          const x = 60 + ((progress * 900 + i * 150) % 720);
          return <div key={i} style={{position: "absolute", left: x, top: 120 + i * 105, width: 170, height: 70, border: `8px solid ${cyan}`, borderLeft: 0, borderRight: 0, borderRadius: "50%", opacity: .7}} />;
        })}
        <div style={{position: "absolute", right: 44, top: 50, padding: "12px 20px", borderRadius: 12, background: yellow, color: "#111", font: "900 29px Arial"}}>DALGA BURADA KALIR</div>
      </div>
    );
  }
  if (chapter.id === "knife") {
    return <div style={{position: "absolute", left: "20%", bottom: 120, color: "white", font: "900 39px Arial", background: "rgba(3,7,16,.78)", padding: "14px 23px", borderLeft: `8px solid ${red}`}}>HER ÇİZGİ = YENİ UÇ</div>;
  }
  if (chapter.id === "tape") {
    return (
      <div style={{position: "absolute", left: 70, right: 70, bottom: 110, height: 150, background: "#FFD52B", borderRadius: 20, boxShadow: "0 20px 45px rgba(0,0,0,.35)"}}>
        <div style={{position: "absolute", inset: "18px 35px", borderTop: "4px solid #171717"}} />
        {[12, 32, 52, 72, 92].map((left, index) => <div key={left} style={{position: "absolute", left: `${left}%`, top: 33, color: "#111", font: "900 54px Arial", transform: "rotate(45deg)"}}>◆<span style={{display: "block", transform: "rotate(-45deg)", fontSize: 20, marginLeft: 20, whiteSpace: "nowrap"}}>{index ? "19,2 inç" : "0"}</span></div>)}
      </div>
    );
  }
  return null;
};

const ChalkBoard: React.FC<{children: React.ReactNode}> = ({children}) => (
  <div style={{position: "absolute", left: 28, right: 28, top: 28, bottom: 28, borderRadius: 18, background: "radial-gradient(circle at 20% 25%,rgba(255,255,255,.055),transparent 28%), linear-gradient(135deg,#173E3B,#0E2C2C)", border: "18px solid #A87C45", boxShadow: "inset 0 0 0 4px #5D3E22,0 22px 55px rgba(0,0,0,.35)", overflow: "hidden"}}>
    <div style={{position: "absolute", inset: 0, opacity: .2, backgroundImage: "repeating-linear-gradient(7deg,transparent 0 18px,rgba(255,255,255,.025) 19px 20px)"}} />
    {children}
  </div>
);

const HookMontage: React.FC<{progress: number}> = ({progress}) => {
  const files = ["fuel-gauge.jpg", "pen-caps.jpg", "keyboard.jpg"];
  const reveal = interpolate(progress, [0.04, .35], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp"});
  return (
    <AbsoluteFill style={{background: "#081318"}}>
      <ChalkBoard>
        <div style={{position: "absolute", left: 510, top: 118, width: 780}}>
          <div style={{color: yellow, font: "900 28px Arial", letterSpacing: 4}}>STRANGE THINGS LAB DOSYASI #01</div>
          <div style={{color: "#F8F2DD", font: "900 80px/.96 Arial", marginTop: 22, clipPath: `inset(0 ${(1 - reveal) * 100}% 0 0)`}}>BUNLARIN HİÇBİRİ<br /><span style={{color: cyan}}>SÜS DEĞİL.</span></div>
          <div style={{marginTop: 26, width: 640, height: 8, borderRadius: 8, background: red, scale: `${reveal} 1`, transformOrigin: "left"}} />
        </div>
        <div style={{position: "absolute", left: 485, right: 70, top: 480, display: "flex", gap: 28}}>
          {files.map((file, index) => <div key={file} style={{width: 345, height: 245, background: "#F4EDD7", padding: 12, paddingBottom: 42, rotate: `${[-4,3,-2][index]}deg`, boxShadow: "9px 12px 0 rgba(0,0,0,.25)", translate: `0 ${interpolate(progress, [.12 + index * .08,.25 + index * .08],[60,0],{extrapolateLeft:'clamp',extrapolateRight:'clamp'})}px`, opacity: interpolate(progress,[.1 + index * .08,.22 + index * .08],[0,1],{extrapolateLeft:'clamp',extrapolateRight:'clamp'})}}><Img src={staticFile(`hidden-designs/${file}`)} style={{width: "100%", height: "100%", objectFit: "cover"}} /><div style={{position: "absolute", left: "50%", top: -16, width: 32, height: 32, borderRadius: "50%", background: index === 1 ? cyan : red, boxShadow: "0 5px 8px rgba(0,0,0,.4)"}} /></div>)}
        </div>
        <div style={{position: "absolute", right: 110, top: 250, color: "rgba(255,255,255,.68)", font: "700 27px Comic Sans MS, Arial", rotate: "-7deg"}}>GÖRDÜN.<br />AMA FARK ETMEDİN! ↘</div>
      </ChalkBoard>
      <LabHost mood={progress < .45 ? "write" : "talk"} scale={.9} />
    </AbsoluteFill>
  );
};

const ChapterScene: React.FC<{chapter: Chapter; timeMs: number}> = ({chapter, timeMs}) => {
  const duration = chapter.endMs - chapter.startMs;
  const local = timeMs - chapter.startMs;
  const progress = Math.max(0, Math.min(1, local / duration));
  const fade = Math.min(
    interpolate(local, [0, 350], [0, 1], {extrapolateRight: "clamp"}),
    interpolate(duration - local, [0, 350], [0, 1], {extrapolateRight: "clamp"}),
  );
  if (chapter.id === "hook") return <div style={{position: "absolute", inset: 0, opacity: fade}}><HookMontage progress={progress} /></div>;

  const isOutro = chapter.id === "outro";
  const note = boardNotes[chapter.id];
  const writing = interpolate(progress, [0.02, .22], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp"});
  const hostMood = progress < .25 ? "write" : progress < .62 ? "point" : "talk";
  return (
    <AbsoluteFill style={{opacity: fade, background: "#081318"}}>
      <ChalkBoard>
        <div style={{position: "absolute", left: 475, top: 90, width: 560, zIndex: 3}}>
          <div style={{display: "inline-block", color: note?.color ?? cyan, font: "900 24px Arial", letterSpacing: 2.2, padding: "8px 14px", border: `3px solid ${note?.color ?? cyan}`, rotate: "-1deg"}}>{chapter.kicker}</div>
          <div style={{color: "#F8F2DD", font: `900 ${isOutro ? 69 : 58}px/.98 Arial`, marginTop: 26, opacity: interpolate(progress,[.02,.11],[0,1],{extrapolateLeft:'clamp',extrapolateRight:'clamp'}), translate: `${interpolate(progress,[.02,.12],[-18,0],{extrapolateLeft:'clamp',extrapolateRight:'clamp'})}px 0`, textShadow: "2px 3px 0 rgba(0,0,0,.3)"}}>{chapter.title}</div>
          {!isOutro && <div style={{marginTop: 23, color: "rgba(248,242,221,.7)", font: "700 23px Comic Sans MS, Arial", rotate: "-2deg"}}>görünen detay → <span style={{color: yellow}}>gerçek işlev</span></div>}
        </div>

        {!isOutro && <div style={{position: "absolute", left: 1055, top: 74, width: 720, height: 665, background: "#F3EACF", padding: 15, paddingBottom: 72, rotate: progress < .5 ? "2deg" : "1deg", boxShadow: "12px 15px 0 rgba(0,0,0,.28)", zIndex: 2}}>
          <Img src={staticFile(`hidden-designs/${chapter.image}`)} style={{width: "100%", height: "100%", objectFit: "cover", objectPosition: chapter.id === "fuel" ? "40% 42%" : "center", scale: 1 + progress * .035, filter: "contrast(1.04) saturate(1.08)"}} />
          <div style={{position: "absolute", left: "50%", top: -19, width: 38, height: 38, borderRadius: "50%", background: red, boxShadow: "0 6px 10px rgba(0,0,0,.45)"}} />
          <div style={{position: "absolute", inset: 15, bottom: 72, overflow: "hidden"}}><Marker chapter={chapter} progress={progress} /></div>
          <div style={{position: "absolute", left: 25, bottom: 20, color: "#182336", font: "900 26px Arial", letterSpacing: 1}}>KANIT FOTOĞRAFI / {objectNames[chapter.id]}</div>
        </div>}

        {note && <div style={{position: "absolute", left: 500, top: 505, width: 505, padding: "24px 28px", border: `5px solid ${note.color}`, color: "#F8F2DD", rotate: "-2deg", opacity: interpolate(progress,[.14,.25],[0,1],{extrapolateLeft:'clamp',extrapolateRight:'clamp'})}}>
          <div style={{display: "inline-block", color: "#13262A", background: note.color, padding: "6px 12px", font: "900 20px Arial", marginBottom: 15}}>{note.label}</div>
          <div style={{font: "900 37px/1.16 Comic Sans MS, Arial", clipPath: `inset(0 ${(1-writing)*100}% 0 0)`}}>{note.line1}<br /><span style={{color: note.color}}>{note.line2}</span></div>
        </div>}

        {isOutro && <div style={{position: "absolute", left: 990, top: 210, width: 670, padding: 45, color: "#F8F2DD", border: `6px dashed ${yellow}`, rotate: "2deg", textAlign: "center"}}><div style={{font: "900 39px Comic Sans MS, Arial", color: yellow}}>YORUMLARA YAZ</div><div style={{font: "900 92px Arial", marginTop: 25}}>1 — 8</div><div style={{font: "700 27px Arial", marginTop: 12}}>Hangisi seni şaşırttı?</div></div>}
      </ChalkBoard>
      <LabHost mood={hostMood} scale={.88} />
    </AbsoluteFill>
  );
};

export const HiddenDesignsLong: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const timeMs = (frame / fps) * 1000;
  const chapter = chapters.find((item) => timeMs >= item.startMs && timeMs < item.endMs) ?? chapters[chapters.length - 1];
  const overall = frame / durationInFrames;

  return (
    <AbsoluteFill style={{background: "#050914", fontFamily: "Arial, sans-serif"}}>
      <ChapterScene chapter={chapter} timeMs={timeMs} />
      <div style={{position: "absolute", left: 58, top: 42, zIndex: 10, display: "flex", alignItems: "center", gap: 15, filter: "drop-shadow(0 8px 18px rgba(0,0,0,.55))"}}>
        <StrangeThingsMark size={52} science="#2E7BFF" active="#F13B3B" />
        <div style={{color: "white", font: "900 20px Arial", letterSpacing: 1.5}}>STRANGE THINGS LAB</div>
      </div>
      <div style={{position: "absolute", left: 0, right: 0, top: 0, height: 6, background: "rgba(255,255,255,.1)", zIndex: 20}}>
        <div style={{height: "100%", width: `${overall * 100}%`, background: `linear-gradient(90deg,${cyan},${yellow})`}} />
      </div>
      <CaptionLayer />
      <Audio src={staticFile("hidden-designs/narration.mp3")} volume={1} />
      <Audio src={staticFile("hidden-designs/music.mp3")} volume={0.04} />
    </AbsoluteFill>
  );
};
