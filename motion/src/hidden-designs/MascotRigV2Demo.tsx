import React from "react";
import {
  AbsoluteFill,
  Easing,
  Interactive,
  interpolate,
  useCurrentFrame,
} from "remotion";
import {MascotAction, MascotActor} from "./MascotRigV2";

const beatLength = 85;
const actions: {action: MascotAction; label: string; detail: string}[] = [
  {action: "idle", label: "DİNLE", detail: "sakin bekleme ve nefes"},
  {action: "speak", label: "KONUŞ", detail: "kontrollü anlatım hareketi"},
  {action: "write-board", label: "TAHTAYA YAZ", detail: "işaretleyiciyle açıklama"},
  {action: "point-left", label: "SOLA İŞARET ET", detail: "görsel odağı sola taşı"},
  {action: "point-right", label: "SAĞA İŞARET ET", detail: "görsel odağı sağa taşı"},
  {action: "surprise", label: "ŞAŞIR", detail: "kısa ve okunaklı tepki"},
  {action: "think", label: "DÜŞÜN", detail: "soru veya olasılık anı"},
  {action: "doubt", label: "ŞÜPHELEN", detail: "iddiayı sorgulayan duruş"},
  {action: "laugh", label: "GÜL", detail: "hafif ve kontrollü neşe"},
  {action: "walk-in", label: "SAHNEYE GİR", detail: "yumuşak yatay giriş"},
  {action: "turn", label: "DÖN", detail: "iki boyutlu yön değişimi"},
  {action: "approach", label: "YAKLAŞ", detail: "önemli bilgiye vurgu"},
];

export const MascotRigV2Demo: React.FC = () => {
  const frame = useCurrentFrame();
  const index = Math.min(actions.length - 1, Math.floor(frame / beatLength));
  const previous = actions[Math.max(0, index - 1)];
  const beat = actions[index];
  const local = frame % beatLength;

  return (
    <AbsoluteFill
      style={{
        background: "radial-gradient(circle at 27% 28%,#244D68,#091728 58%,#030812)",
        fontFamily: "Arial,sans-serif",
        overflow: "hidden",
      }}
    >
      <Interactive.Div
        name="Moving laboratory grid"
        style={{
          position: "absolute",
          inset: -100,
          backgroundImage: "radial-gradient(circle,rgba(73,226,246,.18) 2px,transparent 3px)",
          backgroundSize: "58px 58px",
          translate: `${-frame * 0.16}px 0`,
          opacity: 0.32,
        }}
      />
      <Interactive.Div name="Mascot action" style={{position: "absolute", left: 72, top: 116}}>
        <MascotActor
          action={beat.action}
          previousAction={previous.action}
          actionFrame={local}
        />
      </Interactive.Div>
      <Interactive.Div
        name="Action description"
        style={{
          position: "absolute",
          left: 860,
          right: 90,
          top: 285,
          color: "white",
          opacity: interpolate(local, [0, 9, 68, 84], [0, 1, 1, 0], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
          translate: `${interpolate(local, [0, 14], [68, 0], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.bezier(0.16, 1, 0.3, 1),
          })}px 0`,
        }}
      >
        <div style={{font: "1000 72px/.96 Arial", letterSpacing: -2, textShadow: "0 7px 0 rgba(0,0,0,.5)"}}>
          {beat.label}
        </div>
        <div
          style={{
            display: "inline-block",
            marginTop: 30,
            color: "#07101B",
            background: index % 2 ? "#51E4F5" : "#FFD51F",
            padding: "13px 23px",
            font: "900 27px Arial",
            rotate: "-2deg",
            boxShadow: "8px 9px 0 rgba(0,0,0,.42)",
          }}
        >
          {beat.detail.toLocaleUpperCase("tr-TR")}
        </div>
      </Interactive.Div>
      <Interactive.Div
        name="Action library progress"
        style={{position: "absolute", left: 860, right: 110, bottom: 135, height: 9, borderRadius: 9, background: "rgba(255,255,255,.12)"}}
      >
        <div style={{height: "100%", width: `${frame / (beatLength * actions.length) * 100}%`, background: "linear-gradient(90deg,#51E4F5,#FFD51F,#FF5364)", borderRadius: 9}} />
      </Interactive.Div>
    </AbsoluteFill>
  );
};
