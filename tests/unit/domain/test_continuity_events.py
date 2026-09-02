from core.domain.events.continuity_event import (
    ContinuityEvent,
    CharacterEnteredLocation,
    CharacterChangedOutfit,
    CharacterPickedUpObject,
    CharacterDroppedObject,
    CharacterInjured,
    OutfitDamaged,
    ObjectBroken,
    CharacterEmotionChanged
)

def test_event_polymorphic_serialization():
    events = [
        CharacterEnteredLocation("CharacterEnteredLocation", 1, 10, "SH_001", "akira", "rooftop"),
        CharacterChangedOutfit("CharacterChangedOutfit", 1, 20, "SH_002", "akira", "battle_v2"),
        CharacterPickedUpObject("CharacterPickedUpObject", 1, 30, "SH_003", "akira", "katana_01"),
        CharacterDroppedObject("CharacterDroppedObject", 1, 40, "SH_004", "akira", "katana_01"),
        CharacterInjured("CharacterInjured", 1, 50, "SH_005", "akira", "cut on right cheek"),
        OutfitDamaged("OutfitDamaged", 1, 60, "SH_006", "akira", "battle_v2", "left_sleeve"),
        ObjectBroken("ObjectBroken", 1, 70, "SH_007", "katana_01"),
        CharacterEmotionChanged("CharacterEmotionChanged", 1, 80, "SH_008", "akira", "angry")
    ]

    for original_event in events:
        data = original_event.to_dict()
        restored_event = ContinuityEvent.from_dict(data)

        assert isinstance(restored_event, original_event.__class__)
        assert restored_event.schema_version == original_event.schema_version
        assert restored_event.sequence == original_event.sequence
        assert restored_event.shot_id == original_event.shot_id

        # Check subclass-specific fields
        if hasattr(original_event, "character_id"):
            assert restored_event.character_id == original_event.character_id
        if hasattr(original_event, "object_id"):
            assert restored_event.object_id == original_event.object_id
        if hasattr(original_event, "region"):
            assert restored_event.region == original_event.region
        if hasattr(original_event, "emotion"):
            assert restored_event.emotion == original_event.emotion
        if hasattr(original_event, "location"):
            assert restored_event.location == original_event.location
