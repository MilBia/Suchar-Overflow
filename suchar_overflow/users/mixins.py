from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.mixins import UserPassesTestMixin
from django.shortcuts import redirect
from django.views.generic import View


class AsyncLoginRequiredMixin(LoginRequiredMixin):
    """LoginRequiredMixin that works with async view handlers."""

    async def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        return await super().dispatch(request, *args, **kwargs)


class AsyncUserPassesTestMixin(UserPassesTestMixin):
    """UserPassesTestMixin that works with async view handlers and async test_func."""

    async def dispatch(self, request, *args, **kwargs):
        if not await self.test_func():
            return self.handle_no_permission()
        return await View.dispatch(self, request, *args, **kwargs)

    def handle_no_permission(self):
        # Always redirect to login_url instead of raising PermissionDenied
        # This follows the behavior of LoginRequiredMixin
        if self.login_url is None:
            msg = (
                f"{self.__class__.__name__}.login_url is required. "
                "Define login_url or override handle_no_permission()."
            )
            raise ValueError(msg)
        return redirect(self.login_url)
