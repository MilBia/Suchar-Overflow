import inspect

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.mixins import UserPassesTestMixin

# Django's View.as_view() copies cls.dispatch.__annotations__ at class-creation
# time, forcing the lazy annotation to resolve — it must stay a real runtime
# import, not TYPE_CHECKING-only. Same for HttpRequest below (dispatch's whole
# annotation set is copied, not just the return type).
from django.http import HttpRequest  # noqa: TC002
from django.http import HttpResponseBase  # noqa: TC002
from django.shortcuts import redirect
from django.utils.translation import gettext
from django.views.generic import View


class AsyncLoginRequiredMixin(LoginRequiredMixin, View):
    """LoginRequiredMixin that works with async view handlers."""

    # django-stubs types `dispatch` as sync-returning `HttpResponseBase`; it has
    # no async variant, even though Django supports async dispatch at runtime.
    async def dispatch(  # type: ignore[override]
        self,
        request: HttpRequest,
        *args: object,
        **kwargs: object,
    ) -> HttpResponseBase:
        if callable(getattr(request, "auser", None)):
            user = await request.auser()
            request.user = user
        else:
            user = request.user
        if not user.is_authenticated:
            return self.handle_no_permission()
        # Skip sync LoginRequiredMixin.dispatch. If another async mixin (e.g.
        # AsyncUserPassesTestMixin) follows in the MRO, call it; otherwise go
        # straight to View.dispatch which will call the method handler.
        mro = type(self).__mro__
        idx = mro.index(AsyncLoginRequiredMixin)
        for cls in mro[idx + 1 :]:
            if cls is View:
                break
            cls_dispatch = cls.__dict__.get("dispatch")
            if cls_dispatch and inspect.iscoroutinefunction(cls_dispatch):
                return await cls_dispatch(self, request, *args, **kwargs)
        # View.dispatch is typed as sync-returning HttpResponseBase, but at
        # runtime it returns a coroutine for async view handlers (Django
        # inspects view_is_async) — same stub gap as the dispatch override above.
        return await View.dispatch(self, request, *args, **kwargs)  # type: ignore[misc]


class AsyncUserPassesTestMixin(UserPassesTestMixin, View):
    """UserPassesTestMixin that works with async view handlers and async test_func."""

    # See AsyncLoginRequiredMixin.dispatch above: django-stubs has no async
    # variant of `dispatch`/`test_func`.
    async def dispatch(  # type: ignore[override]
        self,
        request: HttpRequest,
        *args: object,
        **kwargs: object,
    ) -> HttpResponseBase:
        if callable(getattr(request, "auser", None)):
            request.user = await request.auser()
        if not await self.test_func():
            messages.error(request, gettext("You don't have permission to do that."))
            return redirect(self.get_login_url())
        # See the comment on AsyncLoginRequiredMixin.dispatch's final line above.
        return await View.dispatch(self, request, *args, **kwargs)  # type: ignore[misc]

    async def test_func(self) -> bool:  # type: ignore[override]
        msg = f"{type(self).__name__} is missing implementation of test_func method."
        raise NotImplementedError(msg)
