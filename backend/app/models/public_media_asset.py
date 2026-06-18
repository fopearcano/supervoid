from typing import Optional

from sqlmodel import Field

from app.models.base import BaseEntity
from app.models.enums import MediaAssetType


class PublicMediaAsset(BaseEntity, table=True):
    """A public, curated media asset (image / audio / video) the reader may load.

    Deliberately decoupled from the private ``Attachment`` model: public media
    is an explicit, published projection — never a direct reference to raw
    private files. ``file_path`` is a public, local-first path or URL.
    """

    __tablename__ = "public_media_assets"

    type: MediaAssetType = Field(default=MediaAssetType.IMAGE, index=True)
    title: str = Field(max_length=300)
    file_path: str = Field(max_length=600)
    poster_image: Optional[str] = Field(default=None, max_length=600)
    duration: Optional[float] = Field(default=None, ge=0)  # seconds
    loop: bool = Field(default=False)
    credits: Optional[str] = Field(default=None, max_length=400)
    public_visibility: bool = Field(default=True, index=True)
