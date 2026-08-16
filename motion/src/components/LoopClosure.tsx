import React from "react";
import {AbsoluteFill} from "remotion";
import type {SceneSpec} from "../types";
import {SceneLayer} from "./SceneLayer";

export const LoopClosure: React.FC<{scene: SceneSpec}> = ({scene}) => {
  return (
    <AbsoluteFill>
      <SceneLayer
        scene={{...scene, durationFrames: 8, sourceStartFrame: 0, transition: "hard"}}
        index={0}
      />
    </AbsoluteFill>
  );
};
