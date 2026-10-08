"""The Meridian intranet: the knowledge team's read-only site over published snapshots."""

import re
from pathlib import Path
from urllib.parse import parse_qs, urlencode

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader

from zknowledge.index import Caller, IndexStore, NotFound
from zknowledge.site import identity, pages
from zknowledge.snapshot import SnapshotUnavailable, snapshot_directory

HERE = Path(__file__).parent
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'self'; img-src 'self'; form-action 'self'; "
        "frame-ancestors 'none'; base-uri 'none'"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}
KEYS = {
    "wiki": re.compile(r"[0-9]{1,8}"),
    "qms": re.compile(r"[A-Z0-9]+(?:-[A-Z0-9]+)+"),
    "ticketing": re.compile(r"[A-Z]+-[0-9]{1,6}"),
    "reference": re.compile(r"[a-z0-9_]{1,64}"),
    "wikipedia": re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*"),
}
DOCUMENT_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
TEMPLATES = {
    "wiki": "wiki.html",
    "qms": "qms.html",
    "ticketing": "ticket.html",
    "reference": "reference.html",
    "wikipedia": "library.html",
}
KINDS = {
    "sop": "SOP",
    "validation": "Validation summary",
    "form": "Form",
    "change_request": "Change request",
    "service_request": "Service request",
    "incident": "Incident",
    "problem": "Problem",
    "wiki_page": "Page",
    "reference_table": "Reference table",
    "glossary": "Glossary",
    "encyclopedia": "Article",
}


