import React from "react";
import {
  Easing,
  Img,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

export type ArmPose =
  | "relaxed"
  | "point-up"
  | "point-right"
  | "present"
  | "stop"
  | "thumbs-up"
  | "fist"
  | "marker"
  | "pointer"
  | "pinch"
  | "surprise"
  | "talk";

export type MascotMood =
  | "calm"
  | "explain"
  | "idea"
  | "surprise"
  | "think"
  | "happy"
  | "doubt";
export type MascotMotion =
  | "idle"
  | "wave"
  | "scan"
  | "write"
  | "recoil"
  | "celebrate"
  | "peek"
  | "talk"
  | "think"
  | "doubt"
  | "laugh"
  | "walk"
  | "turn"
  | "approach";

export type MascotAction =
  | "idle"
  | "speak"
  | "write-board"
  | "point-left"
  | "point-right"
  | "surprise"
  | "think"
  | "doubt"
  | "laugh"
  | "walk-in"
  | "turn"
  | "approach";

type MascotActionPreset = {
  leftPose: ArmPose;
  rightPose: ArmPose;
  mood: MascotMood;
  motion: MascotMotion;
};

export const MASCOT_ACTION_PRESETS: Record<MascotAction, MascotActionPreset> = {
  idle: {leftPose: "relaxed", rightPose: "present", mood: "calm", motion: "idle"},
  speak: {leftPose: "talk", rightPose: "present", mood: "explain", motion: "talk"},
  "write-board": {leftPose: "present", rightPose: "marker", mood: "explain", motion: "write"},
  "point-left": {leftPose: "point-right", rightPose: "relaxed", mood: "explain", motion: "scan"},
  "point-right": {leftPose: "relaxed", rightPose: "point-right", mood: "explain", motion: "scan"},
  surprise: {leftPose: "stop", rightPose: "surprise", mood: "surprise", motion: "recoil"},
  think: {leftPose: "pinch", rightPose: "relaxed", mood: "think", motion: "think"},
  doubt: {leftPose: "stop", rightPose: "pinch", mood: "doubt", motion: "doubt"},
  laugh: {leftPose: "thumbs-up", rightPose: "present", mood: "happy", motion: "laugh"},
  "walk-in": {leftPose: "relaxed", rightPose: "present", mood: "calm", motion: "walk"},
  turn: {leftPose: "relaxed", rightPose: "present", mood: "calm", motion: "turn"},
  approach: {leftPose: "present", rightPose: "point-up", mood: "idea", motion: "approach"},
};

const asset = (name: string) =>
  staticFile(`hidden-designs/maskot-rig-v2/${name}.png`);

const colorFilter = (side: "left" | "right") => {
  const glow = side === "right"
    ? "drop-shadow(0 0 13px rgba(255,213,31,.42))"
    : "drop-shadow(0 0 13px rgba(81,228,245,.46))";
  return `${glow} drop-shadow(0 18px 16px rgba(0,0,0,.25))`;
};

const Arm: React.FC<{
  pose: ArmPose;
  previousPose: ArmPose;
  side: "left" | "right";
  progress: number;
  energy: number;
  motion: MascotMotion;
  gestureSeconds: number;
}> = ({pose, previousPose, side, progress, energy, motion, gestureSeconds}) => {
  const isLeft = side === "left";
  const baseLeft = isLeft ? -100 : 450;
  const baseTop = 307;
  const baseRotation = isLeft ? 10 : -2;
  const anticipation = interpolate(progress, [0, 0.22, 0.62, 1], [0, isLeft ? 10 : -10, isLeft ? -3 : 3, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.2, 0.8, 0.2, 1),
  });
  // A deliberate gesture followed by a rest reads more naturally than a
  // continuously oscillating arm. Each gesture is eased in and out.
  const gestureWindow = gestureSeconds % 4.4;
  const gesture = gestureWindow < 1.45
    ? Math.sin((gestureWindow / 1.45) * Math.PI)
    : 0;
  const wave = motion === "wave" && !isLeft ? gesture * 7 : 0;
  const scan = motion === "scan" && !isLeft ? gesture * -5 : 0;
  const writing = motion === "write" && !isLeft
    ? Math.sin(gestureWindow * Math.PI * 3.2) * gesture * 2.8
    : 0;
  const celebrate = motion === "celebrate" ? gesture * (isLeft ? -4 : 4) : 0;
  const conversational = motion === "talk" ? gesture * (isLeft ? -2.5 : 2.5) : 0;
  const laugh = motion === "laugh" ? Math.sin(gestureWindow * Math.PI * 2.2) * gesture * (isLeft ? -3 : 3) : 0;

  const shared = {
    position: "absolute" as const,
    left: baseLeft,
    top: baseTop,
    width: 360,
    height: 321,
    objectFit: "contain" as const,
    transformOrigin: isLeft ? "79% 18%" : "21% 18%",
    rotate: `${baseRotation + anticipation + wave + scan + writing + celebrate + conversational + laugh}deg`,
    scale: `${isLeft ? -1 : 1} 1`,
    zIndex: 3,
  };

  return (
    <>
      <Img
        src={asset(`arm-${previousPose}-${isLeft ? "cyan" : "yellow"}`)}
        style={{
          ...shared,
          opacity: 1 - Math.min(1, progress * 1.25),
          filter: colorFilter(side),
        }}
      />
      <Img
        src={asset(`arm-${pose}-${isLeft ? "cyan" : "yellow"}`)}
        style={{
          ...shared,
          opacity: Math.min(1, progress * 1.25),
          scale: `${isLeft ? -1 : 1} ${0.97 + Math.min(progress, 1) * 0.03}`,
          filter: `${colorFilter(side)} brightness(${0.99 + energy * 0.035})`,
        }}
      />
    </>
  );
};

