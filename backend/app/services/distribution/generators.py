"""Distribution-package generators for each channel.

Each generator builds a JSON-safe manifest and a validation checklist for an
edition. They prepare and validate packages; they do not upload anything.
"""
from __future__ import annotations

from typing import Callable

from app.models.enums import (
    DistributionChannel,
    EditionFormat,
    EditionIdentifierType,
)
from app.services.distribution.base import (
    EditionContext,
    PackageResult,
    na,
    prefer,
    require,
)


def is_isbn13(value: str | None) -> bool:
    digits = [c for c in (value or "") if c.isdigit()]
    if len(digits) != 13:
        return False
    total = sum((1 if i % 2 == 0 else 3) * int(d) for i, d in enumerate(digits))
    return total % 10 == 0


_ONIX_PRODUCT_FORM = {
    EditionFormat.HARDCOVER: "BB",
    EditionFormat.TRADE_PAPERBACK: "BC",
    EditionFormat.MASS_MARKET: "BC",
    EditionFormat.POD_PAPERBACK: "BC",
    EditionFormat.EBOOK: "EB",
    EditionFormat.AUDIOBOOK: "AJ",
    EditionFormat.WEB_COMIC: "EB",
    EditionFormat.PDF: "EB",
    EditionFormat.BOX_SET: "BF",
    EditionFormat.OTHER: "00",
}


def _contributor(ctx: EditionContext) -> list[dict]:
    if not ctx.author_name:
        return []
    return [{"SequenceNumber": 1, "ContributorRole": "A01", "PersonName": ctx.author_name}]


# --- ONIX ------------------------------------------------------------------


def generate_onix(ctx: EditionContext) -> PackageResult:
    e = ctx.edition
    has_identifier = bool(e.identifier) and e.identifier_type != EditionIdentifierType.NONE
    is_isbn = e.identifier_type in (
        EditionIdentifierType.ISBN_13,
        EditionIdentifierType.ISBN_10,
    )
    manifest = {
        "standard": "ONIX 3.0 (subset)",
        "RecordReference": e.id,
        "NotificationType": "03",
        "ProductIdentifier": {
            "type": e.identifier_type.value,
            "value": e.identifier,
        },
        "DescriptiveDetail": {
            "ProductForm": _ONIX_PRODUCT_FORM.get(e.format, "00"),
            "TitleDetail": {"TitleText": ctx.title, "Subtitle": ctx.subtitle},
            "Contributor": _contributor(ctx),
            "Language": e.language,
            "Extent": {"PageCount": e.page_count},
            "Measure": {"width_mm": e.width_mm, "height_mm": e.height_mm},
        },
        "PublishingDetail": {
            "Imprint": e.imprint,
            "PublishingStatus": e.distribution_status.value,
            "PublishingDate": ctx.pub_date,
            "SalesRights": {"Territory": e.territory},
        },
        "ProductSupply": {"Price": ctx.money},
        "Description": ctx.synopsis,
    }
    checklist = [
        require("identifier", "Product identifier", has_identifier,
                fail_detail="An ISBN/identifier is required for ONIX."),
        prefer("isbn", "ISBN as identifier", is_isbn,
               warn_detail="ONIX feeds usually expect an ISBN-13."),
        (require("isbn_valid", "Valid ISBN-13",
                 is_isbn13(e.identifier),
                 fail_detail="ISBN-13 checksum failed.")
         if e.identifier_type == EditionIdentifierType.ISBN_13
         else na("isbn_valid", "Valid ISBN-13", "Not an ISBN-13.")),
        require("title", "Title", bool(ctx.title), fail_detail="Title is required."),
        prefer("contributor", "Contributor", bool(ctx.author_name),
               warn_detail="No contributor (author) set."),
        prefer("pub_date", "Publishing date", bool(ctx.pub_date),
               warn_detail="No publication date set."),
        prefer("price", "Price", e.price is not None,
               warn_detail="No price set."),
        prefer("description", "Description", bool(ctx.synopsis),
               warn_detail="No description/synopsis."),
        require("territory", "Sales territory", bool(e.territory), fail_detail="Territory required."),
    ]
    return PackageResult(DistributionChannel.ONIX.value, manifest, checklist)


# --- Amazon KDP ------------------------------------------------------------


