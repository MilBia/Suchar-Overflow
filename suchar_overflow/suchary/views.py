from typing import TYPE_CHECKING

from asgiref.sync import sync_to_async
from django.contrib import messages
from django.core.paginator import InvalidPage
from django.core.paginator import Paginator
from django.db.models import Count
from django.db.models import F
from django.db.models import OuterRef
from django.db.models import Q
from django.db.models import Subquery
from django.http import Http404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext
from django.views import View

from suchar_overflow.users.mixins import AsyncLoginRequiredMixin
from suchar_overflow.users.mixins import AsyncUserPassesTestMixin
from suchar_overflow.users.models import User

from .forms import SucharForm
from .models import Suchar
from .models import Tag
from .models import Vote
from .signals import suchar_edited

if TYPE_CHECKING:
    from django.http import HttpRequest
    from django.http import HttpResponse

_PER_PAGE = 10
# Elided pagination window (see issue #210). With these values the navigation
# never renders more than 9 page numbers, and no elision happens at all for
# <= (_ON_EACH_SIDE + _ON_ENDS) * 2 == 6 pages, so short lists keep the plain
# "1 2 3 4 5" navigation they had before.
_ON_EACH_SIDE = 2
_ON_ENDS = 1


class SucharListView(View):
    template_name = "suchary/suchar_list.html"

    async def get(self, request: HttpRequest) -> HttpResponse:
        qs = (
            Suchar.objects.select_related("author")
            .prefetch_related("tags")
            .filter(published_at__lte=timezone.now())
            .annotate(
                # The `?q=` branch below matches tags via a `pk__in` subquery
                # rather than a JOIN, so it never adds a second multi-valued
                # JOIN in parallel with this one (suchar -> votes) -- these
                # aggregates see at most one row per vote and don't need
                # `distinct=True` (#241; see #196 for the fan-out this used
                # to guard against).
                funny_count=Count("votes", filter=Q(votes__is_funny=True)),
                dry_count=Count("votes", filter=Q(votes__is_dry=True)),
            )
        )

        user = await request.auser()
        if user.is_authenticated:
            qs = qs.annotate(
                user_is_funny=Subquery(
                    Vote.objects.filter(
                        suchar=OuterRef("pk"),
                        user=user,
                    ).values("is_funny")[:1],
                ),
                user_is_dry=Subquery(
                    Vote.objects.filter(
                        suchar=OuterRef("pk"),
                        user=user,
                    ).values("is_dry")[:1],
                ),
            )

        sort = request.GET.get("sort")
        if sort == "top":
            qs = qs.order_by("-funny_count", "-dry_count", "-created_at")
        else:
            qs = qs.order_by("-created_at")

        q = request.GET.get("q")
        if q:
            qs = qs.filter(
                Q(text__icontains=q)
                | Q(pk__in=Tag.objects.filter(name__icontains=q).values("suchary__pk")),
            )

        tag = request.GET.get("tag")
        if tag:
            qs = qs.filter(tags__slug=tag)

        author = request.GET.get("author")
        if author:
            qs = qs.filter(author__username=author)

        page_number = request.GET.get("page", 1)

        def _paginate_and_render() -> HttpResponse:
            paginator = Paginator(qs, per_page=_PER_PAGE)
            try:
                page = paginator.page(page_number)
            except InvalidPage as exc:
                raise Http404 from exc
            return render(
                request,
                self.template_name,
                {
                    "page_obj": page,
                    "suchary": page.object_list,
                    "paginator": paginator,
                    "is_paginated": page.has_other_pages(),
                    # Built here rather than in the template: the template
                    # engine cannot pass the current page number (nor the
                    # window arguments) to get_elided_page_range().
                    "page_range": paginator.get_elided_page_range(
                        page.number,
                        on_each_side=_ON_EACH_SIDE,
                        on_ends=_ON_ENDS,
                    ),
                },
            )

        return await sync_to_async(_paginate_and_render)()


