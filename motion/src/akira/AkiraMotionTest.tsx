import React from "react";
import {
  AbsoluteFill,
  Easing,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

const particles = [
  {left: 96, top: 1510, size: 8, delay: 0},
  {left: 188, top: 1390, size: 5, delay: 34},
  {left: 862, top: 1470, size: 7, delay: 18},
  {left: 934, top: 1320, size: 4, delay: 52},
  {left: 126, top: 1120, size: 6, delay: 71},
  {left: 902, top: 980, size: 5, delay: 95},
  {left: 72, top: 760, size: 4, delay: 119},
  {left: 978, top: 620, size: 7, delay: 142},
];

export const AkiraMotionTest: React.FC = () => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();

  return (
    <AbsoluteFill
      style={{
        background:
          "radial-gradient(circle at 50% 38%, #f3d7d8 0%, #d7dfe8 34%, #758090 70%, #111722 100%)",
        color: "#f8fafc",
        fontFamily: "Arial, Helvetica, sans-serif",
        overflow: "hidden",
      }}
    >
      <AbsoluteFill
        style={{
          opacity: 0.28,
          backgroundImage:
            "linear-gradient(rgba(255,255,255,.22) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.16) 1px, transparent 1px)",
          backgroundSize: "72px 72px",
          translate: interpolate(frame, [0, durationInFrames - 1], ["0px 0px", "-72px -144px"], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.linear,
          }),
        }}
      />

      <div
        style={{
          position: "absolute",
          left: 540,
          top: 900,
          width: 980,
          height: 980,
          borderRadius: "50%",
          translate: "-50% -50%",
          scale: interpolate(frame, [0, 75, 150, 225, 299], [0.86, 1.02, 0.91, 1.06, 0.86], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.bezier(0.37, 0, 0.63, 1),
            output: "perceptual-scale",
          }),
          background:
            "radial-gradient(circle, rgba(226,45,62,.35) 0%, rgba(226,45,62,.12) 42%, rgba(226,45,62,0) 72%)",
          filter: "blur(18px)",
        }}
      />

      <div
        style={{
          position: "absolute",
          left: 160,
          top: 210,
          width: 760,
          height: 1510,
          overflow: "hidden",
          borderRadius: 36,
          border: "2px solid rgba(255,255,255,.72)",
          boxShadow: "0 42px 110px rgba(7,12,20,.5), 0 0 0 1px rgba(208,36,55,.32)",
          backgroundColor: "#eef0ee",
          translate: interpolate(
            frame,
            [0, 60, 120, 180, 240, 299],
            ["0px 38px", "-18px 0px", "16px 26px", "-12px -8px", "20px 18px", "0px 38px"],
            {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.bezier(0.37, 0, 0.63, 1),
            },
          ),
          rotate: interpolate(
            frame,
            [0, 60, 120, 180, 240, 299],
            ["-1.6deg", "1.4deg", "-1.1deg", "1.2deg", "-0.8deg", "-1.6deg"],
            {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.bezier(0.37, 0, 0.63, 1),
            },
          ),
          scale: interpolate(frame, [0, 150, 299], [1, 1.075, 1.18], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.bezier(0.16, 1, 0.3, 1),
            output: "perceptual-scale",
          }),
        }}
      >
        <Img
          name="Akira approved front reference"
          src={staticFile("akira/approved-front.png")}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            objectPosition: "50% 42%",
            scale: interpolate(
              frame,
              [0, 38, 76, 114, 152, 190, 228, 266, 299],
              [1, 1.018, 1, 1.02, 1, 1.019, 1, 1.017, 1],
              {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
                easing: Easing.bezier(0.37, 0, 0.63, 1),
                output: "perceptual-scale",
              },
            ),
            translate: interpolate(
              frame,
              [0, 75, 150, 225, 299],
              ["0px 0px", "8px -8px", "-7px 2px", "9px -10px", "0px 0px"],
              {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
                easing: Easing.bezier(0.37, 0, 0.63, 1),
              },
            ),
          }}
        />
        <div
          style={{
            position: "absolute",
            inset: 0,
            background:
              "linear-gradient(115deg, transparent 25%, rgba(255,255,255,.52) 47%, transparent 61%)",
            translate: interpolate(frame, [0, 299], ["-900px 0px", "900px 0px"], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
            mixBlendMode: "screen",
          }}
        />
        <div
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            height: 5,
            top: interpolate(frame, [0, 299], [-10, 1510], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.linear,
            }),
            background: "#e22d3e",
            boxShadow: "0 0 22px 5px rgba(226,45,62,.7)",
            opacity: 0.74,
          }}
        />
      </div>

      {particles.map((particle, index) => (
        <div
          key={`${particle.left}-${particle.top}`}
          style={{
            position: "absolute",
            left: particle.left,
            top: particle.top,
            width: particle.size,
            height: particle.size,
            borderRadius: "50%",
            backgroundColor: index % 2 === 0 ? "#ff334b" : "#dff7ff",
            boxShadow: index % 2 === 0 ? "0 0 20px #ff334b" : "0 0 18px #dff7ff",
            translate: interpolate(
              (frame + particle.delay) % durationInFrames,
              [0, durationInFrames - 1],
              ["0px 180px", `${index % 2 === 0 ? 54 : -48}px -980px`],
              {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
                easing: Easing.linear,
              },
            ),
            opacity: interpolate(
              (frame + particle.delay) % durationInFrames,
              [0, 30, 235, 299],
              [0, 0.9, 0.7, 0],
              {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              },
            ),
          }}
        />
      ))}

      <div
        style={{
          position: "absolute",
          left: 74,
          right: 74,
          top: 76,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          letterSpacing: 8,
          fontSize: 25,
          fontWeight: 700,
          opacity: interpolate(frame, [0, 24, 270, 299], [0, 1, 1, 0], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
        }}
      >
        <span>SELMA LABS</span>
        <span style={{color: "#ff334b"}}>MOTION TEST // 01</span>
      </div>

      <div
        style={{
          position: "absolute",
          left: 76,
          bottom: 78,
          opacity: interpolate(frame, [18, 44, 258, 292], [0, 1, 1, 0], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
        }}
      >
        <div style={{fontSize: 78, fontWeight: 900, letterSpacing: 12}}>AKIRA</div>
        <div style={{fontSize: 23, letterSpacing: 7, color: "#ff6878", marginTop: 10}}>
          APPROVED REFERENCE // CONTROLLED MOTION
        </div>
      </div>

      <div
        style={{
          position: "absolute",
          left: 42,
          top: 42,
          right: 42,
          bottom: 42,
          border: "1px solid rgba(255,255,255,.28)",
          borderRadius: 28,
          pointerEvents: "none",
        }}
      />
    </AbsoluteFill>
  );
};
