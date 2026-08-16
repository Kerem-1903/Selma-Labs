import React, {useMemo} from "react";
import type {Word} from "./types";

export const Captions: React.FC<{words: Word[]; now: number}> = ({words, now}) => {
  const active = useMemo(() => {
    const index = words.findIndex((word) => now >= word.startMs - 35 && now <= word.endMs + 120);
    if (index < 0) return [];
    const start = Math.floor(index / 7) * 7;
    return words.slice(start, start + 7);
  }, [now, words]);
  if (!active.length) return null;
  return <div style={{position:"absolute",left:130,right:130,bottom:28,zIndex:200,display:"flex",justifyContent:"center",pointerEvents:"none"}}>
    <div style={{maxWidth:1540,padding:"13px 25px 15px",borderRadius:14,background:"rgba(2,7,13,.86)",borderBottom:"5px solid #ffd42a",boxShadow:"0 12px 38px rgba(0,0,0,.5)",font:"900 38px/1.15 Arial",textAlign:"center",textTransform:"uppercase",letterSpacing:.2}}>
      {active.map((word,index)=><React.Fragment key={`${word.startMs}-${index}`}><span style={{color:now>=word.startMs&&now<=word.endMs?"#ffd42a":"#f8fbff"}}>{word.text}</span>{index<active.length-1?" ":""}</React.Fragment>)}
    </div>
  </div>;
};
