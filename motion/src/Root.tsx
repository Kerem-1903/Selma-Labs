import React from "react";
import {Composition} from "remotion";
import demoProps from "./demo-props.json";
import {StrangeThingsShort} from "./StrangeThingsShort";
import {StrangeThingsLogoStill} from "./StrangeThingsLogoStill";
import type {StrangeThingsProps} from "./types";
import {VenusDayYearV2} from "./venus-v2/VenusDayYearV2";
import {MicrowaveMeshShort} from "./microwave-mesh/MicrowaveMeshShort";
import {SpiderEmblemsShort} from "./spiderman-emblems/SpiderEmblemsShort";
import {HiddenDesignsLong} from "./hidden-designs/HiddenDesignsLong";
import {ProvenStylePreview} from "./hidden-designs/ProvenStylePreview";
import {ProvenStyleFull} from "./hidden-designs/ProvenStyleFull";
import {HiddenDesignsThumbnail} from "./hidden-designs/HiddenDesignsThumbnail";
import {MascotAnimationDemo} from "./hidden-designs/MascotAnimationDemo";
import {MascotIllustratedDemo} from "./hidden-designs/MascotIllustratedDemo";
import {MascotFinalV5Demo} from "./hidden-designs/MascotFinalV5Demo";
import {MascotRigDemo} from "./hidden-designs/MascotRigDemo";
import {MascotRigV2Demo} from "./hidden-designs/MascotRigV2Demo";
import {HiddenDesignsMascotFull} from "./hidden-designs/HiddenDesignsMascotFull";
import {ReferenceStyleV3} from "./hidden-designs/ReferenceStyleV3";
import {HiddenDesigns45} from "./hidden-designs/HiddenDesigns45";
import {EarthStopVideo} from "./earth-stop/EarthStopVideo";
import {PerseidShort} from "./perseid-short/PerseidShort";
import {InternetOutageVideo} from "./internet-outage/InternetOutageVideo";
import {InternetOutageThumbnail} from "./internet-outage/InternetOutageThumbnail";
import {PhantomVibrationShort} from "./phantom-vibration/PhantomVibrationShort";
import {VlahovicTomatoShort} from "./vlahovic-tomato/VlahovicTomatoShort";
import {AirplaneLavatoryShort} from "./airplane-lavatory/AirplaneLavatoryShort";
import {ChipBagShort} from "./chip-bag/ChipBagShort";
import {AkiraMotionTest} from "./akira/AkiraMotionTest";

export const RemotionRoot: React.FC = () => (
  <>
    <Composition
      id="AkiraMotionTest"
      component={AkiraMotionTest}
      width={1080}
      height={1920}
      fps={30}
      durationInFrames={300}
    />
    <Composition
      id="ChipBagShort"
      component={ChipBagShort}
      width={1080}
      height={1920}
      fps={30}
      durationInFrames={870}
    />
    <Composition
      id="AirplaneLavatoryShort"
      component={AirplaneLavatoryShort}
      width={1080}
      height={1920}
      fps={30}
      durationInFrames={930}
    />
    <Composition
      id="VlahovicTomatoShort"
      component={VlahovicTomatoShort}
      width={1080}
      height={1920}
      fps={30}
      durationInFrames={1080}
    />
    <Composition
      id="PhantomVibrationShort"
      component={PhantomVibrationShort}
      width={1080}
      height={1920}
      fps={30}
      durationInFrames={900}
    />
    <Composition
      id="StrangeThingsShort"
      component={StrangeThingsShort}
      width={1080}
      height={1920}
      fps={30}
      durationInFrames={720}
      defaultProps={demoProps as StrangeThingsProps}
      calculateMetadata={({props}) => ({
        durationInFrames: props.durationInFrames,
        fps: props.fps,
      })}
    />
    <Composition
      id="VenusDayYearV2"
      component={VenusDayYearV2}
      width={1080}
      height={1920}
      fps={30}
      durationInFrames={930}
    />
    <Composition
      id="MicrowaveMeshShort"
      component={MicrowaveMeshShort}
      width={1080}
      height={1920}
      fps={30}
      durationInFrames={960}
    />
    <Composition
      id="SpiderEmblemsShort"
      component={SpiderEmblemsShort}
      width={1080}
      height={1920}
      fps={30}
      durationInFrames={1260}
    />
    <Composition
      id="HiddenDesignsLong"
      component={HiddenDesignsLong}
      width={1920}
      height={1080}
      fps={30}
      durationInFrames={6657}
    />
    <Composition
      id="HiddenDesignsProvenStylePreview"
      component={ProvenStylePreview}
      width={1920}
      height={1080}
      fps={30}
      durationInFrames={1208}
    />
    <Composition
      id="HiddenDesignsProvenStyleFull"
      component={ProvenStyleFull}
      width={1920}
      height={1080}
      fps={30}
      durationInFrames={6597}
    />
    <Composition
      id="HiddenDesignsMascotFull"
      component={HiddenDesignsMascotFull}
      width={1920}
      height={1080}
      fps={30}
      durationInFrames={6597}
    />
    <Composition
      id="HiddenDesignsReferenceV3"
      component={ReferenceStyleV3}
      width={1920}
      height={1080}
      fps={30}
      durationInFrames={6597}
    />
    <Composition
      id="HiddenDesigns45"
      component={HiddenDesigns45}
      width={1920}
      height={1080}
      fps={30}
      durationInFrames={15081}
    />
    <Composition
      id="EarthStopVideo"
      component={EarthStopVideo}
      width={1920}
      height={1080}
      fps={30}
      durationInFrames={12059}
    />
    <Composition
      id="PerseidShort"
      component={PerseidShort}
      width={1080}
      height={1920}
      fps={30}
      durationInFrames={1169}
    />
    <Composition
      id="InternetOutageVideo"
      component={InternetOutageVideo}
      width={1920}
      height={1080}
      fps={30}
      durationInFrames={34007}
    />
    <Composition
      id="InternetOutageQaReel"
      component={InternetOutageVideo}
      width={1920}
      height={1080}
      fps={30}
      durationInFrames={46}
      defaultProps={{qaStrideFrames: 750, includeAudio: false}}
    />
    <Composition
      id="InternetOutageThumbnail"
      component={InternetOutageThumbnail}
      width={1280}
      height={720}
      fps={30}
      durationInFrames={1}
    />
    <Composition
      id="HiddenDesignsThumbnail"
      component={HiddenDesignsThumbnail}
      width={1280}
      height={720}
      fps={30}
      durationInFrames={1}
    />
    <Composition
      id="MascotAnimationDemo"
      component={MascotAnimationDemo}
      width={1920}
      height={1080}
      fps={30}
      durationInFrames={450}
    />
    <Composition
      id="MascotIllustratedDemo"
      component={MascotIllustratedDemo}
      width={1920}
      height={1080}
      fps={30}
      durationInFrames={360}
    />
    <Composition
      id="MascotFinalV5Demo"
      component={MascotFinalV5Demo}
      width={1920}
      height={1080}
      fps={30}
      durationInFrames={420}
    />
    <Composition
      id="MascotRigDemo"
      component={MascotRigDemo}
      width={1920}
      height={1080}
      fps={30}
      durationInFrames={420}
    />
    <Composition
      id="MascotRigV2Demo"
      component={MascotRigV2Demo}
      width={1920}
      height={1080}
      fps={30}
      durationInFrames={1020}
    />
    <Composition
      id="StrangeThingsLogo"
      component={StrangeThingsLogoStill}
      width={1024}
      height={1024}
      fps={30}
      durationInFrames={1}
    />
  </>
);
