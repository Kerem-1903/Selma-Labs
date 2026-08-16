import React, {useMemo} from "react";
import {interpolate, useCurrentFrame, useVideoConfig} from "remotion";
import data from "../../public/hidden-designs/data.json";

type Word = {text: string; startMs: number; endMs: number};
type Page = {words: Word[]; startMs: number; endMs: number};

const makePages = (words: Word[]): Page[] => {
  const pages: Page[] = [];
  for (let index = 0; index < words.length; index += 5) {
    const group = words.slice(index, index + 5);
    pages.push({
      words: group,
      startMs: group[0].startMs,
      endMs: group[group.length - 1].endMs + 170,
    });
  }
  return pages;
};

export const CaptionLayer: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const timeMs = (frame / fps) * 1000;
  const pages = useMemo(() => makePages(data.words as Word[]), []);
  const page = pages.find((item) => timeMs >= item.startMs && timeMs <= item.endMs);
  if (!page) return null;

  const opacity = interpolate(timeMs - page.startMs, [0, 80], [0, 1], {
    extrapolateRight: "clamp",
  });
  const lift = interpolate(timeMs - page.startMs, [0, 120], [12, 0], {
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        position: "absolute",
        left: 450,
        right: 75,
        bottom: 34,
        display: "flex",
        justifyContent: "center",
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          maxWidth: 1320,
          padding: "13px 26px 16px",
          borderRadius: 14,
          background: "rgba(246, 240, 211, 0.96)",
          border: "3px solid #172235",
          borderLeft: "10px solid #FF5364",
          boxShadow: "7px 9px 0 rgba(15,24,37,.36)",
          color: "white",
          font: "900 36px/1.12 Arial, sans-serif",
          textAlign: "left",
          opacity,
          translate: `0 ${lift}px`,
        }}
      >
        {page.words.map((word, index) => {
          const active = timeMs >= word.startMs && timeMs <= word.endMs;
          return (
            <React.Fragment key={`${word.startMs}-${word.text}`}>
              <span style={{color: active ? "#E5384F" : "#172235", background: active ? "#FFE46B" : "transparent", borderRadius: 5, padding: active ? "1px 5px 2px" : "1px 0 2px", scale: active ? 1.05 : 1, display: "inline-block"}}>{word.text}</span>
              {index < page.words.length - 1 ? " " : ""}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};
