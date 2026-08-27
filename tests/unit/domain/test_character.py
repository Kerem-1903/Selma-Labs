from core.domain.entities.character import Character

def test_character_initialization():
    char = Character(
        id="char_1",
        name="Akira",
        face_identity_notes="Sharp jawline, red eyes.",
        body_proportions="Tall and athletic.",
        hair="Spiky black",
        eye_color="Red",
        silhouette="Slender",
        style_constraints=["anime", "cyberpunk"]
    )
    assert char.id == "char_1"
    assert char.name == "Akira"
    assert char.face_identity_notes == "Sharp jawline, red eyes."
    assert char.hair == "Spiky black"
    assert char.eye_color == "Red"
    assert "anime" in char.style_constraints

def test_character_serialization():
    char = Character(
        id="char_1",
        name="Akira",
        face_identity_notes="notes",
        body_proportions="proportions",
        hair="black",
        eye_color="blue",
        silhouette="tall",
        style_constraints=["gothic"]
    )
    data = char.to_dict()
    assert data["name"] == "Akira"
    assert data["hair"] == "black"

    char_restored = Character.from_dict(data)
    assert char_restored.id == "char_1"
    assert char_restored.name == "Akira"
    assert char_restored.face_identity_notes == "notes"
    assert char_restored.eye_color == "blue"
    assert "gothic" in char_restored.style_constraints
