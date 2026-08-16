import React, {useMemo} from "react";
import {interpolate, useCurrentFrame, useVideoConfig} from "remotion";
import data from "../../public/venus-v2/data.json";
import {colors} from "./shared";

type Word = {text: string; startMs: number; endMs: number};
type Page = {words: Word[]; startMs: number; endMs: number};

const makePages = (words: Word[]): Page[] => {
  const pages: Page[] = [];
  for (let index = 0; index < words.length; index += 4) {
    const group = words.slice(index, index + 4);
    pages.push({words: group, startMs: group[0].startMs, endMs: group[group.length - 1].endMs + 220});
  }
  return pages;
};

export const CaptionLayer: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const timeMs = (frame / fps) * 1000;
  const pages = useMemo(() => makePages(data.words as Word[]), []);
  const page = pages.find((candidate) => timeMs >= candidate.startMs && timeMs <= candidate.endMs);
  if (!page) return null;
  const local = timeMs - page.startMs;
  return (
    <div style={{position: "absolute", left: 70, right: 70, bottom: 110, display: "flex", justifyContent: "center", opacity: interpolate(local, [0, 90], [0, 1], {extrapolateRight: "clamp"})}}>
      <div style={{background: "rgba(2,4,8,.88)", borderRadius: 28, padding: "20px 30px 24px", boxShadow: "0 12px 34px rgba(0,0,0,.48)", textAlign: "center", font: "900 58px/1.12 Arial Black, Arial", color: "white", maxWidth: 900}}>
        {page.words.map((word, index) => {
          const active = timeMs >= word.startMs && timeMs <= word.endMs;
          return <React.Fragment key={`${word.startMs}-${word.text}`}><span style={{color: active ? colors.yellow : "white"}}>{word.text}</span>{index < page.words.length - 1 ? " " : ""}</React.Fragment>;
        })}
      </div>
    </div>
  );
};

