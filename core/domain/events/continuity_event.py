from dataclasses import dataclass
from typing import Dict, Any

@dataclass(frozen=True)
class ContinuityEvent:
    event_type: str
    schema_version: int
    sequence: int
    shot_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "shot_id": self.shot_id,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "ContinuityEvent":
        event_type = data.get("event_type")
        if event_type == "CharacterEnteredLocation":
            return CharacterEnteredLocation.from_dict(data)
        elif event_type == "CharacterChangedOutfit":
            return CharacterChangedOutfit.from_dict(data)
        elif event_type == "CharacterPickedUpObject":
            return CharacterPickedUpObject.from_dict(data)
        elif event_type == "CharacterDroppedObject":
            return CharacterDroppedObject.from_dict(data)
        elif event_type == "CharacterInjured":
            return CharacterInjured.from_dict(data)
        elif event_type == "OutfitDamaged":
            return OutfitDamaged.from_dict(data)
        elif event_type == "ObjectBroken":
            return ObjectBroken.from_dict(data)
        elif event_type == "CharacterEmotionChanged":
            return CharacterEmotionChanged.from_dict(data)
        else:
            raise ValueError(f"Unknown ContinuityEvent type: {event_type}")

@dataclass(frozen=True)
class CharacterEnteredLocation(ContinuityEvent):
    character_id: str
    location: str

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({"character_id": self.character_id, "location": self.location})
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CharacterEnteredLocation":
        return cls(
            event_type=data["event_type"],
            schema_version=data["schema_version"],
            sequence=data["sequence"],
            shot_id=data["shot_id"],
            character_id=data["character_id"],
            location=data["location"]
        )

@dataclass(frozen=True)
class CharacterChangedOutfit(ContinuityEvent):
    character_id: str
    outfit_id: str

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({"character_id": self.character_id, "outfit_id": self.outfit_id})
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CharacterChangedOutfit":
        return cls(
            event_type=data["event_type"],
            schema_version=data["schema_version"],
            sequence=data["sequence"],
            shot_id=data["shot_id"],
            character_id=data["character_id"],
            outfit_id=data["outfit_id"]
        )

@dataclass(frozen=True)
class CharacterPickedUpObject(ContinuityEvent):
    character_id: str
    object_id: str

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({"character_id": self.character_id, "object_id": self.object_id})
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CharacterPickedUpObject":
        return cls(
            event_type=data["event_type"],
            schema_version=data["schema_version"],
            sequence=data["sequence"],
            shot_id=data["shot_id"],
            character_id=data["character_id"],
            object_id=data["object_id"]
        )

@dataclass(frozen=True)
class CharacterDroppedObject(ContinuityEvent):
    character_id: str
    object_id: str

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({"character_id": self.character_id, "object_id": self.object_id})
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CharacterDroppedObject":
        return cls(
            event_type=data["event_type"],
            schema_version=data["schema_version"],
            sequence=data["sequence"],
            shot_id=data["shot_id"],
            character_id=data["character_id"],
            object_id=data["object_id"]
        )

@dataclass(frozen=True)
class CharacterInjured(ContinuityEvent):
    character_id: str
    injury: str

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({"character_id": self.character_id, "injury": self.injury})
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CharacterInjured":
        return cls(
            event_type=data["event_type"],
            schema_version=data["schema_version"],
            sequence=data["sequence"],
            shot_id=data["shot_id"],
            character_id=data["character_id"],
            injury=data["injury"]
        )

@dataclass(frozen=True)
class OutfitDamaged(ContinuityEvent):
    character_id: str
    outfit_id: str
    region: str

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({"character_id": self.character_id, "outfit_id": self.outfit_id, "region": self.region})
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OutfitDamaged":
        return cls(
            event_type=data["event_type"],
            schema_version=data["schema_version"],
            sequence=data["sequence"],
            shot_id=data["shot_id"],
            character_id=data["character_id"],
            outfit_id=data["outfit_id"],
            region=data["region"]
        )

@dataclass(frozen=True)
class ObjectBroken(ContinuityEvent):
    object_id: str

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({"object_id": self.object_id})
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ObjectBroken":
        return cls(
            event_type=data["event_type"],
            schema_version=data["schema_version"],
            sequence=data["sequence"],
            shot_id=data["shot_id"],
            object_id=data["object_id"]
        )

@dataclass(frozen=True)
class CharacterEmotionChanged(ContinuityEvent):
    character_id: str
    emotion: str

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({"character_id": self.character_id, "emotion": self.emotion})
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CharacterEmotionChanged":
        return cls(
            event_type=data["event_type"],
            schema_version=data["schema_version"],
            sequence=data["sequence"],
            shot_id=data["shot_id"],
            character_id=data["character_id"],
            emotion=data["emotion"]
        )
