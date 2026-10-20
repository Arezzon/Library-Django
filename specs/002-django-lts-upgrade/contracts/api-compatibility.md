# Contract: REST API compatibility (PR 1)

**Requirements**: FR-004, FR-005, SC-004 | **Research**: R5, R6

The upgrade must not change the public API. This contract defines "unchanged" and how it is
checked.

## Scope

- Every operation under `/api/v1/`, as published by `GET /api/schema/` (drf-spectacular).
- The interactive docs at `/api/docs/`. They load as before; CI already checks this.

## Must be identical before and after

Compare the schema generated from `main` (Django 4.1, DRF 3.15.1) with the schema generated from
the PR 1 branch (Django 5.2.18, DRF 3.18.3).

| Element | Rule |
|---|---|
| Paths and methods | Same set: nothing added, removed or renamed |
| `operationId` | Same for every operation |
| Parameters | Same name, location, `required` and type |
| Request bodies | Same media types and the same schema properties, types and `required` lists |
| Responses | Same status codes per operation, and the same response schema properties and types |
| Security | Same security requirements per operation |

## Allowed differences

Each one is listed in the PR description:
- description and summary text, key order and whitespace;
- additions that only document existing behavior, such as an `enum` on a read-only field after
  DRF 3.18 started passing `choices` to non-editable fields.

Any other difference is a breaking change. It is fixed in PR 1, never merged as it is.

## Behavior beyond the schema

The existing API tests (`book`, `author`, `order`, `events`, `authentication`) must pass without
weakening their assertions. They cover status codes, permission denials and response bodies. They
include the semantic search response (`BookSearchSerializer` with `similarity`) and the events API,
whose broker-outage path answers `503`.

## Procedure

See [quickstart.md](../quickstart.md) §2.3:
1. Save the schema from the running stack on `main` before any pin changes.
2. Save it again on the branch.
3. Compare structurally and review each difference against this contract.
