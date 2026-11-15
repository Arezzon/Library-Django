# Book covers

Book detail pages show a small, locally served cover beside the title. A shared light frame, contained image proportions and a maximum width of 80 pixels keep the existing layout compact. Mobile covers use 64 × 96 pixels. Catalog lists remain unchanged.

The nine sample titles in `library/seed_db.py` are matched by trimmed, case-insensitive title through `library/book/covers.json`. Matching does not depend on database IDs or reseeding, so existing records receive covers immediately. Other titles use a neutral local SVG placeholder. New books do not automatically query an external image service.

To curate another cover, place the downloaded image in `library/book/static/book/covers/` and add its normalized title, static `file`, Open Library work `source`, and original `image_url` to the manifest. Verify both author and title before adding an image. Run `python manage.py collectstatic --noinput` when deploying outside the standard image build. The manifest records provenance; third-party cover artwork remains with its respective rights holders. Covers illustrate works, not a guaranteed physical edition, since the catalog does not store ISBNs.

Sources: [Open Library Covers API](https://openlibrary.org/dev/docs/api/covers); per-work and image URLs are in the manifest. Original cover artwork is preserved; presentation is standardized through the frame rather than changing its colors or cropping its typography.
