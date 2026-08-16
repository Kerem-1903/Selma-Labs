import React from "react";
import {
  AbsoluteFill,
  Easing,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import data from "../../public/hidden-designs/data.json";
import {ArmPose, MascotMood, MascotRigV2} from "./MascotRigV2";
import {ProvenCaptions} from "./ProvenStylePreview";
import {ProvenStyleFull} from "./ProvenStyleFull";

type Chapter = {
  id: string;
  startMs: number;
  endMs: number;
};

const chapters = data.chapters as Chapter[];
const clamp = {extrapolateLeft: "clamp" as const, extrapolateRight: "clamp" as const};
const cyan = "#51DEFF";
const yellow = "#FFD42A";
const red = "#FF3E55";

const chapterGestures: Record<
  string,
  {left: ArmPose; right: ArmPose; mood: MascotMood}
> = {
  fuel: {left: "present", right: "thumbs-up", mood: "idea"},
  pen: {left: "present", right: "marker", mood: "explain"},
  keyboard: {left: "talk", right: "point-up", mood: "idea"},
  escalator: {left: "stop", right: "point-right", mood: "surprise"},
  airplane: {left: "relaxed", right: "pointer", mood: "explain"},
  microwave: {left: "present", right: "point-right", mood: "idea"},
  knife: {left: "stop", right: "pointer", mood: "explain"},
  tape: {left: "present", right: "thumbs-up", mood: "idea"},
};

const BoardHook: React.FC<{timeMs: number}> = ({timeMs}) => {
  const {fps} = useVideoConfig();
  const localMs = timeMs - 10450;
  const actionFrame = Math.max(0, Math.round((localMs / 1000) * fps));
  const enter = interpolate(localMs, [0, 380], [0, 1], {
    ...clamp,
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  const exit = interpolate(localMs, [5150, 5650], [1, 0], clamp);
  const line = interpolate(localMs, [1850, 2850], [0, 100], clamp);
  const reveal = interpolate(localMs, [2750, 3350], [0, 1], {
    ...clamp,
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  return (
    <AbsoluteFill
      style={{
        zIndex: 40,
        opacity: Math.min(enter, exit),
        background: "radial-gradient(circle at 22% 35%,#224965,#0A1829 58%,#030812)",
        overflow: "hidden",
      }}
    >
      <div style={{position: "absolute", inset: 0, opacity: 0.22, backgroundImage: "radial-gradient(circle,rgba(81,222,255,.38) 2px,transparent 3px)", backgroundSize: "58px 58px"}} />
      <div style={{position: "absolute", left: 38, top: -95}}>
        <MascotRigV2
          leftPose="present"
          rightPose="marker"
          previousLeftPose="relaxed"
          previousRightPose="relaxed"
          mood="explain"
          actionFrame={actionFrame}
          scale={0.72}
        />
      </div>
      <div
        style={{
          position: "absolute",
          left: 720,
          right: 88,
          top: 128,
          bottom: 154,
          padding: "52px 62px",
          borderRadius: 26,
          background: "linear-gradient(145deg,#152C2B,#0B1B1D)",
          border: "10px solid #D6B47A",
          boxShadow: "0 26px 60px rgba(0,0,0,.46), inset 0 0 45px rgba(255,255,255,.04)",
          color: "white",
          translate: `${(1 - enter) * 90}px 0`,
        }}
      >
        <div style={{font: "900 32px Arial", color: cyan, letterSpacing: 2}}>HER GÜN GÖRÜYORSUN</div>
        <div style={{marginTop: 22, font: "1000 94px/.88 Arial", letterSpacing: -4}}>
          8 KÜÇÜK
          <br />
          <span style={{color: yellow}}>DETAY</span>
        </div>
        <div style={{marginTop: 32, width: `${line}%`, maxWidth: 650, height: 11, borderRadius: 11, background: red, rotate: "-1deg", boxShadow: `0 0 18px ${red}`}} />
        <div style={{marginTop: 28, opacity: reveal, translate: `0 ${(1 - reveal) * 22}px`, font: "1000 47px/1.03 Arial"}}>
          GERÇEK AMAÇLARI
          <br />
          <span style={{color: cyan}}>GÖZÜNÜN ÖNÜNDE SAKLI</span>
        </div>
        <div style={{position: "absolute", right: 45, top: 40, width: 18, height: 18, borderRadius: "50%", background: yellow, boxShadow: `0 0 22px ${yellow}`}} />
        <div style={{position: "absolute", right: 78, top: 66, width: 11, height: 11, borderRadius: "50%", background: cyan, boxShadow: `0 0 18px ${cyan}`}} />
      </div>
      <div style={{position: "absolute", left: 28, top: 25, color: "white", font: "900 18px Arial", letterSpacing: 1.4}}>STRANGE THINGS LAB</div>
      <ProvenCaptions />
    </AbsoluteFill>
  );
};

const ChapterMascot: React.FC<{
  chapter: Chapter;
  chapterIndex: number;
  timeMs: number;
}> = ({chapter, chapterIndex, timeMs}) => {
  const {fps} = useVideoConfig();
  const duration = chapter.endMs - chapter.startMs;
  const startMs = chapter.startMs + duration * 0.75;
  const localMs = timeMs - startMs;
  const actionFrame = Math.max(0, Math.round((localMs / 1000) * fps));
  const enter = interpolate(localMs, [0, 420], [0, 1], {
    ...clamp,
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  const exit = interpolate(localMs, [duration * 0.25 - 550, duration * 0.25], [1, 0], clamp);
  // Sunucuyu aynı tarafta tutmak, bilgi kartının okunurluğunu ve serinin görsel dilini koruyor.
  const onLeft = true;
  const gesture = chapterGestures[chapter.id];
  if (!gesture || localMs < 0) return null;

  return (
    <div
      style={{
        position: "absolute",
        left: onLeft ? -56 : 1256,
        top: -112,
        width: 720,
        height: 820,
        zIndex: 30,
        opacity: Math.min(enter, exit),
        translate: `${(1 - enter) * (onLeft ? -95 : 95)}px 0`,
        filter: "drop-shadow(0 22px 28px rgba(0,0,0,.35))",
      }}
    >
      <div style={{position:"absolute",left:onLeft?40:20,top:292,width:510,height:420,borderRadius:"50% 50% 44% 44%",background:"radial-gradient(circle at 50% 45%,rgba(27,67,91,.94),rgba(5,15,27,.82) 72%)",border:`5px solid ${chapterIndex%3===0?yellow:chapterIndex%3===1?cyan:red}`,boxShadow:"0 18px 38px rgba(0,0,0,.38),inset 0 0 42px rgba(81,222,255,.12)"}}/>
      <div style={{position:"absolute",left:onLeft?56:36,top:650,zIndex:2,color:"#101621",background:chapterIndex%3===0?yellow:chapterIndex%3===1?cyan:red,padding:"8px 14px",font:"1000 22px Arial",boxShadow:"6px 7px 0 rgba(0,0,0,.65)",transform:"rotate(-2deg)"}}>LAB NOTU {chapterIndex+1}</div>
      <MascotRigV2
        leftPose={gesture.left}
        rightPose={gesture.right}
        previousLeftPose="relaxed"
        previousRightPose="relaxed"
        mood={gesture.mood}
        actionFrame={actionFrame}
        scale={0.6}
      />
    </div>
  );
};

const TapePromiseMascot: React.FC<{timeMs: number}> = ({timeMs}) => {
  const {fps} = useVideoConfig();
  const localMs = timeMs - 16150;
  const enter = interpolate(localMs, [0, 360], [0, 1], {...clamp, easing: Easing.bezier(0.16, 1, 0.3, 1)});
  const exit = interpolate(localMs, [3850, 4450], [1, 0], clamp);
  return (
    <div style={{position: "absolute", left: 1215, top: -118, width: 720, height: 820, zIndex: 30, opacity: Math.min(enter, exit), translate: `${(1 - enter) * 90}px 0`,filter:"drop-shadow(0 22px 28px rgba(0,0,0,.35))"}}>
      <MascotRigV2
        leftPose="present"
        rightPose="pointer"
        previousLeftPose="relaxed"
        previousRightPose="relaxed"
        mood="idea"
        actionFrame={Math.max(0, Math.round((localMs / 1000) * fps))}
        scale={0.59}
      />
    </div>
  );
};

const OutroMascot: React.FC<{timeMs: number}> = ({timeMs}) => {
  const {fps} = useVideoConfig();
  const localMs = timeMs - 206512;
  const enter = interpolate(localMs, [0, 500], [0, 1], {...clamp, easing: Easing.bezier(0.16, 1, 0.3, 1)});
  return (
    <div style={{position: "absolute", left: -48, top: -108, width: 720, height: 820, zIndex: 30, opacity: enter, translate: `${(1 - enter) * -90}px 0`,filter:"drop-shadow(0 22px 28px rgba(0,0,0,.35))"}}>
      <MascotRigV2
        leftPose="present"
        rightPose={localMs > 5600 ? "point-right" : "thumbs-up"}
        previousLeftPose="relaxed"
        previousRightPose="relaxed"
        mood="idea"
        actionFrame={Math.max(0, Math.round(((localMs % 5600) / 1000) * fps))}
        scale={0.62}
      />
    </div>
  );
};

export const HiddenDesignsMascotFull: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const timeMs = (frame / fps) * 1000;
  const chapter = chapters.find((item) => timeMs >= item.startMs && timeMs < item.endMs) ?? chapters[chapters.length - 1];
  const chapterIndex = chapters.filter((item) => !["hook", "outro"].includes(item.id)).findIndex((item) => item.id === chapter.id);

  return (
    <AbsoluteFill style={{background: "#081321", overflow: "hidden"}}>
      <ProvenStyleFull />
      {timeMs >= 10450 && timeMs < 16100 ? <BoardHook timeMs={timeMs} /> : null}
      {timeMs >= 16100 && timeMs < 20661 ? <TapePromiseMascot timeMs={timeMs} /> : null}
      {chapterIndex >= 0 ? <ChapterMascot chapter={chapter} chapterIndex={chapterIndex} timeMs={timeMs} /> : null}
      {chapter.id === "outro" ? <OutroMascot timeMs={timeMs} /> : null}
    </AbsoluteFill>
  );
};
