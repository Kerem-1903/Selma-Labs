import React from "react";
import {Video} from "@remotion/media";
import {AbsoluteFill, Easing, Interactive, interpolate, staticFile, useCurrentFrame} from "remotion";

export const FootageScene: React.FC<{file: string; trimBefore?: number; label?: string}> = ({file, trimBefore = 0, label}) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill>
      <Video
        src={staticFile(`phantom-vibration/footage/${file}.mp4`)}
        muted
        trimBefore={trimBefore}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          scale: interpolate(frame, [0, 180], [1.02, 1.09], {extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.linear}),
          filter: "brightness(.72) contrast(1.12) saturate(.78)",
        }}
      />
      <AbsoluteFill style={{background: "linear-gradient(180deg,rgba(1,4,10,.45),transparent 28%,transparent 55%,rgba(1,4,10,.88) 92%),linear-gradient(90deg,rgba(2,7,16,.26),transparent 55%)"}} />
      {label && <Interactive.Div name="Sahne etiketi" style={{position: "absolute", top: 145, left: 72, padding: "12px 18px", borderLeft: "7px solid #FFD52A", background: "rgba(3,7,14,.78)", color: "white", font: "900 28px Arial", letterSpacing: 2}}>{label}</Interactive.Div>}
    </AbsoluteFill>
  );
};
