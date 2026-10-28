from .context import audit_context


class AuditContextMiddleware:
    """Records a request's changes as the signed-in account's, with the channel its
    path belongs to: the admin site, the API or the web (research R21)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/admin/"):
            channel = "admin"
        elif request.path.startswith("/api/"):
            channel = "api"
        else:
            channel = "web"
        # request.user stays lazy: a request that changes nothing loads no account.
        with audit_context(actor=request.user, channel=channel):
            return self.get_response(request)