export const MascotRigV2: React.FC<{
  leftPose?: ArmPose;
  rightPose?: ArmPose;
  previousLeftPose?: ArmPose;
  previousRightPose?: ArmPose;
  mood?: MascotMood;
  actionFrame?: number;
  scale?: number;
  motion?: MascotMotion;
}> = ({
  leftPose = "present",
  rightPose = "point-up",
  previousLeftPose = "relaxed",
  previousRightPose = "relaxed",
  mood = "idea",
  actionFrame = 18,
  scale = 1,
  motion = "idle",
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const seconds = frame / fps;
  const progress = spring({
    fps,
    frame: Math.max(0, actionFrame),
    config: {damping: 22, stiffness: 115, mass: 0.9},
  });
  const gestureSeconds = Math.max(0, actionFrame) / fps;
  const breathe = Math.sin(seconds * Math.PI * 0.58);
  const talk = Math.sin(seconds * Math.PI * 0.82);
  const energy = (Math.sin(seconds * Math.PI * 0.72) + 1) / 2;
  const isSurprised = mood === "surprise";
  const reaction = isSurprised ? Math.sin(Math.min(actionFrame, 18) / 18 * Math.PI) : 0;
  const headTilt = mood === "idea"
    ? -3.5 - progress * 1.2
    : mood === "explain"
      ? talk * 0.75
      : mood === "think"
        ? -7 + Math.sin(seconds * Math.PI * 0.42) * 1.2
        : mood === "doubt"
          ? 6 + Math.sin(seconds * Math.PI * 0.7) * 1.4
          : mood === "happy"
            ? Math.sin(seconds * Math.PI * 1.8) * 1.1
            : reaction * 2.5;
  const bodyLean = mood === "explain"
    ? talk * 0.28
    : mood === "idea"
      ? -progress * 0.45
      : mood === "doubt"
        ? 1.4
        : 0;
  const celebrationWindow = gestureSeconds % 4.4;
  const celebrationGesture = celebrationWindow < 1.45 ? Math.sin((celebrationWindow / 1.45) * Math.PI) : 0;
  const celebrateBob = motion === "celebrate" ? celebrationGesture * -7 : 0;
  const recoil = motion === "recoil" ? Math.sin(Math.min(actionFrame, 28) / 28 * Math.PI) * -11 : 0;
  const peek = motion === "peek" ? Math.sin(seconds * Math.PI * 0.55) * 3 : 0;
  const laughBob = motion === "laugh" ? Math.abs(Math.sin(seconds * Math.PI * 2.2)) * -5 : 0;
  const walkBob = motion === "walk" ? Math.abs(Math.sin(seconds * Math.PI * 2.5)) * -4 : 0;
  const walkX = motion === "walk" ? interpolate(actionFrame, [0, 36], [-190, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  }) : 0;
  const turnScaleX = motion === "turn"
    ? interpolate(actionFrame, [0, 12, 25, 40], [1, 0.22, -0.22, -1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.bezier(0.2, 0.8, 0.2, 1),
    })
    : 1;
  const approachScale = motion === "approach" ? interpolate(actionFrame, [0, 42], [0.82, 1.08], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  }) : 1;
  const approachY = motion === "approach" ? interpolate(actionFrame, [0, 42], [52, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  }) : 0;
  const bob = breathe * 1.7 - reaction * 5 + celebrateBob + recoil + laughBob + walkBob;

  return (
    <div
      style={{
        position: "relative",
        width: 720,
        height: 820,
        scale: `${scale * approachScale * turnScaleX} ${scale * approachScale}`,
        translate: `${peek + walkX}px ${bob + approachY}px`,
        rotate: `${bodyLean + (motion === "recoil" ? reaction * 3 : 0)}deg`,
        transformOrigin: "center bottom",
      }}
    >
      <Img
        src={asset("hover-ring")}
        style={{
          position: "absolute",
          left: 205,
          top: 700,
          width: 310,
          height: 66,
          objectFit: "contain",
          scale: `${1 + breathe * 0.035} ${0.85 + breathe * 0.015}`,
          opacity: 0.82,
          filter: `brightness(${0.95 + energy * 0.15}) drop-shadow(0 0 18px rgba(81,228,245,.45))`,
        }}
      />
      <Arm pose={leftPose} previousPose={previousLeftPose} side="left" progress={progress} energy={energy} motion={motion} gestureSeconds={gestureSeconds} />
      <Arm pose={rightPose} previousPose={previousRightPose} side="right" progress={progress} energy={energy} motion={motion} gestureSeconds={gestureSeconds} />
      <Img
        src={asset("torso")}
        style={{
          position: "absolute",
          left: 225,
          top: 405,
          width: 270,
          height: 253,
          objectFit: "contain",
          scale: `${1 + breathe * 0.0025} 1`,
          filter: "drop-shadow(0 25px 25px rgba(0,0,0,.3))",
          zIndex: 4,
        }}
      />
      <Img
        src={asset("collar")}
        style={{
          position: "absolute",
          left: 175,
          top: 315,
          width: 370,
          height: 165,
          objectFit: "contain",
          zIndex: 6,
          filter: "drop-shadow(0 14px 14px rgba(0,0,0,.22))",
        }}
      />
      <Img
        src={asset("head-front")}
        style={{
          position: "absolute",
          left: 219,
          top: 78,
          width: 282,
          height: 281,
          objectFit: "contain",
          rotate: `${headTilt}deg`,
          transformOrigin: "center bottom",
          filter: `brightness(${1 + energy * 0.025}) drop-shadow(0 18px 20px rgba(0,0,0,.3))`,
          zIndex: 7,
        }}
      />
      <Img
        src={asset("particle-cyan")}
        style={{
          position: "absolute",
          left: 56 + Math.cos(seconds * 0.82) * 13,
          top: 265 + Math.sin(seconds * 0.82) * 9,
          width: 82,
          height: 90,
          objectFit: "contain",
          scale: `${0.86 + energy * 0.13}`,
          filter: "drop-shadow(0 0 12px #51E4F5)",
          zIndex: 9,
        }}
      />
      <Img
        src={asset("particle-yellow")}
        style={{
          position: "absolute",
          right: 48 + Math.cos(seconds * 0.82) * 13,
          top: 245 - Math.sin(seconds * 0.82) * 9,
          width: 86,
          height: 86,
          objectFit: "contain",
          scale: `${0.86 + energy * 0.13}`,
          filter: "drop-shadow(0 0 12px #FFD51F)",
          zIndex: 9,
        }}
      />
      {isSurprised ? (
        <Img
          src={asset("accent")}
          style={{
            position: "absolute",
            right: 32,
            top: 64,
            width: 120,
            height: 106,
            objectFit: "contain",
            scale: `${0.78 + reaction * 0.3}`,
            zIndex: 10,
          }}
        />
      ) : null}
    </div>
  );
};

export const MascotActor: React.FC<{
  action: MascotAction;
  previousAction?: MascotAction;
  actionFrame?: number;
  scale?: number;
}> = ({action, previousAction = "idle", actionFrame = 0, scale = 1}) => {
  const current = MASCOT_ACTION_PRESETS[action];
  const previous = MASCOT_ACTION_PRESETS[previousAction];
  return (
    <MascotRigV2
      leftPose={current.leftPose}
      rightPose={current.rightPose}
      previousLeftPose={previous.leftPose}
      previousRightPose={previous.rightPose}
      mood={current.mood}
      motion={current.motion}
      actionFrame={actionFrame}
      scale={scale}
    />
  );
};
