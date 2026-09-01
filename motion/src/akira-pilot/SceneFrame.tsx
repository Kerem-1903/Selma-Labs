import React from "react";
import {
  AbsoluteFill,
  CanvasImage,
  Easing,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";
import {RainLayer} from "./RainLayer";

type SceneFrameProps = {
  asset: string;
  durationInFrames: number;
  fadeIn?: number;
  fadeOut?: number;
  fromScale: number;
  toScale: number;
  fromX?: number;
  toX?: number;
  fromY?: number;
  toY?: number;
  rainIntensity?: number;
  redPulse?: boolean;
};

export const SceneFrame: React.FC<SceneFrameProps> = ({
  asset,
  durationInFrames,
  fadeIn = 0,
  fadeOut = 0,
  fromScale,
  toScale,
  fromX = 0,
  toX = 0,
  fromY = 0,
  toY = 0,
  rainIntensity = 1,
  redPulse = false,
}) => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill
      style={{
        backgroundColor: "#05080d",
        opacity:
          (fadeIn > 0
            ? interpolate(frame, [0, fadeIn], [0, 1], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              })
            : 1) *
          (fadeOut > 0
            ? interpolate(
                frame,
                [durationInFrames - fadeOut, durationInFrames],
                [1, 0],
                {extrapolateLeft: "clamp", extrapolateRight: "clamp"},
              )
            : 1),
        overflow: "hidden",
      }}
    >
      <CanvasImage
        src={staticFile(`akira-pilot/${asset}`)}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          scale: interpolate(frame, [0, durationInFrames], [fromScale, toScale], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.bezier(0.22, 0.7, 0.2, 1),
            output: "perceptual-scale",
          }),
          translate: interpolate(
            frame,
            [0, durationInFrames],
            [`${fromX}px ${fromY}px`, `${toX}px ${toY}px`],
            {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.bezier(0.22, 0.7, 0.2, 1),
            },
          ),
        }}
      />
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(180deg, rgba(2,5,10,0.08), transparent 48%, rgba(1,3,8,0.3)), radial-gradient(circle at center, transparent 52%, rgba(0,0,0,0.3))",
        }}
      />
      {redPulse ? (
        <AbsoluteFill
          style={{
            opacity: interpolate(frame, [0, 18, 46, durationInFrames], [0.02, 0.13, 0.04, 0.1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            }),
            background:
              "radial-gradient(circle at 75% 40%, rgba(255,24,38,0.34), transparent 34%)",
            mixBlendMode: "screen",
          }}
        />
      ) : null}
      <RainLayer intensity={rainIntensity} />
    </AbsoluteFill>
  );
};
