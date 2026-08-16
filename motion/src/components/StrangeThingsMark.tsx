import React from "react";

export const StrangeThingsMark: React.FC<{
  size: number;
  science: string;
  active: string;
}> = ({size, science, active}) => (
  <svg
    aria-label="Strange Things ST portal mark"
    height={size}
    viewBox="0 0 100 100"
    width={size}
  >
    <defs>
      <radialGradient id="st-core" cx="50%" cy="42%" r="62%">
        <stop offset="0%" stopColor="#172033" />
        <stop offset="72%" stopColor="#050912" />
        <stop offset="100%" stopColor="#010308" />
      </radialGradient>
      <filter id="st-glow" x="-60%" y="-60%" width="220%" height="220%">
        <feGaussianBlur stdDeviation="3" result="blur" />
        <feMerge>
          <feMergeNode in="blur" />
          <feMergeNode in="SourceGraphic" />
        </feMerge>
      </filter>
    </defs>
    <circle cx="50" cy="50" r="45" fill="url(#st-core)" stroke="rgba(255,255,255,.18)" strokeWidth="2" />
    <path
      d="M18 63 A39 39 0 0 1 74 17"
      fill="none"
      filter="url(#st-glow)"
      stroke={science}
      strokeLinecap="round"
      strokeWidth="5"
    />
    <path
      d="M82 37 A39 39 0 0 1 27 84"
      fill="none"
      filter="url(#st-glow)"
      stroke={active}
      strokeLinecap="round"
      strokeWidth="4"
    />
    <circle cx="82" cy="37" fill={active} r="4.5" />
    <circle cx="18" cy="63" fill={science} r="4.5" />
    <text
      x="50"
      y="62"
      fill="#FFFFFF"
      fontFamily="Arial Black, Arial, sans-serif"
      fontSize="34"
      fontWeight="900"
      letterSpacing="-3"
      textAnchor="middle"
    >
      ST
    </text>
  </svg>
);
