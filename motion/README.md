# Strange Things Motion

Programmatic motion-design layer for the Shorts factory. Remotion owns visual
composition; FFmpeg remains responsible for the final H.264 delivery encode,
BT.709 tagging, narration mix, loudness normalization, and technical QA.

## Local checks

```powershell
npm install
npm run typecheck
npm run render:demo
```

Factory runs receive a JSON creative timeline containing exact scene and word
frames. The default demo intentionally uses generated gradients so the motion
system can be validated without licensed footage.
