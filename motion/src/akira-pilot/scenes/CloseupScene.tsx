import React from "react";
import {SceneFrame} from "../SceneFrame";

export const CloseupScene: React.FC = () => (
  <SceneFrame
    asset="shot-03-closeup.png"
    durationInFrames={108}
    fadeIn={18}
    fromScale={1.015}
    toScale={1.105}
    fromY={8}
    toY={-6}
    rainIntensity={1.25}
    redPulse
  />
);
