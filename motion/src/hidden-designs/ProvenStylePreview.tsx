import React, {useMemo} from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import data from "../../public/hidden-designs/data.json";

type Word = {text: string; startMs: number; endMs: number};

const yellow = "#FFD42A";
const cyan = "#51DEFF";
const red = "#FF3E55";

const FullPhoto: React.FC<{file: string; position?: string; zoom?: number}> = ({file, position = "center", zoom = 1.08}) => {
  const frame = useCurrentFrame();
  return <Img src={staticFile(`hidden-designs/${file}`)} style={{width: "100%", height: "100%", objectFit: "cover", objectPosition: position, transform: `scale(${zoom + frame * 0.00016})`, filter: "contrast(1.08) saturate(1.1)"}} />;
};

const Shade: React.FC = () => <AbsoluteFill style={{background: "linear-gradient(90deg,rgba(0,0,0,.74),rgba(0,0,0,.05) 58%,rgba(0,0,0,.18))"}} />;

const PopText: React.FC<{top?: number; children: React.ReactNode; color?: string; small?: boolean}> = ({top = 94, children, color = "white", small = false}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const s = spring({frame, fps, config: {damping: 13, stiffness: 180}});
  return <div style={{position: "absolute", left: 74, top, color, font: `1000 ${small ? 46 : 78}px/.94 Arial, sans-serif`, maxWidth: 920, textTransform: "uppercase", textShadow: "0 5px 0 rgba(0,0,0,.72),0 12px 30px rgba(0,0,0,.5)", transform: `scale(${.88 + s * .12})`, transformOrigin: "left center"}}>{children}</div>;
};

