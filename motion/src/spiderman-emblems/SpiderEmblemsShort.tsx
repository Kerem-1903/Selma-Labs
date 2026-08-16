import React from "react";
import {AbsoluteFill, Audio, Sequence, staticFile} from "remotion";
import {BrandBug} from "../components/BrandBug";
import {CaptionLayer} from "./CaptionLayer";
import {EmblemScene} from "./EmblemScene";
import {FinalScene} from "./FinalScene";
import {HookScene} from "./HookScene";
import {IdentityScene} from "./IdentityScene";
import {colors} from "./shared";

export const SpiderEmblemsShort: React.FC = () => (
  <AbsoluteFill style={{background: colors.black}}>
    <Sequence from={0} durationInFrames={165}><HookScene /></Sequence>
    <Sequence from={165} durationInFrames={137}><EmblemScene file="tobey.png" index={1} name="TOBEY MAGUIRE" era="RAIMI ÜÇLEMESİ" trait="KALIN + METALİK" accent="#D4D9E1" position="center" startScale={1.1} /></Sequence>
    <Sequence from={302} durationInFrames={119}><EmblemScene file="andrew.jpg" index={2} name="ANDREW GARFIELD" era="THE AMAZING SPIDER-MAN" trait="UZUN + KESKİN" accent="#47A8FF" position="72% 100%" startScale={1.34} yOffset={-1050} /></Sequence>
    <Sequence from={421} durationInFrames={136}><EmblemScene file="tom.jpg" index={3} name="TOM HOLLAND" era="STARK KOSTÜMÜ" trait="KÜÇÜK + TEKNOLOJİK" accent="#FF5454" position="center" startScale={1.55} /></Sequence>
    <Sequence from={557} durationInFrames={162}><EmblemScene file="iron.jpg" index={4} name="IRON SPIDER" era="AVENGERS DÖNEMİ" trait="BÜYÜK + ALTIN" accent="#FFD34E" position="center" startScale={1.08} /></Sequence>
    <Sequence from={719} durationInFrames={138}><EmblemScene file="miles.jpg" index={5} name="MILES MORALES" era="KENDİ TARZI" trait="KIRMIZI + CESUR" accent="#FF3B48" position="center" startScale={1.08} /></Sequence>
    <Sequence from={857} durationInFrames={133}><EmblemScene file="symbiote.jpg" index={6} name="SYMBIOTE" era="KARANLIK DÖNEM" trait="DEV + BEYAZ" accent="#F7F7F7" position="center 30%" startScale={1.03} /></Sequence>
    <Sequence from={990} durationInFrames={186}><IdentityScene /></Sequence>
    <Sequence from={1176} durationInFrames={84}><FinalScene /></Sequence>
    <Sequence from={35} durationInFrames={1225}><BrandBug science="#2E7BFF" active="#F13B3B" /></Sequence>
    <CaptionLayer />
    <Audio src={staticFile("spiderman-emblems/music.mp3")} loop volume={0.032} />
    <Audio src={staticFile("spiderman-emblems/narration.mp3")} volume={1} />
  </AbsoluteFill>
);
