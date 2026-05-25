import asyncio

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.mixins import UserPassesTestMixin
from django.shortcuts import redirect
from django.views.generic import View


class AsyncLoginRequiredMixin(LoginRequiredMixin):
    """LoginRequiredMixin that works with async view handlers."""

    async def dispatch(self, request, *args, **kwargs):
        if callable(getattr(request, "auser", None)):
            user = await request.auser()
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
            if cls_dispatch and asyncio.iscoroutinefunction(cls_dispatch):
                return await cls_dispatch(self, request, *args, **kwargs)
        return await View.dispatch(self, request, *args, **kwargs)


class AsyncUserPassesTestMixin(UserPassesTestMixin):
    """UserPassesTestMixin that works with async view handlers and async test_func."""

    async def dispatch(self, request, *args, **kwargs):
        if not await self.test_func():
            return redirect(self.get_login_url())
        return await View.dispatch(self, request, *args, **kwargs)
