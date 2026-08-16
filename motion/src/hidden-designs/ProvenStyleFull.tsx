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
import {ProvenCaptions, ProvenHook} from "./ProvenStylePreview";

type Chapter = {id: string; kicker: string; title: string; image: string; startMs: number; endMs: number};
const chapters = data.chapters as Chapter[];
const yellow = "#FFD42A";
const cyan = "#51DEFF";
const red = "#FF3E55";

const replacementImages: Record<string, string> = {
  escalator: "escalator-brush-v2.png",
  airplane: "airplane-bleed-hole-v2.png",
  tape: "tape-diamond-v2.png",
};

const info: Record<string, {number: string; short: string; wrong: string; truth: string; punch: string; accent: string}> = {
  fuel: {number:"1 / 8",short:"YAKIT OKU",wrong:"Camdan bakman gerekiyor",truth:"OK = KAPAĞIN TARAFI",punch:"UTANÇ TURUNA SON ✓",accent:yellow},
  pen: {number:"2 / 8",short:"KALEM KAPAĞI",wrong:"Mürekkebi havalandırıyor",truth:"DELİK = HAVA GEÇİŞİ",punch:"SÜS DEĞİL. GÜVENLİK.",accent:cyan},
  keyboard: {number:"3 / 8",short:"F VE J TUŞLARI",wrong:"Üretim izi",truth:"PARMAKLARIN PUSULASI",punch:"BAKMADAN YAZ ✓",accent:red},
  escalator: {number:"4 / 8",short:"KENAR FIRÇASI",wrong:"Ayakkabını temizliyor",truth:"AYAĞINI UZAKLAŞTIRIYOR",punch:"FIRÇA ≠ TEMİZLİK",accent:yellow},
  airplane: {number:"5 / 8",short:"UÇAK PENCERESİ",wrong:"Kusur ya da vida deliği",truth:"BASINÇ + NEM KONTROLÜ",punch:"MİNİCİK DELİK, İKİ İŞ",accent:cyan},
  microwave: {number:"6 / 8",short:"METAL NOKTALAR",wrong:"Görüşü bozmak için",truth:"IŞIK GEÇER • DALGA KALIR",punch:"GÖRÜNMEZ GÜVENLİK DUVARI",accent:yellow},
  knife: {number:"7 / 8",short:"BIÇAKTAKİ ÇİZGİLER",wrong:"Ölçü işareti",truth:"HER ÇİZGİ = YENİ UÇ",punch:"KIR • YENİLE • DEVAM ET",accent:red},
  tape: {number:"8 / 8",short:"MEZURADAKİ ELMAS",wrong:"Rastgele logo",truth:"◆ = 48,8 SANTİMETRE",punch:"MARANGOZUN KISA YOLU",accent:yellow},
};

const Photo: React.FC<{chapter: Chapter; local: number; crop?: boolean}> = ({chapter, local, crop}) => {
  const zoom = (crop ? 1.3 : 1.08) + local * .0000015;
  const positions: Record<string,string> = {fuel:"38% 45%",pen:"center",keyboard:"center",escalator:"center",airplane:"center",microwave:"center",knife:"center",tape:"center"};
  const file = replacementImages[chapter.id] ?? chapter.image;
  return <Img src={staticFile(`hidden-designs/${file}`)} style={{width:"100%",height:"100%",objectFit:"cover",objectPosition:positions[chapter.id],transform:`scale(${zoom})`,filter:"contrast(1.09) saturate(1.09)"}}/>;
};

const Ring: React.FC<{left:number;top:number;size:number;color:string;delay?:number}> = ({left,top,size,color,delay=0}) => {
  const frame=useCurrentFrame();
  const pulse=1+Math.sin((frame-delay)/6)*.045;
  return <div style={{position:"absolute",left,top,width:size,height:size,border:`10px solid ${color}`,borderRadius:"50%",boxShadow:`0 0 0 5px rgba(0,0,0,.44),0 0 30px ${color}`,transform:`scale(${pulse})`}}/>;
};

const Tag: React.FC<{left:number;top:number;color:string;children:React.ReactNode}> = ({left,top,color,children}) => <div style={{position:"absolute",left,top,color:"#101621",background:color,padding:"9px 15px",font:"1000 24px Arial",boxShadow:"7px 8px 0 rgba(0,0,0,.7)",transform:"rotate(-1deg)"}}>{children}</div>;