const Circle: React.FC<{left: number; top: number; size: number; label?: string}> = ({left, top, size, label}) => {
  const frame = useCurrentFrame();
  const draw = interpolate(frame, [2, 12], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp"});
  return <div style={{position: "absolute", left, top, width: size, height: size, border: `10px solid ${yellow}`, borderRadius: "50%", transform: `scale(${draw}) rotate(-8deg)`, boxShadow: "0 0 0 3px rgba(0,0,0,.2),0 0 28px rgba(255,212,42,.55)"}}>{label && <div style={{position: "absolute", left: size * .72, top: -48, color: "#111", background: yellow, padding: "8px 15px", font: "900 28px Arial", whiteSpace: "nowrap", transform: "rotate(8deg)"}}>{label}</div>}</div>;
};

export const ProvenHook: React.FC<{time: number}> = ({time}) => {
  if (time < 3.8) return <AbsoluteFill><FullPhoto file="fuel-gauge.jpg" position="38% 46%" zoom={1.25}/><Shade/><PopText>BU KÜÇÜK OK<br/><span style={{color: yellow}}>SENİ KURTARABİLİR</span></PopText><Circle left={720} top={250} size={140} label="BU OK!"/></AbsoluteFill>;
  if (time < 7.1) return <AbsoluteFill><FullPhoto file="pen-caps.jpg" zoom={1.18}/><Shade/><PopText top={720} small>BU DELİK<br/><span style={{color: cyan}}>SÜS DEĞİL</span></PopText><Circle left={1135} top={95} size={185}/></AbsoluteFill>;
  if (time < 10.7) return <AbsoluteFill><FullPhoto file="escalator.jpg" position="54% center" zoom={1.15}/><Shade/><PopText top={710} small>BU FIRÇA<br/><span style={{color: yellow}}>AYAKKABI TEMİZLEMİYOR</span></PopText><div style={{position:"absolute",right:70,top:100,color:"white",background:red,padding:"13px 22px",font:"900 34px Arial",transform:"rotate(3deg)"}}>CİDDEN!</div></AbsoluteFill>;
  if (time < 15.2) return <AbsoluteFill style={{background: "#5B97E8"}}><div style={{display:"grid",gridTemplateColumns:"1fr 1fr",height:"100%",gap:10,padding:10}}>{[["keyboard.jpg","DOKUN"],["airplane-window.jpg","BAK"],["knife.jpg","KIR"],["tape.jpg","ÖLÇ"]].map(([file,label],i)=><div key={file} style={{position:"relative",overflow:"hidden",border:"7px solid white"}}><Img src={staticFile(`hidden-designs/${file}`)} style={{width:"100%",height:"100%",objectFit:"cover"}}/><div style={{position:"absolute",left:20,bottom:16,color:i%2?"#111":"white",background:i%2?yellow:red,padding:"8px 15px",font:"900 30px Arial"}}>{label}</div></div>)}</div><div style={{position:"absolute",left:0,right:0,top:430,textAlign:"center",color:"white",font:"1000 68px Arial",textShadow:"0 6px 0 #111"}}>GÖRDÜN. AMA FARK ETMEDİN.</div></AbsoluteFill>;
  return <AbsoluteFill><FullPhoto file="tape.jpg" position="center 60%" zoom={1.17}/><Shade/><PopText top={98} small>SONUNCUDAN SONRA<br/><span style={{color:yellow}}>MEZURAYA AYNI BAKMAYACAKSIN</span></PopText><div style={{position:"absolute",right:95,bottom:105,color:"#111",background:yellow,borderRadius:999,padding:"20px 30px",font:"1000 42px Arial",boxShadow:"0 8px 0 #111"}}>8 GİZLİ AMAÇ</div></AbsoluteFill>;
};

const FuelDemo: React.FC<{time: number}> = ({time}) => {
  const local = time - 20.66;
  const side = local > 7;
  return <AbsoluteFill style={{background:"#101621"}}><FullPhoto file="fuel-gauge.jpg" position="38% 45%" zoom={side ? 1.38 : 1.19}/><Shade/>
    {!side && <><div style={{position:"absolute",left:62,top:70,color:"#111",background:yellow,padding:"10px 18px",font:"1000 28px Arial"}}>1 / 8</div><PopText top={130}>DEPO KAPAĞI<br/><span style={{color:cyan}}>HANGİ TARAFTA?</span></PopText></>}
    {side && <><Circle left={395} top={215} size={240} label="OKA BAK"/><div style={{position:"absolute",right:85,top:135,width:590,color:"white",font:"1000 55px/1.03 Arial",textShadow:"0 5px 0 #111"}}>OK NEREYİ GÖSTERİYORSA<br/><span style={{color:yellow}}>KAPAK ORADA.</span></div><div style={{position:"absolute",right:120,bottom:140,color:"white",background:red,padding:"12px 20px",font:"900 30px Arial",transform:"rotate(-2deg)"}}>UTANÇ TURUNA SON ✓</div></>}
  </AbsoluteFill>;
};

export const ProvenCaptions: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const now = frame / fps * 1000;
  const words = data.words as Word[];
  const active = useMemo(() => {
    const index = words.findIndex((w) => now >= w.startMs && now <= w.endMs + 120);
    if (index < 0) return [];
    const start = Math.floor(index / 6) * 6;
    return words.slice(start, start + 6);
  }, [now, words]);
  if (!active.length) return null;
  return <div style={{position:"absolute",left:160,right:160,bottom:35,textAlign:"center",font:"1000 38px/1.18 Arial",textTransform:"uppercase",filter:"drop-shadow(0 4px 0 #000) drop-shadow(0 0 8px #000)"}}>{active.map((w,i)=><React.Fragment key={`${w.startMs}-${w.text}`}><span style={{color:now>=w.startMs&&now<=w.endMs?yellow:"white"}}>{w.text}</span>{i<active.length-1?" ":""}</React.Fragment>)}</div>;
};

export const ProvenStylePreview: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const time = frame / fps;
  return <AbsoluteFill style={{background:"#101621",fontFamily:"Arial,sans-serif",overflow:"hidden"}}>
    {time < 20.66 ? <ProvenHook time={time}/> : <FuelDemo time={time}/>}
    <div style={{position:"absolute",left:28,top:25,color:"white",font:"900 18px Arial",letterSpacing:1.4,textShadow:"0 2px 6px #000"}}>STRANGE THINGS LAB</div>
    <ProvenCaptions/>
    <Audio src={staticFile("hidden-designs/narration.mp3")}/>
    <Audio src={staticFile("hidden-designs/music.mp3")} volume={0.055}/>
  </AbsoluteFill>;
};
