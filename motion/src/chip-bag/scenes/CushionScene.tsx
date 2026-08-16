import React from "react";
import {Series} from "remotion";
import {amber, Film, Headline, Photo} from "../Visuals";

export const CushionScene: React.FC = () => (
  <Series>
    <Series.Sequence durationInFrames={102}>
      <Film file="chip-bag/footage/holding_chip_bag.mp4" trimBefore={145} brightness={.68}/>
      <Headline>ŞİŞKİN PAKET<br/><span style={{color: amber}}>YASTIK GİBİDİR</span></Headline>
    </Series.Sequence>
    <Series.Sequence durationInFrames={101}>
      <Photo file="chip-bag/footage/open_chip_bag.jpg" position="center"/>
      <Headline>TAŞIMADA<br/><span style={{color: amber}}>CİPSLERİ KORUR</span></Headline>
    </Series.Sequence>
  </Series>
);
