# Contract: Runtime dependency list (PR 1)

**Requirements**: FR-001–FR-003, FR-015, FR-016 | **Research**: R1, R2 |
**Data model**: [§1](../data-model.md#1-runtime-dependency-list-requirementstxt-pr-1)

## Who reads it

| Consumer | How | Must keep working |
|---|---|---|
| `Dockerfile` | `COPY requirements.txt` then `pip install -r /app/requirements.txt` | The image builds on `linux/amd64` and `linux/arm64` from wheels only |
| README local setup | `python -m pip install -r requirements.txt` from the repository root (Windows PowerShell and Linux/macOS) | One step installs every runtime dependency (SC-007) |
| Dependabot | Opens pull requests against the single file | Each bump touches one file |

`library/requirements.txt` no longer exists. Current files must not mention it (FR-016). Past
specs, bridge snapshots and earlier changelog entries keep their text.

## Format

```text
# Runtime dependencies for the Django Library app: the only runtime dependency list.
# Installed by the Dockerfile and by local development (see README).
# Direct dependencies are listed first. The transitive group is `pip freeze` from the built
# Linux image; regenerate it after changing a direct pin (see below).

# --- Direct ---
Django==5.2.18
djangorestframework==3.18.3
…
celery[redis]==5.6.3
kombu==5.6.2
redis==6.4.0

# --- Transitive (pinned for reproducible builds) ---
amqp==5.4.1
…
```

## Regenerating the transitive group

1. Change the direct pins.
2. Build the image without the old transitive pins, from a temporary copy of the file that holds
   only the direct group.
3. Run `pip freeze --exclude-editable` inside it.
4. Keep every package that is not in the direct group.

`pip freeze` leaves out pip itself; it is not a runtime dependency.

The result must:
- install with `--only-binary=:all:` on both architectures (CI builds both natively);
- pass `pip check`;
- contain no package that is only needed on Windows or macOS.

## Invariants

- Exact `==` pins only. No ranges and no unpinned names.
- Each package is listed once.
- Every pin is the latest release, unless research R1 gives the reason it is lower.
- Changing the Django release line or the DRF minor release needs a feature spec (constitution
  v2.1.0). Patch releases are routine updates.