const FeatureMarker: React.FC<{id:string;color:string}> = ({id,color}) => {
  if(id==="fuel") return <><Ring left={747} top={168} size={132} color={color}/><Tag left={568} top={322} color={color}>KÜÇÜK OK BURADA</Tag><div style={{position:"absolute",left:730,top:286,width:95,height:10,background:color,transform:"rotate(-48deg)",transformOrigin:"right center",boxShadow:`0 0 15px ${color}`}}/></>;
  if(id==="pen") return <><Ring left={305} top={520} size={112} color={color}/><Ring left={716} top={520} size={112} color={color} delay={8}/><Tag left={330} top={690} color={color}>HAVA GEÇİŞİ</Tag></>;
  if(id==="keyboard") return <><Tag left={82} top={674} color={color}>F TUŞUNDAKİ ÇIKINTI</Tag><div style={{position:"absolute",left:210,top:764,width:12,height:118,background:color,boxShadow:`0 0 18px ${color}`,transform:"rotate(20deg)"}}/></>;
  if(id==="escalator") return <><div style={{position:"absolute",left:612,top:145,width:274,height:742,borderLeft:`12px solid ${color}`,borderRight:`12px solid ${color}`,background:`linear-gradient(90deg,transparent,${color}2a,transparent)`,filter:`drop-shadow(0 0 13px ${color})`}}/><Tag left={548} top={118} color={color}>GÜVENLİK FIRÇASI</Tag></>;
  if(id==="airplane") return <><Ring left={500} top={615} size={76} color={color}/><Tag left={250} top={728} color={color}>BASINÇ DELİĞİ</Tag><div style={{position:"absolute",left:466,top:713,width:92,height:9,background:color,transform:"rotate(-43deg)",transformOrigin:"right center"}}/></>;
  if(id==="microwave") return <><div style={{position:"absolute",left:260,top:274,width:390,height:330,border:`10px solid ${color}`,background:"linear-gradient(135deg,transparent 42%,rgba(255,255,255,.18) 48%,transparent 55%)",boxShadow:`0 0 30px ${color}`}}/><Tag left={300} top={645} color={color}>DELİKLİ METAL AĞ</Tag></>;
  if(id==="knife") return <><Tag left={105} top={180} color={color}>HER ÇİZGİ YENİ BİR UÇ</Tag>{[255,435,610].map((left)=><div key={left} style={{position:"absolute",left,top:346,width:70,height:13,background:color,transform:"rotate(-54deg)",boxShadow:`0 0 16px ${color}`}}/>)}</>;
  if(id==="tape") return <><Ring left={818} top={430} size={112} color={color}/><Tag left={510} top={618} color={color}>SİYAH ELMAS</Tag><div style={{position:"absolute",left:730,top:598,width:115,height:9,background:color,transform:"rotate(-42deg)",transformOrigin:"right center"}}/></>;
  return null;
};

const Wipe: React.FC<{local: number; stageLength: number; color: string}> = ({local, stageLength, color}) => {
  const within = local % stageLength;
  const x = interpolate(within,[0,180,360],[100,0,-100],{extrapolateLeft:"clamp",extrapolateRight:"clamp"});
  if (within > 360) return null;
  return <AbsoluteFill style={{background:color,transform:`translateX(${x}%)`,zIndex:15}}/>;
};

