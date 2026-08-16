import React from "react";
import {AbsoluteFill} from "remotion";
import {amber, Film, ink} from "../Visuals";

export const HookScene: React.FC = () => (
  <AbsoluteFill>
    <Film file="chip-bag/footage/eating_chips.mp4" trimBefore={10} brightness={.7}/>
    <div style={{position: "absolute", top: 240, left: 54, right: 54, textAlign: "center"}}>
      <div style={{display: "inline-block", padding: "9px 18px", background: amber, color: ink, font: "1000 32px Arial Black", letterSpacing: 2}}>HERKES BUNU DÜŞÜNDÜ</div>
      <div style={{marginTop: 17, color: "white", font: "1000 83px/.9 Arial Black", letterSpacing: -4, textShadow: "0 9px 28px #000"}}>PAKETİN<br/><span style={{color: amber, fontSize: 110}}>YARISI</span><br/>NEDEN HAVA?</div>
    </div>
  </AbsoluteFill>
);