class SucharCreateView(AsyncLoginRequiredMixin):
    template_name = "suchary/suchar_form.html"
    success_url = reverse_lazy("suchary:list")

    async def get(self, request: HttpRequest) -> HttpResponse:
        return await sync_to_async(render)(
            request,
            self.template_name,
            {"form": SucharForm()},
        )

    async def post(self, request: HttpRequest) -> HttpResponse:
        form = SucharForm(request.POST)  # safe: no instance, no DB in __init__
        if not await sync_to_async(form.is_valid)():
            return await sync_to_async(render)(
                request,
                self.template_name,
                {"form": form},
            )

        def _save() -> None:
            suchar = form.save(commit=False)
            # AsyncLoginRequiredMixin already rejects anonymous requests.
            assert isinstance(request.user, User)
            suchar.author = request.user
            suchar.save()
            form.save_m2m()

        await sync_to_async(_save)()
        messages.success(request, gettext("Your suchar has been posted."))
        return redirect(self.success_url)


class SucharUpdateView(AsyncLoginRequiredMixin, AsyncUserPassesTestMixin):  # type: ignore[misc]
    template_name = "suchary/suchar_form.html"
    success_url = reverse_lazy("suchary:list")

    #: Per-request cache for the edited suchar; Django builds a fresh view
    #: instance for every request, so this can never leak between requests.
    _suchar: Suchar | None = None

    async def _get_suchar(self, pk: int) -> Suchar:
        """Fetch the edited suchar, at most once per request (issue #201).

        `AsyncUserPassesTestMixin.dispatch` calls `test_func()` before handing
        off to `get()`/`post()`, and both need the same row. Memoizing here —
        rather than only in `test_func` — keeps the handlers correct even if
        they are ever reached without `test_func` having run first.
        """
        suchar = self._suchar
        if suchar is not None and suchar.pk == pk:
            return suchar
        try:
            suchar = await Suchar.objects.select_related("author").aget(pk=pk)
        except Suchar.DoesNotExist as exc:
            raise Http404 from exc
        self._suchar = suchar
        return suchar

    async def test_func(self) -> bool:  # type: ignore[override]
        suchar = await self._get_suchar(self.kwargs["pk"])
        return suchar.author == self.request.user

    async def _reject_if_published(
        self,
        request: HttpRequest,
        suchar: Suchar,
    ) -> HttpResponse | None:
        """Return the "too late to edit" response if suchar is published, else None."""
        if suchar.is_published:
            return await sync_to_async(render)(
                request,
                "suchary/edit_too_late.html",
                status=403,
            )
        return None

    async def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        suchar = await self._get_suchar(pk)
        too_late = await self._reject_if_published(request, suchar)
        if too_late is not None:
            return too_late
        # SucharForm.__init__ reads existing tags from DB when given an instance
        form = await sync_to_async(SucharForm)(instance=suchar)
        return await sync_to_async(render)(request, self.template_name, {"form": form})

    async def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        suchar = await self._get_suchar(pk)
        too_late = await self._reject_if_published(request, suchar)
        if too_late is not None:
            return too_late
        # SucharForm.__init__ reads existing tags from DB when given an instance
        form = await sync_to_async(SucharForm)(request.POST, instance=suchar)
        if not await sync_to_async(form.is_valid)():
            return await sync_to_async(render)(
                request,
                self.template_name,
                {"form": form},
            )

        def _save_and_signal() -> None:
            # form.save() now writes only text/published_at (see
            # SucharForm.save), so this atomic bump can't be clobbered by a
            # stale in-memory edit_count and concurrent edits each count once.
            form.save()
            Suchar.objects.filter(pk=suchar.pk).update(
                edit_count=F("edit_count") + 1,
            )
            # Best-effort local value for signal receivers; the engine ignores
            # it and re-reads edit_count from the DB anyway.
            suchar.edit_count += 1
            suchar_edited.send(sender=Suchar, author=suchar.author, suchar=suchar)

        await sync_to_async(_save_and_signal)()
        messages.success(request, gettext("Your suchar has been updated."))
        return redirect(self.success_url)
