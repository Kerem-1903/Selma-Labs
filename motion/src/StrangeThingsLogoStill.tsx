import React from "react";
import {AbsoluteFill} from "remotion";
import {StrangeThingsMark} from "./components/StrangeThingsMark";

export const StrangeThingsLogoStill: React.FC = () => (
  <AbsoluteFill
    style={{
      alignItems: "center",
      background: "radial-gradient(circle at 50% 42%, #172033 0%, #050912 58%, #02040A 100%)",
      justifyContent: "center",
    }}
  >
    <div style={{filter: "drop-shadow(0 28px 70px rgba(34,211,238,.28))"}}>
      <StrangeThingsMark size={820} science="#22D3EE" active="#FFD700" />
    </div>
  </AbsoluteFill>
);
