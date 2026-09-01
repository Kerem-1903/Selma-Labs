import React from "react";
import {SceneFrame} from "../SceneFrame";

export const WalkScene: React.FC = () => (
  <SceneFrame
    asset="shot-01-walk.png"
    durationInFrames={114}
    fadeOut={18}
    fromScale={1.025}
    toScale={1.13}
    fromX={18}
    toX={-20}
    fromY={8}
    toY={-8}
    rainIntensity={0.8}
  />
);
