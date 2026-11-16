# Test cases: mandatory book title and removing authors

Retest of two fixes: a book must have a title, and removing authors from a book removes only the given authors.

| Field | Value |
| --- | --- |
| Build | 9ee1369 (first run: 5edca17) |
| Date | 2026-11-16 |
| Account | librarian (`librarian@library.com`) |
| Executed | by script in Chrome and through the developer console; the admin part of TC-7 by hand |

**Preparation:** a fresh `main`, local run, migrations applied. Sign in as a librarian. For the API, use the Swagger page at `/api/docs/` in the same browser after signing in (session and CSRF token). Create temporary books for the checks and delete them afterwards.

## Mandatory book title

### TC-1. Creating a book on the site with an empty title

**Steps**

1. Books → create a book (`/book/create/`).
2. Leave the title empty and save. Repeat with a title made of spaces only.

**Expected result:** the book is not created; an error is shown next to the title field; the field is marked as required. With a normal title the book is created as before.

**Result:** Pass

### TC-2. Editing on the site

**Steps**

1. Open an existing book → Edit (`/book/update/<id>/`).
2. Erase the title (or replace it with spaces) and save.

**Expected result:** the changes are not saved, an error is shown next to the title, and the catalog keeps the old title. Changing other fields with a normal title is saved.

**Result:** Pass

### TC-3. Admin site

**Steps**

1. Open `/admin` → Books → Add book with an empty title.
2. Change an existing book and erase its title.

**Expected result:** in both cases an error is shown next to the field and nothing is saved.

**Result:** Pass

### TC-4. API

**Steps**

1. `POST /api/v1/book/` with `"name": ""`, with `"name": "   "` and without `name`.
2. `PUT /api/v1/book/<id>/` with an empty title.
3. `PATCH /api/v1/book/<id>/` with `"name": ""`.
4. `PATCH /api/v1/book/<id>/` without `name`, for example with `count` only.

**Expected result:** steps 1–3 answer `400` with an error for `name`, and nothing changes in the database. Step 4 answers `200`, the title stays and the other field changes. `POST` with a normal title answers `201`.

**Result:** Pass

## Removing only the given authors

The function that removes authors from a book is not called from any page or API route, so it is checked through the developer console.

### TC-5. Only the given author is removed

**Steps**

1. Prepare a book with 2–3 authors (on the site or in the admin site).
2. Note the authors of the book.
3. In the developer console, run the function that removes authors from this book, giving it one of its authors.
4. Look at the authors of the book again.

**Expected result:** only the given author is gone, the others stay. The author still exists on the Authors page and is still linked to their other books.

**Result:** Pass

### TC-6. Several authors, an empty list, `None`, an author the book does not have

**Steps**

1. Run the author removal function giving it two authors of the book.
2. Run it with an empty list, and then with no value at all.
3. Run it giving an author the book does not have.
4. Give it authors as objects, and then as ids.

**Expected result:** both authors disappear in step 1. In steps 2 and 3 nothing changes and there is no error. Both objects and ids are accepted.

**Result:** Pass

### TC-7. Regression: editing authors on the site and in the admin site

**Steps**

1. Change the list of authors of a book in the edit form (remove one, add another).
2. Do the same in the admin site. The authors of a book are read-only on the book page there, so the list is changed on the author's page (the Books field).

**Expected result:** exactly the chosen list is saved; other books of these authors do not change.

**Result:** Pass (the site form by script, the admin site by hand)
