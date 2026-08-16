export type SceneMode = "hook" | "network" | "local" | "payment" | "gps" | "calls" | "news" | "logistics" | "critical" | "evening" | "recovery" | "checklist" | "outro";

export type SceneSpec = {
  id: string;
  eyebrow: string;
  headline: string;
  accent: string;
  mode: SceneMode;
  clips: string[];
  metric?: string;
  metricLabel?: string;
  mascot?: "pointer" | "marker" | "stop" | "thumbs-up";
};

export type Chapter = {id: string; title: string; startMs: number; endMs: number};
export type Word = {text: string; startMs: number; endMs: number};
