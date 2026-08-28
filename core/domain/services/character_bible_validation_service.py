from core.domain.entities.character_bible import CharacterBible
from core.domain.value_objects.character_identity import ReferenceView
from core.domain.value_objects.character_bible_validation_report import CharacterBibleValidationReport

class CharacterBibleValidationService:
    """
    Domain service to evaluate the structural integrity and multi-view
    completeness of a Character Bible, independent of physical storage.
    """

    # Core views required for a "complete" character pack
    REQUIRED_VIEWS = {
        ReferenceView.FRONT,
        ReferenceView.THREE_QUARTER_LEFT,
        ReferenceView.PROFILE_LEFT,
        ReferenceView.BACK,
        ReferenceView.PROFILE_RIGHT,
        ReferenceView.THREE_QUARTER_RIGHT,
        ReferenceView.FACE_CLOSEUP
    }

    @staticmethod
    def validate(bible: CharacterBible) -> CharacterBibleValidationReport:
        missing_views = []
        invalid_references = []

        # Check for missing required views
        for required_view in CharacterBibleValidationService.REQUIRED_VIEWS:
            if required_view not in bible.reference_pack:
                missing_views.append(required_view)

        # Validate existing references
        for view, ref in bible.reference_pack.items():
            if not ref.asset_id:
                invalid_references.append(f"Reference for {view.value} is missing asset_id")
            if ref.character_id != bible.character_id:
                invalid_references.append(f"Reference {ref.id} belongs to different character")

        is_complete = len(missing_views) == 0 and len(invalid_references) == 0

        return CharacterBibleValidationReport(
            missing_views=missing_views,
            invalid_references=invalid_references,
            is_complete=is_complete
        )
