# Narration and Pronunciation Assets

`pronunciation_lexicon.json` is the channel-owned pronunciation dictionary.
Entries are applied immediately before synthesis and every replacement is
stored with the resulting `VoiceTrack`. Keep entries short and listen to a
preview before approving a new spelling.

For recorded narration, use a voice owned by the channel or backed by explicit
speaker consent. Cleanup tools do not create usage rights. A local TTS engine is
also not enough by itself: its voice model card must explicitly permit the
channel's commercial use.
