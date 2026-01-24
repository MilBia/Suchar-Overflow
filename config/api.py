from ninja import NinjaAPI

api = NinjaAPI(
    title="Suchar Overflow API",
    version="1.0.0",
    description="API for accessing and interacting with Suchar Overflow content.",
    urls_namespace="api",
)

api.add_router("/suchary/", "suchar_overflow.suchary.api.router")
