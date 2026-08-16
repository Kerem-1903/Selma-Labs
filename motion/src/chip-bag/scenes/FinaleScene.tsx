import React from "react";
import {AbsoluteFill, Series} from "remotion";
import {amber, Film, Headline, ink} from "../Visuals";

export const FinaleScene: React.FC = () => (
  <Series>
    <Series.Sequence durationInFrames={110}>
      <Film file="chip-bag/footage/snack_aisle.mp4" trimBefore={15} brightness={.62}/>
      <Headline>PAKET BOŞ DEĞİL<br/><span style={{color: amber}}>İKİ İŞ YAPIYOR</span></Headline>
    </Series.Sequence>
    <Series.Sequence durationInFrames={160}>
      <AbsoluteFill>
        <Film file="chip-bag/footage/eating_chips.mp4" trimBefore={210} brightness={.58}/>
        <div style={{position: "absolute", top: 300, left: 55, right: 55, textAlign: "center"}}>
          <div style={{color: "white", font: "1000 67px/.92 Arial Black", textShadow: "0 9px 28px #000"}}>PAKETİN BOYUNA DEĞİL</div>
          <div style={{marginTop: 26, padding: "24px 18px", background: amber, color: ink, font: "1000 88px/.9 Arial Black", boxShadow: "14px 14px 0 #F04438"}}>NET GRAMAJA<br/>BAK</div>
        </div>
      </AbsoluteFill>
    </Series.Sequence>
  </Series>
);
