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
        return await View.dispatch(self, request, *args, **kwargs)


class AsyncUserPassesTestMixin(UserPassesTestMixin):
    """UserPassesTestMixin that works with async view handlers and async test_func."""

    async def dispatch(self, request, *args, **kwargs):
        if not await self.test_func():
            return redirect(self.get_login_url())
        return await View.dispatch(self, request, *args, **kwargs)
