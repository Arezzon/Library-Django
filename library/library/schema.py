"""The API schema states who may call each operation (FR-005).

Each permission class in ``authentication.permissions`` carries an audience label. For
every operation this schema class adds that label as ``x-audience``, ends the
description with "Audience: ...", and documents the refusals: 401 and 403 unless anyone
may call the operation, and 404 where readers see only their own records.
"""

from drf_spectacular import openapi
from drf_spectacular.authentication import SessionScheme
from drf_spectacular.plumbing import ResolvedComponent
from rest_framework.permissions import AllowAny


class SessionSignIn(SessionScheme):
    """Documents the project's session sign-in the way drf-spectacular documents
    DRF's own: a session cookie (``cookieAuth``)."""

    target_class = "authentication.permissions.SessionAuthentication"


ANONYMOUS = ("anonymous", "Anyone, signed in or not.")
# From the widest audience to the narrowest; several classes give the narrowest.
AUDIENCES = [
    "anonymous",
    "signed-in",
    "signed-in-read",
    "self-or-librarian",
    "librarian",
]

REFUSALS = {
    "401": "Not signed in: sign in and try again.",
    "403": "Signed in, but this account may not do this.",
    "404": "No such record, or it belongs to another account.",
}

REFUSAL_BODY = ResolvedComponent(
    name="Refusal",
    type=ResolvedComponent.SCHEMA,
    object="Refusal",
    schema={
        "type": "object",
        "properties": {"detail": {"type": "string"}},
        "required": ["detail"],
    },
)


class AutoSchema(openapi.AutoSchema):
    def get_operation(self, path, path_regex, path_prefix, method, registry):
        operation = super().get_operation(
            path, path_regex, path_prefix, method, registry
        )
        if operation is None:
            return None
        audience, description = self.get_audience()
        operation["x-audience"] = audience
        text = operation.get("description", "").rstrip()
        sentence = f"Audience: {description}"
        operation["description"] = f"{text}\n\n{sentence}" if text else sentence
        if audience != "anonymous":
            codes = ["401", "403"]
            if "{" in path and self.limits_readers_to_own_records(audience):
                codes.append("404")
            registry.register_on_missing(REFUSAL_BODY)
            for code in codes:
                operation["responses"].setdefault(
                    code,
                    {
                        "description": REFUSALS[code],
                        "content": {"application/json": {"schema": REFUSAL_BODY.ref}},
                    },
                )
        return operation

    def get_audience(self):
        labels = []
        for permission in self.view.get_permissions():
            if isinstance(permission, AllowAny):
                labels.append(ANONYMOUS)
            else:
                labels.append(
                    (
                        getattr(permission, "audience", "nobody"),
                        getattr(
                            permission, "audience_description", "Nobody: undeclared."
                        ),
                    )
                )
        # An unknown label sorts last, so it is never hidden behind a wider one.
        return max(
            labels or [("nobody", "Nobody: undeclared.")],
            key=lambda label: (
                AUDIENCES.index(label[0]) if label[0] in AUDIENCES else len(AUDIENCES)
            ),
        )

    def limits_readers_to_own_records(self, audience):
        return audience == "self-or-librarian" or getattr(
            self.view, "own_records_only", False
        )
