import React from "react";
import {interpolate, useCurrentFrame, useVideoConfig} from "remotion";
import {StrangeThingsMark} from "../components/StrangeThingsMark";

export const LabHost: React.FC<{
  mood?: "talk" | "point" | "write";
  scale?: number;
}> = ({mood = "talk", scale = 1}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const bob = Math.sin((frame / fps) * Math.PI * 2.2) * 4;
  const talk = Math.sin((frame / fps) * Math.PI * 5) * 5;
  const rightRotation = mood === "write" ? -72 + talk * .6 : mood === "point" ? -48 + talk : -8 + talk;
  const leftRotation = mood === "talk" ? 18 - talk * 0.7 : 8;

  return (
    <div
      style={{
        position: "absolute",
        width: 390,
        height: 760,
        left: 62,
        bottom: 36,
        scale,
        transformOrigin: "bottom center",
        translate: `0 ${bob}px`,
      }}
    >
      <div style={{position: "absolute", left: 94, top: 14, zIndex: 8, filter: "drop-shadow(0 18px 20px rgba(0,0,0,.28))"}}>
        <StrangeThingsMark size={205} science="#35D8FF" active="#FF5364" />
      </div>

      <div style={{position: "absolute", left: 142, top: 194, width: 110, height: 54, borderRadius: "0 0 24px 24px", background: "#172235", zIndex: 4}} />

      <div style={{position: "absolute", left: 82, top: 228, width: 232, height: 390, borderRadius: "60px 60px 38px 38px", background: "linear-gradient(110deg,#F9FCFF 0%,#CFDAE9 100%)", border: "5px solid #111B2B", boxShadow: "0 24px 30px rgba(0,0,0,.25)", zIndex: 3}}>
        <div style={{position: "absolute", left: 105, top: 12, width: 10, height: 340, background: "#AEBCCD"}} />
        <div style={{position: "absolute", left: 21, top: 90, width: 78, height: 92, border: "5px solid #97A8BC", borderTop: 0, borderRadius: "0 0 16px 16px"}}>
          <div style={{position: "absolute", left: 16, top: 17, color: "#15243B", font: "900 22px Arial"}}>LAB</div>
          <div style={{position: "absolute", left: 25, top: 48, width: 28, height: 28, borderRadius: "50%", background: "linear-gradient(135deg,#35D8FF,#FF5364)"}} />
        </div>
        <div style={{position: "absolute", right: 24, top: 28, width: 56, height: 12, borderRadius: 8, background: "#35D8FF"}} />
        <div style={{position: "absolute", left: 65, top: -2, width: 52, height: 112, background: "#D8E2ED", clipPath: "polygon(0 0,100% 0,65% 100%,35% 100%)", rotate: "-17deg"}} />
        <div style={{position: "absolute", right: 63, top: -2, width: 52, height: 112, background: "#D8E2ED", clipPath: "polygon(0 0,100% 0,65% 100%,35% 100%)", rotate: "17deg"}} />
      </div>

      <div style={{position: "absolute", left: 65, top: 598, width: 105, height: 112, background: "#172235", borderRadius: "10px 10px 28px 28px", rotate: "3deg", zIndex: 2}} />
      <div style={{position: "absolute", right: 58, top: 598, width: 105, height: 112, background: "#172235", borderRadius: "10px 10px 28px 28px", rotate: "-3deg", zIndex: 2}} />
      <div style={{position: "absolute", left: 45, top: 694, width: 138, height: 44, borderRadius: "34px 16px 14px 14px", background: "#07101E", zIndex: 5}} />
      <div style={{position: "absolute", right: 38, top: 694, width: 138, height: 44, borderRadius: "16px 34px 14px 14px", background: "#07101E", zIndex: 5}} />

      <div style={{position: "absolute", left: 45, top: 270, width: 58, height: 250, borderRadius: 34, background: "#E2EAF3", border: "5px solid #111B2B", transformOrigin: "29px 20px", rotate: `${leftRotation}deg`, zIndex: 1}}>
        <div style={{position: "absolute", left: 6, bottom: -36, width: 45, height: 58, borderRadius: "48%", background: "#F2B38D", border: "4px solid #111B2B"}} />
      </div>

      <div style={{position: "absolute", right: 48, top: 270, width: 60, height: 295, borderRadius: 34, background: "#E2EAF3", border: "5px solid #111B2B", transformOrigin: "30px 22px", rotate: `${rightRotation}deg`, zIndex: 6}}>
        <div style={{position: "absolute", left: 6, bottom: -38, width: 46, height: 62, borderRadius: "48%", background: "#F2B38D", border: "4px solid #111B2B"}} />
        {mood === "write" && <div style={{position: "absolute", left: 21, bottom: -93, width: 11, height: 72, borderRadius: 8, background: "#FFE46B", rotate: "3deg", boxShadow: "0 0 12px rgba(255,228,107,.6)"}} />}
      </div>

      <div style={{position: "absolute", left: 154, top: 412, width: 84, height: 34, borderRadius: 20, background: "#172235", zIndex: 7}}>
        {[0, 1, 2].map((i) => <div key={i} style={{position: "absolute", left: 13 + i * 26, top: 11, width: 10, height: 10, borderRadius: "50%", background: i === 1 ? "#FF5364" : "#35D8FF"}} />)}
      </div>
    </div>
  );
};
