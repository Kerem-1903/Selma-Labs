import React, {useMemo} from "react";
import {Video} from "@remotion/media";
import {
  AbsoluteFill,
  Audio,
  Easing,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import data from "../../public/earth-stop/data.json";
import {MascotMotion, MascotRigV2} from "../hidden-designs/MascotRigV2";

type Chapter = {id: string; title: string; startMs: number; endMs: number};
type Word = {text: string; startMs: number; endMs: number};
const chapters = data.chapters as Chapter[];
const words = data.words as Word[];

const COLORS = {
  ink: "#050A12",
  yellow: "#FFD42A",
  cyan: "#52E5FF",
  red: "#FF4057",
  white: "#F8FBFF",
};

const Caption: React.FC<{now: number}> = ({now}) => {
  const active = useMemo(() => {
    const index = words.findIndex((word) => now >= word.startMs && now <= word.endMs + 110);
    if (index < 0) return [];
    const start = Math.floor(index / 6) * 6;
    return words.slice(start, start + 6);
  }, [now]);
  if (!active.length) return null;
  return (
    <div
      style={{
        position: "absolute",
        left: 160,
        right: 160,
        bottom: 24,
        zIndex: 100,
        display: "flex",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          maxWidth: 1460,
          padding: "12px 24px 15px",
          borderRadius: 15,
          background: "rgba(0,4,10,.82)",
          borderBottom: `5px solid ${COLORS.yellow}`,
          textAlign: "center",
          font: "1000 39px/1.15 Arial",
          textTransform: "uppercase",
          letterSpacing: 0.3,
          boxShadow: "0 12px 32px rgba(0,0,0,.48)",
        }}
      >
        {active.map((word, index) => {
          const isActive = now >= word.startMs && now <= word.endMs;
          return (
            <React.Fragment key={`${word.startMs}-${index}`}>
              <span style={{color: isActive ? COLORS.yellow : COLORS.white}}>{word.text}</span>
              {index < active.length - 1 ? " " : ""}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};

const Footage: React.FC<{
  name: string;
  local: number;
  dim?: number;
  position?: string;
  tint?: string;
  shake?: boolean;
}> = ({name, local, dim = 0.48, position = "center", tint = "#06101D", shake = false}) => {
  const intro = interpolate(local, [0, 420], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.quad),
  });
  const zoom = 1.04 + Math.min(local / 50000, 0.08);
  const x = shake ? Math.sin(local * 0.13) * 13 : 0;
  const y = shake ? Math.sin(local * 0.19) * 7 : 0;
  return (
    <AbsoluteFill style={{background: COLORS.ink, overflow: "hidden"}}>
      <Video
        src={staticFile(`earth-stop/footage/${name}.mp4`)}
        loop
        muted
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          objectPosition: position,
          transform: `translate(${x}px, ${y}px) scale(${zoom})`,
          opacity: intro,
        }}
      />
      <AbsoluteFill style={{background: `linear-gradient(90deg, ${tint}F5 0%, ${tint}B8 37%, ${tint}22 72%), rgba(0,0,0,${dim})`}} />
      <AbsoluteFill style={{background: "linear-gradient(180deg,rgba(0,0,0,.45),transparent 22%,transparent 72%,rgba(0,0,0,.7))"}} />
    </AbsoluteFill>
  );
};

const Host: React.FC<{
  motion: MascotMotion;
  local: number;
  side?: "left" | "right";
  scale?: number;
  top?: number;
}> = ({motion, local, side = "left", scale = 0.54, top = 230}) => {
  const pose =
    motion === "write"
      ? "marker"
      : motion === "recoil"
        ? "stop"
        : motion === "celebrate"
          ? "thumbs-up"
          : motion === "wave" || motion === "peek"
            ? "present"
            : "pointer";
  const entrance = interpolate(local, [0, 520], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  return (
    <div
      style={{
        position: "absolute",
        left: side === "left" ? -34 : 1330,
        top,
        width: 650,
        height: 740,
        zIndex: 48,
        filter: "drop-shadow(0 24px 30px rgba(0,0,0,.68))",
        opacity: entrance,
        translate: `${side === "left" ? (1 - entrance) * -28 : (1 - entrance) * 28}px 0`,
      }}
    >
      <MascotRigV2
        leftPose={motion === "celebrate" ? "thumbs-up" : "present"}
        rightPose={pose}
        mood={motion === "recoil" ? "surprise" : motion === "celebrate" ? "idea" : "explain"}
        motion={motion}
        actionFrame={Math.round(local * 0.03)}
        scale={scale}
      />
    </div>
  );
};

const Kicker: React.FC<{children: React.ReactNode; accent?: string}> = ({children, accent = COLORS.yellow}) => (
  <div
    style={{
      display: "inline-flex",
      alignItems: "center",
      gap: 11,
      background: "rgba(0,0,0,.72)",
      color: COLORS.white,
      padding: "9px 16px",
      font: "1000 21px Arial",
      letterSpacing: 2.2,
      borderLeft: `8px solid ${accent}`,
    }}
  >
    {children}
  </div>
);

const Title: React.FC<{children: React.ReactNode; progress: number; width?: number}> = ({children, progress, width = 1080}) => {
  const shown = interpolate(progress, [0, 0.065], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  return (
    <div
      style={{
        color: COLORS.white,
        font: "1000 76px/.96 Arial",
        maxWidth: width,
        opacity: shown,
        transform: `translateX(${(1 - shown) * -45}px)`,
        textShadow: "0 6px 18px rgba(0,0,0,.8)",
      }}
    >
      {children}
    </div>
  );
};

const Metric: React.FC<{value: string; label: string; accent?: string; compact?: boolean}> = ({
  value,
  label,
  accent = COLORS.yellow,
  compact = false,
}) => (
  <div
    style={{
      background: "rgba(3,10,18,.88)",
      borderLeft: `8px solid ${accent}`,
      padding: compact ? "17px 22px" : "21px 28px",
      boxShadow: "0 16px 36px rgba(0,0,0,.48)",
      backdropFilter: "blur(7px)",
    }}
  >
    <div style={{font: `1000 ${compact ? 53 : 68}px Arial`, color: accent}}>{value}</div>
    <div style={{font: `900 ${compact ? 23 : 27}px Arial`, color: COLORS.white, marginTop: 3}}>{label}</div>
  </div>
);

const SpeedLines: React.FC<{local: number; color?: string}> = ({local, color = COLORS.cyan}) => (
  <>
    {[0, 1, 2, 3, 4, 5].map((index) => (
      <div
        key={index}
        style={{
          position: "absolute",
          left: -430 + ((local * (0.46 + index * 0.035) + index * 347) % 2600),
          top: 210 + index * 125,
          width: 510,
          height: 9,
          borderRadius: 20,
          background: `linear-gradient(90deg,transparent,${color},transparent)`,
          opacity: 0.7,
          filter: `drop-shadow(0 0 10px ${color})`,
        }}
      />
    ))}
  </>
);

const Scene: React.FC<{chapter: Chapter; now: number}> = ({chapter, now}) => {
  const local = now - chapter.startMs;
  const duration = chapter.endMs - chapter.startMs;
  const progress = local / duration;

  if (chapter.id === "hook") {
    const countdown = Math.max(0, 5 - Math.floor(local / 1000));
    const pulse = 1 + Math.sin(local / 150) * 0.035;
    return (
      <AbsoluteFill style={{overflow: "hidden"}}>
        <Footage name="earth" local={local} dim={0.2} tint="#090716" position="center" shake={local > 5200} />
        <div style={{position: "absolute", left: 82, top: 105}}>
          <Kicker>5 SANİYELİK DENEY</Kicker>
          <div style={{height: 26}} />
          <Title progress={progress} width={880}>
            DÜNYA<br /><span style={{color: COLORS.red}}>DÖNMEYİ</span><br />DURDURSA?
          </Title>
        </div>
        <div
          style={{
            position: "absolute",
            left: 875,
            top: 360,
            width: 205,
            height: 205,
            borderRadius: "50%",
            display: "grid",
            placeItems: "center",
            background: "radial-gradient(circle at 35% 25%,#FF7182,#E30A31 55%,#7A061B)",
            border: "14px solid #620615",
            font: "1000 92px Arial",
            color: "white",
            boxShadow: "0 0 0 10px rgba(255,255,255,.14),0 0 70px #FF274F",
            transform: `scale(${pulse})`,
          }}
        >
          {countdown}
        </div>
        <Host motion={local < 4500 ? "write" : "recoil"} local={local} />
      </AbsoluteFill>
    );
  }

  if (chapter.id === "speed") {
    return (
      <AbsoluteFill style={{overflow: "hidden"}}>
        <Footage name={progress < 0.55 ? "city" : "earth"} local={local} dim={0.25} tint="#051221" position="center 44%" />
        <SpeedLines local={local} />
        <div style={{position: "absolute", left: 80, top: 94}}>
          <Kicker accent={COLORS.cyan}>SİZ ŞU AN HAREKET EDİYORSUNUZ</Kicker>
          <div style={{height: 24}} />
          <Title progress={progress}>NE KADAR HIZLI?</Title>
          <div style={{height: 50}} />
          <div style={{display: "grid", gap: 16, width: 725}}>
            <Metric value="1.670 km/sa" label="EKVATOR YÜZEY HIZI" />
            <Metric value="≈ SES HIZININ 1,35 KATI" label="HAREKETSİZ OTURURKEN" accent={COLORS.cyan} compact />
          </div>
        </div>
        <Host motion="scan" local={local} side="right" scale={0.45} top={360} />
      </AbsoluteFill>
    );
  }

  if (chapter.id === "first-second") {
    const arrowTravel = interpolate((local % 2600) / 2600, [0, 1], [-80, 630]);
    return (
      <AbsoluteFill style={{overflow: "hidden"}}>
        <Footage name={progress < 0.68 ? "city" : "rubble"} local={local} dim={0.35} tint="#180610" shake />
        <div style={{position: "absolute", left: 80, top: 95}}>
          <Kicker accent={COLORS.red}>0,001 SANİYE SONRA</Kicker>
          <div style={{height: 24}} />
          <Title progress={progress}>YER DURUR.<br /><span style={{color: COLORS.yellow}}>SİZ DURMAZSINIZ.</span></Title>
        </div>
        <div style={{position: "absolute", left: 410 + arrowTravel, top: 520, color: COLORS.yellow, font: "1000 160px Arial", textShadow: "0 0 24px #000"}}>→</div>
        <div style={{position: "absolute", left: 480, top: 700, background: "rgba(0,0,0,.8)", color: "white", borderLeft: `8px solid ${COLORS.red}`, padding: "18px 24px", font: "1000 38px Arial"}}>HER ŞEY DOĞUYA DEVAM EDER</div>
        <Host motion="recoil" local={local} scale={0.5} />
      </AbsoluteFill>
    );
  }

  if (chapter.id === "atmosphere") {
    return (
      <AbsoluteFill style={{overflow: "hidden"}}>
        <Footage name="storm" local={local} dim={0.26} tint="#06172B" shake={local > 12000} />
        <SpeedLines local={local} color="#D7F7FF" />
        <div style={{position: "absolute", left: 80, top: 95}}>
          <Kicker accent={COLORS.cyan}>AMA HAVA HÂLÂ HAREKETLİ</Kicker>
          <div style={{height: 24}} />
          <Title progress={progress}>ATMOSFER<br /><span style={{color: COLORS.cyan}}>DURMUYOR</span></Title>
          <div style={{height: 48}} />
          <Metric value="SESÜSTÜ" label="YÜZEYE GÖRE RÜZGÂR" accent={COLORS.cyan} />
        </div>
        <Host motion="recoil" local={local} side="right" scale={0.46} top={350} />
      </AbsoluteFill>
    );
  }

  if (chapter.id === "oceans") {
    const revealFlood = progress > 0.58;
    return (
      <AbsoluteFill style={{overflow: "hidden"}}>
        <Footage name={revealFlood ? "flood" : "ocean"} local={local} dim={0.28} tint="#031A27" shake={revealFlood} />
        <div style={{position: "absolute", left: 80, top: 95}}>
          <Kicker accent={COLORS.cyan}>{revealFlood ? "KIYI ŞERİTLERİ" : "SUYUN MOMENTUMU"}</Kicker>
          <div style={{height: 24}} />
          <Title progress={progress}>OKYANUSLAR<br /><span style={{color: COLORS.cyan}}>DEVAM EDİYOR</span></Title>
          <div style={{height: 50}} />
          <Metric value="5 SANİYE" label="YIKICI DALGALARA YETER" accent={COLORS.cyan} />
        </div>
        <Host motion="peek" local={local} side="right" scale={0.47} top={355} />
      </AbsoluteFill>
    );
  }

  if (chapter.id === "latitude") {
    return (
      <AbsoluteFill style={{overflow: "hidden"}}>
        <Footage name="polar" local={local} dim={0.16} tint="#071523" />
        <div style={{position: "absolute", left: 80, top: 95}}>
          <Kicker accent={COLORS.cyan}>HIZ, ENLEME GÖRE DEĞİŞİR</Kicker>
          <div style={{height: 24}} />
          <Title progress={progress}>NERESİ DAHA<br />GÜVENLİ?</Title>
        </div>
        <div style={{position: "absolute", left: 550, right: 75, top: 250, display: "grid", gap: 14}}>
          <Metric value="EKVATOR" label="EN YÜKSEK HIZ" accent={COLORS.red} compact />
          <Metric value="60° ENLEM" label="YAKLAŞIK YARI HIZ" compact />
          <Metric value="KUTUP" label="NEREDEYSE SIFIR" accent={COLORS.cyan} compact />
        </div>
        <Host motion="scan" local={local} scale={0.48} top={440} />
      </AbsoluteFill>
    );
  }

  if (chapter.id === "weight-space") {
    return (
      <AbsoluteFill style={{overflow: "hidden"}}>
        <Footage name={progress < 0.72 ? "satellite" : "earth"} local={local} dim={0.18} tint="#080B20" position="center" />
        <div style={{position: "absolute", left: 80, top: 95}}>
          <Kicker>EN ÇOK KARIŞTIRILAN KISIM</Kicker>
          <div style={{height: 24}} />
          <Title progress={progress}>UZAYA<br /><span style={{color: COLORS.red}}>FIRLAMIYORUZ</span></Title>
          <div style={{height: 44}} />
          <div style={{display: "grid", gap: 14, width: 650}}>
            <Metric value="11,2 km/sn" label="DÜNYA'DAN KAÇIŞ HIZI" compact />
            <Metric value="0,465 km/sn" label="EKVATOR DÖNÜŞ HIZI" accent={COLORS.cyan} compact />
          </div>
        </div>
        <Host motion="write" local={local} side="right" scale={0.44} top={390} />
      </AbsoluteFill>
    );
  }

  if (chapter.id === "restart") {
    const count = Math.max(0, 5 - Math.floor(local / 1000));
    return (
      <AbsoluteFill style={{overflow: "hidden"}}>
        <Footage name={progress < 0.55 ? "rubble" : "city"} local={local} dim={0.32} tint="#1A050B" shake />
        <div style={{position: "absolute", left: 80, top: 95}}>
          <Kicker accent={COLORS.red}>BEŞİNCİ SANİYE</Kicker>
          <div style={{height: 24}} />
          <Title progress={progress}>SONRA<br /><span style={{color: COLORS.red}}>İKİNCİ DARBE</span></Title>
        </div>
        <div style={{position: "absolute", left: 850, top: 350, color: COLORS.yellow, font: "1000 190px Arial", textShadow: "0 10px 24px #000"}}>{count}</div>
        <div style={{position: "absolute", left: 660, top: 650, background: "rgba(0,0,0,.82)", color: "white", borderLeft: `9px solid ${COLORS.red}`, padding: "18px 25px", font: "1000 42px Arial"}}>DÜNYA YENİDEN DÖNÜYOR</div>
        <Host motion="recoil" local={local} side="right" scale={0.47} top={350} />
      </AbsoluteFill>
    );
  }

  if (chapter.id === "survival") {
    const items = ["KUTBA YAKIN", "KIYIDAN UZAK", "YER ALTINDA", "BAĞIMSIZ ENERJİ"];
    return (
      <AbsoluteFill style={{overflow: "hidden"}}>
        <Footage name="tunnel" local={local} dim={0.18} tint="#071810" position="center" />
        <div style={{position: "absolute", left: 80, top: 95}}>
          <Kicker accent="#55F2AD">EN İYİ SENARYO</Kicker>
          <div style={{height: 24}} />
          <Title progress={progress}>HAYATTA KALMA<br /><span style={{color: "#55F2AD"}}>ŞANSINIZ</span></Title>
        </div>
        <div style={{position: "absolute", left: 610, top: 260, display: "grid", gridTemplateColumns: "repeat(2,470px)", gap: 15}}>
          {items.map((item, index) => {
            const shown = interpolate(progress, [0.14 + index * 0.07, 0.21 + index * 0.07], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp"});
            return <div key={item} style={{background: index === 3 ? COLORS.yellow : "#55F2AD", color: COLORS.ink, padding: "23px 25px", font: "1000 36px Arial", boxShadow: "8px 9px 0 rgba(0,0,0,.75)", transform: `translateY(${(1 - shown) * 25}px)`, opacity: shown}}>✓ {item}</div>;
          })}
        </div>
        <Host motion="write" local={local} scale={0.48} top={430} />
      </AbsoluteFill>
    );
  }

  return (
    <AbsoluteFill style={{overflow: "hidden"}}>
      <Footage name="earth" local={local} dim={0.18} tint="#071020" position="center" />
      <div style={{position: "absolute", left: 535, right: 70, top: 145, textAlign: "center"}}>
        <Kicker>SONUÇ</Kicker>
        <div style={{height: 26}} />
        <Title progress={progress}>DÜĞMEYİ<br /><span style={{color: COLORS.yellow}}>KİLİTLİYORUZ.</span></Title>
        <div style={{marginTop: 48, background: COLORS.red, color: "white", padding: "20px 28px", font: "1000 39px Arial", boxShadow: "10px 12px 0 #000"}}>AY MI YOK OLSUN, GÜNEŞ Mİ SÖNSÜN?</div>
      </div>
      <Host motion="celebrate" local={local} scale={0.58} top={250} />
    </AbsoluteFill>
  );
};

export const EarthStopVideo: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const now = (frame / fps) * 1000;
  const chapter = chapters.find((item) => now >= item.startMs && now < item.endMs) ?? chapters[chapters.length - 1];
  return (
    <AbsoluteFill style={{fontFamily: "Arial, sans-serif", background: COLORS.ink}}>
      <Scene chapter={chapter} now={now} />
      <div style={{position: "absolute", left: 28, top: 23, zIndex: 110, color: "white", font: "900 18px Arial", letterSpacing: 1.5, textShadow: "0 2px 7px #000"}}>STRANGE THINGS LAB</div>
      <Caption now={now} />
      <Audio src={staticFile("earth-stop/narration.mp3")} />
      <Audio
        src={staticFile("hidden-designs/music-v2-future-tech.mp3")}
        volume={(musicFrame) => interpolate(musicFrame, [0, 45, 300, 360, 11950, 12058], [0, 0.06, 0.06, 0.045, 0.045, 0], {extrapolateLeft: "clamp", extrapolateRight: "clamp"})}
      />
    </AbsoluteFill>
  );
};
