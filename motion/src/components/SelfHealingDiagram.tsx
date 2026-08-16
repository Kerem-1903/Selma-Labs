import React from "react";
import {interpolate, useCurrentFrame} from "remotion";

export const SelfHealingDiagram: React.FC<{science: string; active: string}> = ({science, active}) => {
  const frame = useCurrentFrame();
  const reveal = interpolate(frame, [5, 16], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const heal = interpolate(frame, [18, 62], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const pulse = interpolate(frame % 22, [0, 11, 21], [0.35, 1, 0.35]);

  return (
    <div
      style={{
        position: "absolute",
        right: 70,
        top: 330,
        width: 250,
        height: 430,
        opacity: reveal,
        borderRadius: 34,
        background: "linear-gradient(180deg, rgba(3,8,18,.78), rgba(3,8,18,.48))",
        border: `2px solid ${science}77`,
        boxShadow: `0 18px 55px rgba(0,0,0,.38), 0 0 32px ${science}22`,
        overflow: "hidden",
      }}
    >
      <svg height="100%" viewBox="0 0 250 430" width="100%">
        <defs>
          <linearGradient id="repair-flow" x1="0" x2="0" y1="1" y2="0">
            <stop offset="0%" stopColor={active} />
            <stop offset="100%" stopColor={science} />
          </linearGradient>
          <filter id="repair-glow" x="-100%" y="-30%" width="300%" height="160%">
            <feGaussianBlur stdDeviation="5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <rect x="26" y="35" width="198" height="350" rx="28" fill="rgba(255,255,255,.035)" stroke="rgba(255,255,255,.10)" />
        <path
          d="M128 57 L101 110 L143 153 L108 205 L139 248 L111 302 L129 364"
          fill="none"
          stroke="rgba(255,255,255,.72)"
          strokeDasharray="8 9"
          strokeLinecap="round"
          strokeWidth="5"
        />
        <path
          d="M128 364 L111 302 L139 248 L108 205 L143 153 L101 110 L128 57"
          fill="none"
          filter="url(#repair-glow)"
          pathLength="1"
          stroke="url(#repair-flow)"
          strokeDasharray="1"
          strokeDashoffset={1 - heal}
          strokeLinecap="round"
          strokeWidth="11"
        />
        {[82, 134, 188, 242, 298].map((cy, index) => {
          const direction = index % 2 === 0 ? -1 : 1;
          const travel = interpolate(heal, [0, 1], [0, 52]);
          return (
            <circle
              key={cy}
              cx={125 + direction * (72 - travel)}
              cy={cy}
              fill={index % 2 === 0 ? active : science}
              opacity={0.52 + pulse * 0.38}
              r={7 + pulse * 2}
            />
          );
        })}
      </svg>
    </div>
  );
};
