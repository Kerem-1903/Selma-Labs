import React, {useMemo} from "react";
import {interpolate, useCurrentFrame, useVideoConfig} from "remotion";
import data from "../../public/spiderman-emblems/data.json";
import {colors} from "./shared";

type Word = {text: string; startMs: number; endMs: number};
type Page = {words: Word[]; startMs: number; endMs: number};

const pagesFromWords = (words: Word[]): Page[] => {
  const pages: Page[] = [];
  for (let index = 0; index < words.length; index += 4) {
    const group = words.slice(index, index + 4);
    pages.push({words: group, startMs: group[0].startMs, endMs: group[group.length - 1].endMs + 150});
  }
  return pages;
};

export const CaptionLayer: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const timeMs = frame / fps * 1000;
  const pages = useMemo(() => pagesFromWords(data.words as Word[]), []);
  const page = pages.find((candidate) => timeMs >= candidate.startMs && timeMs <= candidate.endMs);
  if (!page) return null;
  return (
    <div style={{position: "absolute", left: 65, right: 65, bottom: 105, display: "flex", justifyContent: "center"}}>
      <div style={{maxWidth: 920, padding: "18px 28px 22px", borderRadius: 24, background: "rgba(1,3,8,.9)", border: "2px solid rgba(255,255,255,.15)", boxShadow: "0 15px 40px rgba(0,0,0,.54)", textAlign: "center", color: "white", font: "900 56px/1.1 Arial Black, Arial", opacity: interpolate(timeMs - page.startMs, [0, 70], [0, 1], {extrapolateRight: "clamp"})}}>
        {page.words.map((word, index) => {
          const active = timeMs >= word.startMs && timeMs <= word.endMs;
          return <React.Fragment key={`${word.startMs}-${word.text}`}><span style={{color: active ? colors.yellow : "white"}}>{word.text}</span>{index < page.words.length - 1 ? " " : ""}</React.Fragment>;
        })}
      </div>
    </div>
  );
};