def create_site(
    store: IndexStore | None = None,
    *,
    verifier: identity.GrantVerifier | None = None,
    sessions: identity.Sessions | None = None,
) -> FastAPI:
    store = store or IndexStore(snapshot_directory())
    verifier = verifier or identity.GrantVerifier.configured()
    sessions = sessions or identity.Sessions()
    templates = Environment(
        loader=FileSystemLoader(HERE / "templates"),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    templates.filters["kind"] = lambda value: KINDS.get(value, value.replace("_", " ").capitalize())
    app = FastAPI(title="Meridian intranet", docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        return response

    def signed_in(request: Request) -> identity.Visitor | None:
        return sessions.read(request.cookies.get(identity.SESSION_COOKIE))

    def visitor(request: Request) -> Caller:
        return identity.caller(signed_in(request))

    def render(request: Request, template: str, code: int = 200, **context) -> HTMLResponse:
        context.setdefault("area", None)
        context.setdefault("notices", [])
        person = signed_in(request)
        if person and request.query_params.get("via") == "workbench":
            context["notices"] = [
                pages.Notice(
                    "identity",
                    f"Opened from your workbench session as {person.name} "
                    f"({person.title.lower()}, {person.site_name}).",
                ),
                *context["notices"],
            ]
        html = templates.get_template(template).render(
            areas=pages.AREAS,
            path=request.url.path,
            query=request.query_params.get("q", "") if request.url.path == "/search" else "",
            visitor=person,
            **context,
        )
        return HTMLResponse(html, status_code=code)

    def missing(request: Request) -> HTMLResponse:
        return render(request, "not_found.html", 404, title="Page not found")

    def unavailable(request: Request) -> HTMLResponse:
        return render(request, "unavailable.html", 503, title="Knowledge base unavailable")

    def with_index(request: Request, build):
        try:
            index = store.open()
        except SnapshotUnavailable:
            return None, unavailable(request)
        try:
            return build(index), None
        except NotFound:
            return None, missing(request)
        finally:
            index.close()

    def document(request: Request, area: str, key: str, version: str | None = None):
        if not KEYS[area].fullmatch(key) or (version is not None and not version.isdigit()):
            return missing(request)
        params = request.query_params
        try:
            page = pages.document_page(
                store,
                visitor(request),
                area,
                key,
                version=version,
                snapshot=params.get("snapshot"),
                lines=params.get("lines"),
                quote=params.get("q"),
            )
        except NotFound:
            return missing(request)
        except SnapshotUnavailable:
            return unavailable(request)
        return render(request, TEMPLATES[area], **page)

    @app.get("/health")
    async def health():
        index = store.open()
        try:
            return JSONResponse({"status": "ok", "snapshot": index.snapshot})
        finally:
            index.close()

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        model, failure = with_index(request, lambda index: pages.home(index, visitor(request)))
        return failure or render(request, "home.html", title="Home", **model)

    @app.get("/d/{document}")
    def resolve(request: Request, document: str):
        """Citation links land here and are sent to the document's own system."""
        params = request.query_params
        if not DOCUMENT_ID.fullmatch(document):
            return missing(request)
        try:
            path = pages.resolve(store, visitor(request), document, params.get("snapshot"))
        except NotFound:
            return missing(request)
        except SnapshotUnavailable:
            return unavailable(request)
        query = {
            name: params[name][: pages.QUOTE_LIMIT]
            for name in ("snapshot", "lines", "q", "via")
            if params.get(name)
        }
        fragment = ""
        if match := pages.LINE_RANGE.fullmatch(params.get("lines", "")):
            fragment = f"#L{match[1]}"
        target = path + (f"?{urlencode(query)}" if query else "") + fragment
        return RedirectResponse(target, status_code=302)

    @app.get("/wiki", response_class=HTMLResponse)
    def wiki_index(request: Request):
        model, failure = with_index(
            request, lambda index: {"tree": pages.wiki_tree(index, visitor(request))}
        )
        return failure or render(
            request, "wiki_index.html", area="wiki", title="MCGC space", **model
        )

    @app.get("/wiki/display/MCGC/{page}", response_class=HTMLResponse)
    def wiki_page(request: Request, page: str):
        return document(request, "wiki", page)

    @app.get("/qms", response_class=HTMLResponse)
    def qms_index(request: Request):
        status = request.query_params.get("status") or None
        model, failure = with_index(
            request,
            lambda index: {"register": pages.qms_register(index, visitor(request), status)},
        )
        return failure or render(
            request,
            "qms_index.html",
            area="qms",
            title="Document register",
            status=status,
            **model,
        )

    @app.get("/qms/documents/{number}", response_class=HTMLResponse)
    def qms_series(request: Request, number: str):
        if not KEYS["qms"].fullmatch(number):
            return missing(request)

        def build(index):
            register = pages.qms_register(index, visitor(request), number=number)
            if not register:
                raise NotFound("Document not found")
            return {"series": register[0]}

        model, failure = with_index(request, build)
        return failure or render(request, "qms_series.html", area="qms", title=number, **model)

    @app.get("/qms/documents/{number}/v{version}", response_class=HTMLResponse)
    def qms_document(request: Request, number: str, version: str):
        return document(request, "qms", number, version)

    @app.get("/servicedesk", response_class=HTMLResponse)
    def service_desk(request: Request):
        kind = request.query_params.get("type") or None
        status = request.query_params.get("status") or None
        model, failure = with_index(
            request, lambda index: pages.issues(index, visitor(request), kind, status)
        )
        return failure or render(
            request,
            "servicedesk_index.html",
            area="ticketing",
            title="Issues",
            kind=kind,
            status=status,
            **model,
        )

    @app.get("/servicedesk/browse/{key}", response_class=HTMLResponse)
    def ticket(request: Request, key: str):
        return document(request, "ticketing", key)

    @app.get("/reference", response_class=HTMLResponse)
    def reference_index(request: Request):
        model, failure = with_index(
            request,
            lambda index: {
                "documents": [
                    pages.summary(row)
                    for row in pages.visible_rows(index, visitor(request), "reference")
                ]
            },
        )
        return failure or render(
            request, "reference_index.html", area="reference", title="Reference", **model
        )

    @app.get("/reference/glossary", response_class=HTMLResponse)
    def glossary(request: Request):
        return document(request, "reference", "glossary")

    @app.get("/reference/tables/{name}", response_class=HTMLResponse)
    def reference_table(request: Request, name: str):
        return document(request, "reference", name)

    @app.get("/library", response_class=HTMLResponse)
    def library_index(request: Request):
        model, failure = with_index(
            request,
            lambda index: {
                "articles": [
                    pages.summary(row)
                    for row in sorted(
                        pages.visible_rows(index, visitor(request), "wikipedia"),
                        key=lambda row: row["title"].lower(),
                    )
                ]
            },
        )
        return failure or render(
            request, "library_index.html", area="wikipedia", title="Library", **model
        )

    @app.get("/library/{slug}", response_class=HTMLResponse)
    def article(request: Request, slug: str):
        return document(request, "wikipedia", slug)

    @app.get("/search", response_class=HTMLResponse)
    def search(request: Request):
        query = request.query_params.get("q", "").strip()
        everything = request.query_params.get("all") == "1"
        model, failure = with_index(
            request,
            lambda index: (
                pages.search(index, visitor(request), query, everything)
                if query
                else {"groups": [], "counts": {}, "expanded": []}
            ),
        )
        return failure or render(
            request, "search.html", title="Search", everything=everything, **model
        )

    def signed_in_response(target: str, cookie: str) -> RedirectResponse:
        response = RedirectResponse(target, status_code=303)
        response.set_cookie(
            identity.SESSION_COOKIE,
            cookie,
            max_age=identity.SESSION_SECONDS,
            httponly=True,
            samesite="lax",
            path="/",
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    def local(target: str | None) -> str:
        """Only same-site paths, so sign-in cannot redirect elsewhere."""
        if target and target.startswith("/") and not target.startswith(("//", "/\\")):
            return target
        return "/"

    @app.get("/signin", response_class=HTMLResponse)
    def signin_page(request: Request):
        return render(
            request,
            "signin.html",
            title="Sign in",
            staff=identity.STAFF,
            sites=identity.SITES,
            next=local(request.query_params.get("next")),
        )

    @app.post("/signin")
    async def signin(request: Request):
        form = parse_qs((await request.body()).decode(errors="replace")[:2000])
        persona = (form.get("persona") or [""])[0]
        site = (form.get("site") or [""])[0]
        if persona not in identity.STAFF or site not in identity.SITES:
            return render(
                request,
                "signin.html",
                400,
                title="Sign in",
                staff=identity.STAFF,
                sites=identity.SITES,
                next="/",
                error="Choose a staff member and a site.",
            )
        return signed_in_response(
            local((form.get("next") or ["/"])[0]), sessions.issue(persona, site)
        )

    @app.post("/signout")
    def signout():
        response = RedirectResponse("/", status_code=303)
        response.delete_cookie(identity.SESSION_COOKIE, path="/")
        return response

    @app.get("/signin/grant")
    def redeem(request: Request):
        """A citation opened from the workbench: sign in as the session's persona, then show it."""
        try:
            grant = verifier.redeem(request.query_params.get("token"))
        except identity.GrantRejected:
            response = render(request, "grant_rejected.html", 403, title="Link expired")
            response.headers["Cache-Control"] = "no-store"
            return response
        query = {
            name: value
            for name, value in (
                ("snapshot", grant.snapshot),
                ("lines", grant.lines),
                ("q", grant.q),
            )
            if value
        }
        target = f"/d/{grant.document}?{urlencode({**query, 'via': 'workbench'})}"
        return signed_in_response(
            target, sessions.issue(grant.persona, grant.site, via="workbench")
        )

    return app


app = create_site()
