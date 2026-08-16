import React from "react";
import {interpolate, spring, useCurrentFrame, useVideoConfig} from "remotion";

export const AnatomyCallout: React.FC<{labels: string[]; science: string}> = ({labels, science}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  if (!labels.length) return null;
  return (
    <div style={{position: "absolute", top: 310, left: 90, right: 90}}>
      {labels.slice(0, 3).map((label, index) => {
        const localFrame = Math.max(0, frame - index * 4);
        const enter = spring({frame: localFrame, fps, config: {damping: 16, stiffness: 190}});
        return (
          <div
            key={`${label}-${index}`}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 16,
              marginTop: 16,
              opacity: interpolate(enter, [0, 1], [0, 1]),
              transform: `translateX(${interpolate(enter, [0, 1], [-55, 0])}px)`,
            }}
          >
            <div style={{width: 18, height: 18, borderRadius: 99, background: science, boxShadow: `0 0 24px ${science}`}} />
            <div
              style={{
                padding: "14px 22px",
                borderRadius: 18,
                background: "rgba(3,8,18,.76)",
                border: `2px solid ${science}88`,
                color: "white",
                fontFamily: "Arial Black, Arial, sans-serif",
                fontSize: 42,
                textTransform: "uppercase",
              }}
            >
              {label}
            </div>
          </div>
        );
      })}
    </div>
  );
};