def generate_kdp(ctx: EditionContext) -> PackageResult:
    e = ctx.edition
    keywords = ctx.meta("keywords", []) or []
    categories = ctx.meta("categories", []) or ctx.meta("bisac", []) or []
    cover = ctx.has_file("cover")
    interior = ctx.has_file("interior", "manuscript", "epub", "pdf")
    price = e.price
    price_ok = price is not None and 0.99 <= float(price) <= 200
    manifest = {
        "channel": "kdp",
        "title": ctx.title,
        "subtitle": ctx.subtitle,
        "author": ctx.author_name,
        "description": ctx.synopsis,
        "language": e.language,
        "keywords": keywords[:7],
        "categories": categories,
        "price": ctx.money,
        "is_ebook": e.format == EditionFormat.EBOOK,
        "cover_file": ctx.file("cover"),
        "interior_file": ctx.file("interior", "manuscript", "epub", "pdf"),
        "territory_rights": e.territory,
        "note": "Prepared for manual upload to Amazon KDP; not submitted.",
    }
    checklist = [
        require("title", "Title", bool(ctx.title), fail_detail="Title is required."),
        require("description", "Description", bool(ctx.synopsis),
                fail_detail="KDP requires a book description."),
        require("cover", "Cover file", cover, fail_detail="A cover file is required."),
        require("interior", "Interior/manuscript file", interior,
                fail_detail="An interior (manuscript/epub/pdf) file is required."),
        prefer("keywords", "Up to 7 keywords", 0 < len(keywords) <= 7,
               warn_detail="Provide 1–7 keywords (extras are dropped)."),
        prefer("categories", "Categories", bool(categories),
               warn_detail="No categories/BISAC set."),
        prefer("price", "Price in KDP range", bool(price_ok),
               warn_detail="Price should be set within KDP's $0.99–$200 range."),
        na("isbn", "ISBN", "Optional — KDP can assign an ASIN."),
    ]
    return PackageResult(DistributionChannel.KDP.value, manifest, checklist)


# --- IngramSpark-style print ----------------------------------------------


def generate_ingram(ctx: EditionContext) -> PackageResult:
    e = ctx.edition
    is_isbn = e.identifier_type in (
        EditionIdentifierType.ISBN_13,
        EditionIdentifierType.ISBN_10,
    )
    interior_pdf = ctx.has_file("interior", "pdf")
    cover_pdf = ctx.has_file("cover", "cover_pdf")
    manifest = {
        "channel": "ingram",
        "title": ctx.title,
        "isbn": e.identifier if is_isbn else None,
        "trim_size": e.trim_size,
        "page_count": e.page_count,
        "spine_mm": e.spine_mm,
        "paper": ctx.meta("paper", "white"),
        "binding": ctx.meta("binding", e.format.value),
        "interior_pdf": ctx.file("interior", "pdf"),
        "cover_pdf": ctx.file("cover", "cover_pdf"),
        "price": ctx.money,
        "returns": ctx.meta("returns", "no"),
        "discount": ctx.meta("discount", None),
        "territory": e.territory,
        "note": "Print preparation package; not submitted to a printer.",
    }
    checklist = [
        require("isbn", "ISBN", is_isbn and bool(e.identifier),
                fail_detail="Print distribution requires an ISBN."),
        require("trim_size", "Trim size", bool(e.trim_size),
                fail_detail="Trim size is required for print."),
        require("page_count", "Page count", bool(e.page_count),
                fail_detail="Page count is required to compute the spine."),
        require("interior_pdf", "Interior PDF", interior_pdf,
                fail_detail="A print-ready interior PDF is required."),
        require("cover_pdf", "Cover PDF", cover_pdf,
                fail_detail="A print-ready cover PDF (with spine) is required."),
        prefer("spine", "Spine width", e.spine_mm is not None,
               warn_detail="Spine width not set; compute from page count + paper."),
        prefer("price", "Price", e.price is not None, warn_detail="No list price set."),
    ]
    return PackageResult(DistributionChannel.INGRAM.value, manifest, checklist)


# --- GlobalComix / web-reader ----------------------------------------------


def generate_globalcomix(ctx: EditionContext) -> PackageResult:
    e = ctx.edition
    pages = [f for f in (e.files or []) if isinstance(f, dict) and f.get("role") == "page"]
    page_count = len(pages) or (e.page_count or 0)
    cover = ctx.has_file("cover")
    is_comic = e.format == EditionFormat.WEB_COMIC or (
        ctx.work is not None and ctx.work.work_type.value == "graphic_novel"
    )
    reading_direction = ctx.meta("reading_direction")
    manifest = {
        "channel": "globalcomix",
        "title": ctx.title,
        "series": ctx.meta("series", ctx.title),
        "language": e.language,
        "cover_file": ctx.file("cover"),
        "pages": pages,
        "page_count": page_count,
        "reading_direction": reading_direction or "ltr",
        "age_rating": ctx.meta("age_rating"),
        "tags": ctx.meta("tags", []),
        "synopsis": ctx.synopsis,
        "note": "Web-reader package; not published to the public reader.",
    }
    checklist = [
        prefer("comic_format", "Comic/graphic-novel format", bool(is_comic),
               warn_detail="Edition is not a web comic / graphic novel."),
        require("pages", "Pages", page_count > 0,
                fail_detail="At least one page is required for a web-reader package."),
        require("cover", "Cover image", cover, fail_detail="A cover image is required."),
        prefer("reading_direction", "Reading direction", bool(reading_direction),
               warn_detail="Reading direction not set (defaulting to ltr)."),
        prefer("age_rating", "Age rating", bool(ctx.meta("age_rating")),
               warn_detail="No age rating set."),
        prefer("synopsis", "Synopsis", bool(ctx.synopsis), warn_detail="No synopsis."),
    ]
    return PackageResult(DistributionChannel.GLOBALCOMIX.value, manifest, checklist)


