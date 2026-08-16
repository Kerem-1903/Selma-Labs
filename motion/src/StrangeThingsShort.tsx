import React from "react";
import {AbsoluteFill, Sequence, interpolate, useCurrentFrame} from "remotion";
import type {StrangeThingsProps} from "./types";
import {AnatomyCallout} from "./components/AnatomyCallout";
import {BrandBug} from "./components/BrandBug";
import {BrandSting} from "./components/BrandSting";
import {HookBurst} from "./components/HookBurst";
import {KineticCaptions} from "./components/KineticCaptions";
import {LoopClosure} from "./components/LoopClosure";
import {PayoffCta} from "./components/PayoffCta";
import {SceneLayer} from "./components/SceneLayer";
import {SelfHealingDiagram} from "./components/SelfHealingDiagram";
import {SemanticTransition} from "./components/SemanticTransition";

const defaultPalette = {
  background: "#02040A",
  foreground: "#FFFFFF",
  active: "#FFD700",
  science: "#22D3EE",
  danger: "#FF3B5C",
};

export const StrangeThingsShort: React.FC<StrangeThingsProps> = (props) => {
  const frame = useCurrentFrame();
  const palette = {...defaultPalette, ...(props.palette ?? {})};
  const brandStartFrame = props.brandStartFrame ?? 27;
  const brandDurationFrames = Math.max(1, props.brandDurationFrames ?? 29);
  const brandEndFrame = brandStartFrame + brandDurationFrames;
  const ctaText = props.ctaText?.trim() ?? "";
  const ctaStartFrame = props.ctaStartFrame ?? Math.max(0, props.durationInFrames - 40);
  const loopDurationFrames = 8;
  const loopStartFrame = Math.max(0, props.durationInFrames - loopDurationFrames);
  const ctaDurationFrames = Math.max(1, loopStartFrame - ctaStartFrame);
  const endingOpacity = interpolate(
    frame,
    [props.durationInFrames - 16, props.durationInFrames - 1],
    [0, 0.24],
    {extrapolateLeft: "clamp", extrapolateRight: "clamp"},
  );

  return (
    <AbsoluteFill style={{background: palette.background}}>
      {props.scenes.map((scene, index) => (
        <React.Fragment key={`${scene.startFrame}-${index}`}>
          <Sequence from={scene.startFrame} durationInFrames={scene.durationFrames} premountFor={15}>
            <SceneLayer scene={scene} index={index} />
            {scene.diagramKind === "self_healing" ? (
              <SelfHealingDiagram science={palette.science} active={palette.active} />
            ) : null}
            {scene.labels.length > 0 ? <AnatomyCallout labels={scene.labels} science={palette.science} /> : null}
          </Sequence>
          {index > 0 && scene.transition !== "hard" ? (
            <Sequence from={Math.max(0, scene.startFrame - 3)} durationInFrames={9}>
              <SemanticTransition kind={scene.transition} science={palette.science} />
            </Sequence>
          ) : null}
        </React.Fragment>
      ))}

      <Sequence from={0} durationInFrames={30}>
        <HookBurst text={props.hookText} active={palette.active} />
      </Sequence>
      <Sequence from={brandStartFrame} durationInFrames={brandDurationFrames}>
        <BrandSting
          text={props.brandSignature}
          science={palette.science}
          active={palette.active}
          durationFrames={brandDurationFrames}
        />
      </Sequence>
      {ctaStartFrame > brandEndFrame ? (
        <Sequence from={brandEndFrame} durationInFrames={ctaStartFrame - brandEndFrame}>
          <BrandBug science={palette.science} active={palette.active} />
        </Sequence>
      ) : null}
      <KineticCaptions cues={props.captions} foreground={palette.foreground} active={palette.active} />
      {ctaText ? (
        <Sequence from={ctaStartFrame} durationInFrames={ctaDurationFrames}>
          <PayoffCta
            text={ctaText}
            active={palette.active}
            science={palette.science}
            durationFrames={ctaDurationFrames}
          />
        </Sequence>
      ) : null}

      {props.scenes[0] ? (
        <Sequence from={loopStartFrame} durationInFrames={loopDurationFrames}>
          <LoopClosure scene={props.scenes[0]} />
        </Sequence>
      ) : null}

      <AbsoluteFill
        style={{
          pointerEvents: "none",
          opacity: endingOpacity,
          background: `radial-gradient(circle at center, transparent 35%, ${palette.science}55 140%)`,
        }}
      />
      <AbsoluteFill
        style={{
          pointerEvents: "none",
          mixBlendMode: "soft-light",
          opacity: 0.14,
          backgroundImage: "repeating-linear-gradient(0deg, rgba(255,255,255,.025) 0px, rgba(255,255,255,.025) 1px, transparent 1px, transparent 4px)",
        }}
      />
    </AbsoluteFill>
  );
};
