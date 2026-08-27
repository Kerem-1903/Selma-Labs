from core.domain.value_objects.outfit import Outfit

def test_outfit_serialization():
    outfit = Outfit(
        id="outfit_1",
        character_id="char_1",
        description="Blue school uniform",
        reference_image_keys=["s3://bucket/ref1.png"]
    )

    data = outfit.to_dict()
    assert data["id"] == "outfit_1"
    assert data["description"] == "Blue school uniform"

    restored = Outfit.from_dict(data)
    assert restored.character_id == "char_1"
    assert "s3://bucket/ref1.png" in restored.reference_image_keys