# --- Press kit -------------------------------------------------------------


def generate_press_kit(ctx: EditionContext) -> PackageResult:
    e = ctx.edition
    manifest = {
        "channel": "press_kit",
        "title": ctx.title,
        "subtitle": ctx.subtitle,
        "logline": ctx.meta("logline"),
        "synopsis": ctx.synopsis,
        "author": ctx.author_name,
        "author_bio": ctx.meta("author_bio"),
        "cover_image": ctx.file("cover"),
        "key_art": ctx.file("key_art", "art"),
        "praise": ctx.meta("praise", []),
        "release_date": ctx.pub_date,
        "press_contact": ctx.meta("press_contact"),
        "boilerplate": ctx.meta("boilerplate"),
        "format": e.format.value,
        "note": "Press kit assembled from catalogue metadata.",
    }
    checklist = [
        require("synopsis", "Synopsis", bool(ctx.synopsis),
                fail_detail="A synopsis is required for a press kit."),
        require("cover", "Cover image", ctx.has_file("cover"),
                fail_detail="A cover image is required."),
        prefer("author_bio", "Author bio", bool(ctx.meta("author_bio")),
               warn_detail="No author bio."),
        prefer("key_art", "Key art", ctx.has_file("key_art", "art"),
               warn_detail="No key art beyond the cover."),
        prefer("release_date", "Release date", bool(ctx.pub_date),
               warn_detail="No release date set."),
        prefer("press_contact", "Press contact", bool(ctx.meta("press_contact")),
               warn_detail="No press contact provided."),
        prefer("praise", "Praise/quotes", bool(ctx.meta("praise")),
               warn_detail="No praise/quotes yet."),
    ]
    return PackageResult(DistributionChannel.PRESS_KIT.value, manifest, checklist)


# --- Reviewer / ARC --------------------------------------------------------


def generate_arc(ctx: EditionContext) -> PackageResult:
    e = ctx.edition
    arc_file = ctx.file("arc", "epub", "pdf")
    manifest = {
        "channel": "arc",
        "title": ctx.title,
        "author": ctx.author_name,
        "synopsis": ctx.synopsis,
        "isbn": e.identifier,
        "publication_date": ctx.pub_date,
        "embargo_date": ctx.meta("embargo_date"),
        "arc_file": arc_file,
        "review_guidelines": ctx.meta("review_guidelines"),
        "review_by_date": ctx.meta("review_by_date"),
        "contact": ctx.meta("press_contact"),
        "note": "Advance review copy package for manual distribution to reviewers.",
    }
    checklist = [
        require("arc_file", "ARC file", arc_file is not None,
                fail_detail="An ARC file (epub/pdf) is required."),
        require("synopsis", "Synopsis", bool(ctx.synopsis),
                fail_detail="A synopsis is required for reviewers."),
        prefer("pub_date", "Publication date", bool(ctx.pub_date),
               warn_detail="No publication date — reviewers need a timeline."),
        prefer("embargo", "Embargo / review-by date",
               bool(ctx.meta("embargo_date") or ctx.meta("review_by_date")),
               warn_detail="No embargo or review-by date set."),
        prefer("guidelines", "Review guidelines", bool(ctx.meta("review_guidelines")),
               warn_detail="No review guidelines provided."),
        prefer("contact", "Contact", bool(ctx.meta("press_contact")),
               warn_detail="No contact for review queries."),
    ]
    return PackageResult(DistributionChannel.ARC.value, manifest, checklist)


GENERATORS: dict[DistributionChannel, Callable[[EditionContext], PackageResult]] = {
    DistributionChannel.ONIX: generate_onix,
    DistributionChannel.KDP: generate_kdp,
    DistributionChannel.INGRAM: generate_ingram,
    DistributionChannel.GLOBALCOMIX: generate_globalcomix,
    DistributionChannel.PRESS_KIT: generate_press_kit,
    DistributionChannel.ARC: generate_arc,
}
