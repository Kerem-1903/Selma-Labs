import React from "react";
import {Series} from "remotion";
import {amber, Film, Headline, Photo} from "../Visuals";

export const NitrogenScene: React.FC = () => (
  <Series>
    <Series.Sequence durationInFrames={47}>
      <Photo file="chip-bag/footage/open_chip_bag.jpg" position="center"/>
      <Headline top={300} tone="red">SENİ KANDIRMAK<br/>İÇİN Mİ?</Headline>
    </Series.Sequence>
    <Series.Sequence durationInFrames={46}>
      <Film file="chip-bag/footage/holding_chip_bag.mp4" trimBefore={145} brightness={.68}/>
      <Headline top={300}>HAVA DEĞİL<br/><span style={{color: amber, fontSize: 94}}>AZOT GAZI</span></Headline>
    </Series.Sequence>
  </Series>
);
