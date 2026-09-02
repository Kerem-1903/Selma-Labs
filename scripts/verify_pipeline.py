#!/usr/bin/env python3
"""
Offline End-to-End Pipeline Smoke Test for SELMA Labs.

Verifies the entire internal domain & application pipeline from Script Generation
down to Timeline Assembly and Subtitle Export using fake in-memory adapters.

Runs completely offline without network calls, external API keys, or paid services.
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.application.services.scene_asset_matching_service import SceneAssetMatchingService
from core.application.services.scene_planning_service import ScenePlanningService
from core.application.services.script_service import ScriptService
from core.application.services.subtitle_service import SubtitleService
from core.application.services.timeline_service import TimelineService
from core.application.services.video_search_service import VideoSearchService
from core.application.services.voice_service import VoiceService
from core.domain.entities.media_asset import MediaAsset
from core.domain.entities.script import Script
from core.domain.ports.scene_planning_port import ScenePlanningPort
from core.domain.ports.script_generator_port import ScriptGeneratorPort
from core.domain.ports.video_source_port import VideoSourcePort
from core.domain.ports.voice_generator_port import VoiceGeneratorPort
from core.domain.value_objects.generated_audio import GeneratedAudio
from core.domain.value_objects.scene import Scene
from infrastructure.storage.local_fs_storage import LocalFsStorage


class FakeScriptGenerator(ScriptGeneratorPort):
    @property
    def provider_identity(self) -> str:
        return "fake:script"

    async def generate_script(self, topic: str, target_duration_seconds: int) -> Script:
        narration = (
            "Artificial Intelligence is rapidly transforming software development. "
            "Engineers use intelligent AI assistants to write cleaner code, generate "
            "comprehensive tests, debug complex runtime issues, and deploy applications "
            "faster than ever before."
        )
        return Script.create(
            topic=topic,
            full_text=narration,
            target_duration_seconds=target_duration_seconds,
            provider_used=self.provider_identity,
        )


class FakeVoiceGenerator(VoiceGeneratorPort):
    @property
    def provider_identity(self) -> str:
        return "fake:voice"

    async def generate_voice(
        self, text: str, voice_name: str, *, direction=None
    ) -> GeneratedAudio:
        return GeneratedAudio(
            audio_bytes=b"FAKE_AUDIO_DATA_MP3",
            duration_seconds=15.0,
            sample_rate=44100,
            provider=self.provider_identity,
            voice_name=voice_name,
        )


class FakeScenePlanner(ScenePlanningPort):
    @property
    def provider_identity(self) -> str:
        return "fake:scene_planner"

    async def plan_scenes(self, narration_text: str) -> list[Scene]:
        return [
            Scene(
                index=0,
                narration="Artificial Intelligence is rapidly transforming software development.",
                search_keywords=["AI", "software"],
                detected_objects=["robot", "computer"],
                location="office",
                mood="futuristic",
                visual_priority="high",
            ),
            Scene(
                index=1,
                narration="Engineers use intelligent AI assistants to write cleaner code.",
                search_keywords=["engineers", "coding"],
                detected_objects=["developer", "screen"],
                location="desk",
                mood="focused",
                visual_priority="medium",
            ),
        ]


class FakeVideoSource(VideoSourcePort):
    @property
    def provider_identity(self) -> str:
        return "fake:video_source"

    async def search(self, query: str, max_results: int) -> list[MediaAsset]:
        return [
            MediaAsset(
                id=f"asset-{query}-1",
                provider=self.provider_identity,
                provider_asset_id=f"p-{query}-1",
                media_type="video",
                original_url="http://example.com/video.mp4",
                thumbnail_url="http://example.com/thumb.jpg",
                width=1080,
                height=1920,
                duration_seconds=10.0,
                fps=30.0,
                tags=[query],
                attribution="Test Attribution",
                license="CC0",
            )
        ]

    async def download(self, asset: MediaAsset) -> bytes:
        return b"FAKE_VIDEO_BYTES_MP4"


async def run_smoke_test() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        storage = LocalFsStorage(root_dir=tmp_dir)

        script_service = ScriptService(FakeScriptGenerator())
        voice_service = VoiceService(
            provider=FakeVoiceGenerator(),
            storage=storage,
            default_voice_name="test_voice",
        )
        scene_service = ScenePlanningService(FakeScenePlanner())
        video_search_service = VideoSearchService(FakeVideoSource(), storage)
        matching_service = SceneAssetMatchingService(video_search_service)
        timeline_service = TimelineService(video_search_service)
        subtitle_service = SubtitleService(storage=storage)

        print("[1/6] Generating Script...")
        script = await script_service.generate("AI Code Assistance", 15)
        print(f"      OK: Script ID '{script.id}', Word Count: {script.estimated_word_count}")

        print("[2/6] Generating Voice Narration...")
        voice_track = await voice_service.generate(script)
        print(f"      OK: Voice Track ID '{voice_track.audio_id}', Duration: {voice_track.duration_seconds:.1f}s")

        print("[3/6] Planning Scenes...")
        scene_plan = await scene_service.plan(script, voice_track)
        print(f"      OK: Scene Plan ID '{scene_plan.id}', Scenes: {len(scene_plan.scenes)}")

        print("[4/6] Matching Visual Assets...")
        match_plan = await matching_service.match(scene_plan)
        print(f"      OK: Match Plan ID '{match_plan.id}', Matches: {len(match_plan.matches)}")

        print("[5/6] Assembling Timeline...")
        timeline = await timeline_service.create(match_plan)
        print(f"      OK: Timeline ID '{timeline.id}', Clips: {len(timeline.clips)}")

        print("[6/6] Generating & Exporting Subtitles...")
        subtitle_track = subtitle_service.generate(scene_plan)
        exported_refs = await subtitle_service.export(subtitle_track, "subtitles/smoke_test")
        print(f"      OK: Subtitle SRT -> {exported_refs['srt'].path}")
        print(f"      OK: Subtitle VTT -> {exported_refs['vtt'].path}")

        print("\n==================================================")
        print("SUCCESS: Offline End-to-End Pipeline Smoke Test Passed!")
        print("==================================================")


if __name__ == "__main__":
    asyncio.run(run_smoke_test())
