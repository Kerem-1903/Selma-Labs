from dataclasses import dataclass, field
from enum import Enum


class AnimeShapeKeyEnum(str, Enum):
    # Mouth / Phonemes
    MOUTH_CLOSED = "MOUTH_CLOSED"
    MOUTH_A = "MOUTH_A"
    MOUTH_E = "MOUTH_E"
    MOUTH_I = "MOUTH_I"
    MOUTH_O = "MOUTH_O"
    MOUTH_U = "MOUTH_U"
    MOUTH_SLIGHT_OPEN = "MOUTH_SLIGHT_OPEN"
    MOUTH_WIDE_OPEN = "MOUTH_WIDE_OPEN"
    MOUTH_TEETH_CONTACT = "MOUTH_TEETH_CONTACT"

    # Eyes & Brows
    EYE_BLINK_L = "EYE_BLINK_L"
    EYE_BLINK_R = "EYE_BLINK_R"
    EYE_SQUINT = "EYE_SQUINT"
    BROW_ANGRY = "BROW_ANGRY"
    BROW_SURPRISED = "BROW_SURPRISED"
    BROW_DETERMINED = "BROW_DETERMINED"
    SMILE_L = "SMILE_L"
    SMILE_R = "SMILE_R"


class StandardPoseEnum(str, Enum):
    IDLE_BREATHING = "IDLE_BREATHING"
    WALK_2STEP = "WALK_2STEP"
    HEAD_TURN = "HEAD_TURN"
    LOOK_AT_CAMERA = "LOOK_AT_CAMERA"
    ARM_RAISE = "ARM_RAISE"
    SPEAKING = "SPEAKING"
    SHOCK = "SHOCK"
    ANGER = "ANGER"


@dataclass(frozen=True)
class RigSpecification:
    has_ik_arm_l: bool
    has_ik_arm_r: bool
    has_ik_leg_l: bool
    has_ik_leg_r: bool
    has_fk_arm_l: bool
    has_fk_arm_r: bool
    has_fk_leg_l: bool
    has_fk_leg_r: bool
    has_secondary_hair: bool
    has_secondary_jacket: bool
    shape_keys: frozenset[str] = field(default_factory=frozenset)
    available_actions: frozenset[str] = field(default_factory=frozenset)

    def is_lipsync_ready(self) -> bool:
        """
        Check if the rig has the minimum required shape keys for basic lipsync.
        """
        required_phonemes = {
            AnimeShapeKeyEnum.MOUTH_A.value,
            AnimeShapeKeyEnum.MOUTH_E.value,
            AnimeShapeKeyEnum.MOUTH_I.value,
            AnimeShapeKeyEnum.MOUTH_O.value,
            AnimeShapeKeyEnum.MOUTH_U.value,
            AnimeShapeKeyEnum.MOUTH_CLOSED.value,
        }
        return required_phonemes.issubset(self.shape_keys)
