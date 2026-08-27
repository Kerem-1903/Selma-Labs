from core.domain.entities.character import Character

def test_character_initialization():
    char = Character(
        id="char_1",
        name="Akira",
        face_identity_notes="Sharp jawline, red eyes.",
        body_proportions="Tall and athletic."
    )
    assert char.id == "char_1"
    assert char.name == "Akira"
    assert char.face_identity_notes == "Sharp jawline, red eyes."

def test_character_serialization():
    char = Character(
        id="char_1",
        name="Akira",
        face_identity_notes="notes",
        body_proportions="proportions"
    )
    data = char.to_dict()
    assert data["name"] == "Akira"

    char_restored = Character.from_dict(data)
    assert char_restored.id == "char_1"
    assert char_restored.name == "Akira"
    assert char_restored.face_identity_notes == "notes"
