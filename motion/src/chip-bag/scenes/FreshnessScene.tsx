import React from "react";
import {Series} from "remotion";
import {amber, Film, Headline} from "../Visuals";

export const FreshnessScene: React.FC = () => (
  <Series>
    <Series.Sequence durationInFrames={110}>
      <Film file="chip-bag/footage/chips_bowl.mp4" trimBefore={35} brightness={.62}/>
      <Headline><span style={{color: amber}}>OKSİJENİ AZALTIR</span><br/>YAĞ DAHA GEÇ BOZULUR</Headline>
    </Series.Sequence>
    <Series.Sequence durationInFrames={82}>
      <Film file="chip-bag/footage/eating_chips.mp4" trimBefore={145} brightness={.68}/>
      <Headline>CİPS<br/><span style={{color: amber, fontSize: 95}}>DAHA GEÇ BAYATLAR</span></Headline>
    </Series.Sequence>
  </Series>
);
