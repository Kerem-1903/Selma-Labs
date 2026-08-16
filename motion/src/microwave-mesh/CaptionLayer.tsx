import React, {useMemo} from "react";
import {interpolate, useCurrentFrame, useVideoConfig} from "remotion";
import data from "../../public/microwave-mesh/data.json";
import {palette} from "./shared";

type Word = {text: string; startMs: number; endMs: number};
type Page = {words: Word[]; startMs: number; endMs: number};

const makePages = (words: Word[]): Page[] => {
  const pages: Page[] = [];
  for (let index = 0; index < words.length; index += 4) {
    const group = words.slice(index, index + 4);
    pages.push({words: group, startMs: group[0].startMs, endMs: group[group.length - 1].endMs + 170});
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
  return (
    <div style={{position: "absolute", left: 68, right: 68, bottom: 105, display: "flex", justifyContent: "center"}}>
      <div
        style={{
          opacity: interpolate(timeMs - page.startMs, [0, 70], [0, 1], {extrapolateRight: "clamp"}),
          maxWidth: 910,
          padding: "19px 30px 23px",
          borderRadius: 28,
          background: "rgba(1,4,8,.9)",
          boxShadow: "0 15px 40px rgba(0,0,0,.52)",
          textAlign: "center",
          color: "white",
          font: "900 57px/1.11 Arial Black, Arial",
        }}
      >
        {page.words.map((word, index) => {
          const active = timeMs >= word.startMs && timeMs <= word.endMs;
          return (
            <React.Fragment key={`${word.startMs}-${word.text}`}>
              <span style={{color: active ? palette.yellow : "white"}}>{word.text}</span>
              {index < page.words.length - 1 ? " " : ""}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};