const ChapterScene: React.FC<{chapter: Chapter; timeMs: number}> = ({chapter,timeMs}) => {
  const cfg = info[chapter.id];
  const local = timeMs - chapter.startMs;
  const duration = chapter.endMs - chapter.startMs;
  const stageLength = duration / 4;
  const stage = Math.min(3,Math.floor(local / stageLength));
  const enter = interpolate(local % stageLength,[100,480],[0,1],{extrapolateLeft:"clamp",extrapolateRight:"clamp"});
  const close = stage === 1 || stage === 3;
  const shade = stage === 2 ? "linear-gradient(90deg,rgba(0,0,0,.04) 0 49%,#172334 49% 100%)" : "linear-gradient(90deg,rgba(0,0,0,.76),rgba(0,0,0,.08) 68%)";
  return <AbsoluteFill style={{background:"#111827",overflow:"hidden"}}>
    <Photo chapter={chapter} local={local} crop={close}/>
    <AbsoluteFill style={{background:shade}}/>
    {stage===0 && <>
      <div style={{position:"absolute",left:70,top:72,color:"#111",background:cfg.accent,padding:"11px 19px",font:"1000 29px Arial",transform:`translateY(${(1-enter)*-24}px)`,opacity:enter}}>{cfg.number} — {cfg.short}</div>
      <div style={{position:"absolute",left:70,top:155,maxWidth:1050,color:"white",font:"1000 72px/.97 Arial",textTransform:"uppercase",textShadow:"0 6px 0 rgba(0,0,0,.8)",opacity:enter}}>{chapter.title}</div>
      <div style={{position:"absolute",left:70,bottom:155,color:"#111",background:"white",padding:"14px 20px",font:"900 29px Arial",transform:"rotate(-1deg)"}}>GÖRDÜN. AMA NEDENİNİ BİLMEDİN.</div>
    </>}
    {stage===1 && <>
      <div style={{position:"absolute",left:75,top:92,color:"white",font:"900 34px Arial",background:red,padding:"10px 18px"}}>ÇOĞU KİŞİNİN SANDIĞI</div>
      <div style={{position:"absolute",left:75,top:165,maxWidth:880,color:"white",font:"1000 66px/.98 Arial",textShadow:"0 6px 0 #000",textDecoration:"line-through",textDecorationColor:red,textDecorationThickness:9}}>{cfg.wrong}</div>
      <div style={{position:"absolute",left:75,bottom:150,color:"white",font:"1000 72px Arial",textShadow:"0 6px 0 #000"}}>HAYIR.</div>
    </>}
    {stage===2 && <>
      <div style={{position:"absolute",left:"52%",right:70,top:110,color:"white"}}>
        <div style={{display:"inline-block",color:"#111",background:cfg.accent,padding:"9px 16px",font:"1000 28px Arial"}}>GERÇEK AMACI</div>
        <div style={{marginTop:28,font:"1000 68px/.97 Arial",color:cfg.accent,textShadow:"0 6px 0 rgba(0,0,0,.5)"}}>{cfg.truth}</div>
        <div style={{marginTop:34,width:300,height:11,background:red}}/>
        <div style={{marginTop:30,font:"800 29px/1.35 Arial",maxWidth:700}}>Küçük ayrıntı, büyük işi sessizce yapıyor.</div>
      </div>
      <FeatureMarker id={chapter.id} color={cfg.accent}/>
    </>}
    {stage===3 && <>
      <div style={{position:"absolute",left:70,right:70,top:90,textAlign:"center",color:"white",font:"1000 49px Arial",textShadow:"0 5px 0 #000"}}>KISACASI</div>
      <div style={{position:"absolute",left:"50%",top:"46%",transform:"translate(-50%,-50%) rotate(-1deg)",color:"#111",background:cfg.accent,padding:"22px 34px",font:"1000 68px/.96 Arial",whiteSpace:"nowrap",boxShadow:"12px 14px 0 rgba(0,0,0,.65)"}}>{cfg.punch}</div>
    </>}
    <Wipe local={local} stageLength={stageLength} color={cfg.accent}/>
  </AbsoluteFill>;
};

const Outro: React.FC = () => {
  const files=["fuel-gauge.jpg","pen-caps.jpg","keyboard.jpg","escalator-brush-v2.png","airplane-bleed-hole-v2.png","microwave-door.jpg","knife.jpg","tape-diamond-v2.png"];
  return <AbsoluteFill style={{background:"#5B97E8",padding:12}}><div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gridTemplateRows:"repeat(2,1fr)",height:"100%",gap:10}}>{files.map((file,i)=><div key={file} style={{overflow:"hidden",border:"5px solid white"}}><Img src={staticFile(`hidden-designs/${file}`)} style={{width:"100%",height:"100%",objectFit:"cover",transform:`scale(${1.08+i*.006})`}}/></div>)}</div><AbsoluteFill style={{background:"rgba(0,0,0,.48)"}}/><div style={{position:"absolute",left:120,right:120,top:280,textAlign:"center",color:"white",font:"1000 72px/.98 Arial",textShadow:"0 6px 0 #000"}}>HANGİSİNİ İLK KEZ DUYDUN?</div><div style={{position:"absolute",left:"50%",top:530,transform:"translateX(-50%) rotate(-1deg)",color:"#111",background:yellow,padding:"18px 30px",font:"1000 48px Arial",boxShadow:"10px 12px 0 #111"}}>YORUMA NUMARASINI YAZ</div></AbsoluteFill>;
};

export const ProvenStyleFull: React.FC = () => {
  const frame=useCurrentFrame();
  const {fps}=useVideoConfig();
  const timeMs=frame/fps*1000;
  const time=timeMs/1000;
  const chapter=chapters.find(c=>timeMs>=c.startMs&&timeMs<c.endMs)??chapters[chapters.length-1];
  return <AbsoluteFill style={{background:"#101621",fontFamily:"Arial,sans-serif"}}>
    {chapter.id==="hook"?<ProvenHook time={time}/>:chapter.id==="outro"?<Outro/>:<ChapterScene chapter={chapter} timeMs={timeMs}/>} 
    <div style={{position:"absolute",left:28,top:25,color:"white",font:"900 18px Arial",letterSpacing:1.4,textShadow:"0 2px 6px #000",zIndex:20}}>STRANGE THINGS LAB</div>
    <ProvenCaptions/>
    <Audio src={staticFile("hidden-designs/narration.mp3")}/>
    <Audio src={staticFile("hidden-designs/music-v2-future-tech.mp3")} volume={(audioFrame)=>interpolate(audioFrame,[0,42,300,340,6460,6596],[0,.078,.078,.056,.056,0],{extrapolateLeft:"clamp",extrapolateRight:"clamp"})}/>
  </AbsoluteFill>;
};
