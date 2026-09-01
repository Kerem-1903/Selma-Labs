import React from "react";
import {SceneFrame} from "../SceneFrame";

export const TurnScene: React.FC = () => (
  <SceneFrame
    asset="shot-02-turn.png"
    durationInFrames={114}
    fadeIn={18}
    fadeOut={18}
    fromScale={1.04}
    toScale={1.13}
    fromX={-30}
    toX={22}
    fromY={10}
    toY={-8}
    rainIntensity={1}
    redPulse
  />
);
