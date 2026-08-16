import React from "react";
import {AbsoluteFill, OffthreadVideo, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from "remotion";
import type {SceneSpec} from "../types";

const fallbackGradients = [
  "radial-gradient(circle at 30% 25%, #164e63 0%, #06101c 45%, #02040a 100%)",
  "radial-gradient(circle at 70% 30%, #312e81 0%, #09101f 50%, #02040a 100%)",
  "radial-gradient(circle at 50% 65%, #155e75 0%, #07111d 45%, #02040a 100%)",
];

export const SceneLayer: React.FC<{scene: SceneSpec; index: number}> = ({scene, index}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const progress = interpolate(frame, [0, Math.max(1, scene.durationFrames - 1)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const interruptBoost = scene.patternInterrupt === "scale_or_layout_change" ? 0.035 : 0;
  const zoomAmount = (scene.motion === "fast-paced" ? 0.11 : scene.motion === "slow-motion" ? 0.035 : 0.06) + interruptBoost;
  const direction = index % 2 === 0 ? 1 : -1;
  const settle = spring({frame, fps, config: {damping: 22, stiffness: 110}});
  const scale = 1.04 + progress * zoomAmount;
  const translateX = direction * interpolate(progress, [0, 1], [-18, 18]);
  const entranceX = scene.transition === "push" ? interpolate(settle, [0, 1], [120 * direction, 0]) : 0;
  const opacity = scene.transition === "impact_flash"
    ? interpolate(frame, [0, 2, 5], [0.25, 1, 1], {extrapolateRight: "clamp"})
    : 1;
  const source = scene.source
    ? /^https?:\/\//i.test(scene.source)
      ? scene.source
      : staticFile(scene.source)
    : null;

  return (
    <AbsoluteFill style={{overflow: "hidden", background: fallbackGradients[index % fallbackGradients.length]}}>
      <AbsoluteFill
        style={{
          opacity,
          transform: `translateX(${entranceX}px) translateX(${translateX}px) scale(${scale})`,
        }}
      >
        {source ? (
          <OffthreadVideo
            src={source}
            trimBefore={scene.sourceStartFrame ?? 0}
            muted
            style={{width: "100%", height: "100%", objectFit: "cover"}}
          />
        ) : (
          <AbsoluteFill style={{background: fallbackGradients[index % fallbackGradients.length]}} />
        )}
      </AbsoluteFill>
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(180deg, rgba(0,0,0,.15) 0%, transparent 45%, rgba(2,4,10,.52) 76%, rgba(2,4,10,.97) 91%, #02040A 100%)",
        }}
      />
    </AbsoluteFill>
  );
};
