import hashlib
import io
from PIL import Image

from core.domain.entities.character_bible import CharacterBible
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.character_identity import ReferenceView
from core.domain.value_objects.character_reference import CharacterReference


class MultiviewAssetRegistrationService:
    def __init__(self, storage: StoragePort):
        self.storage = storage

    async def register_multiview_asset(
        self,
        bible: CharacterBible,
        image_path: str,
        version: str = "v1"
    ) -> CharacterBible:
        """
        Splits a 5-view model sheet into standalone views and updates the CharacterBible.
        The layout is assumed to be a horizontal strip of 5 equal-width views:
        FRONT, THREE_QUARTER_LEFT, PROFILE_LEFT, BACK, FACE_CLOSEUP.
        """
        try:
            img = Image.open(image_path)
            img.load()
        except Exception as e:
            raise ValueError(f"Failed to load image from {image_path}: {e}")

        width, height = img.size
        # The 5 views to split into
        views = [
            ReferenceView.FRONT,
            ReferenceView.THREE_QUARTER_LEFT,
            ReferenceView.PROFILE_LEFT,
            ReferenceView.BACK,
            ReferenceView.FACE_CLOSEUP,
        ]

        if width < len(views):
            raise ValueError(f"Image width ({width}) is too small to contain {len(views)} views")

        view_width = width // len(views)

        for i, view in enumerate(views):
            left = i * view_width
            right = (i + 1) * view_width
            # The last view gets the remainder of the width if it's not evenly divisible
            if i == len(views) - 1:
                right = width

            box = (left, 0, right, height)
            cropped = img.crop(box)

            # Save cropped image to bytes
            img_byte_arr = io.BytesIO()
            cropped.save(img_byte_arr, format='PNG')
            img_bytes = img_byte_arr.getvalue()

            # Calculate SHA-256 hash
            content_hash = hashlib.sha256(img_bytes).hexdigest()

            # Define portable storage key
            key = f"characters/{bible.character_id}/views/{version}/{view.value.lower()}.png"

            # Save to storage port
            await self.storage.save(key, img_bytes, content_type="image/png")

            # Update Character Bible
            ref = CharacterReference(
                id=f"{bible.character_id}-{view.value.lower()}-{version}",
                character_id=bible.character_id,
                view=view,
                asset_id=f"{bible.character_id}-{view.value.lower()}-{version}",
                storage_key=key,
                content_type="image/png",
                content_hash=content_hash,
                revision=1
            )
            bible.reference_pack[view] = ref

        return bible
