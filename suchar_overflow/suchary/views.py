from asgiref.sync import sync_to_async
from django.contrib.auth.decorators import login_required
from django.core.paginator import InvalidPage
from django.core.paginator import Paginator
from django.db.models import Count
from django.db.models import OuterRef
from django.db.models import Q
from django.db.models import Subquery
from django.http import Http404
from django.http import JsonResponse
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View

from suchar_overflow.users.mixins import AsyncLoginRequiredMixin
from suchar_overflow.users.mixins import AsyncUserPassesTestMixin

from .forms import SucharForm
from .models import Suchar
from .models import Vote

_PER_PAGE = 10


class SucharListView(View):
    template_name = "suchary/suchar_list.html"

    async def get(self, request, *args, **kwargs):
        qs = (
            Suchar.objects.select_related("author")
            .prefetch_related("tags")
            .filter(published_at__lte=timezone.now())
            .annotate(
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
            qs = qs.filter(Q(text__icontains=q) | Q(tags__name__icontains=q)).distinct()

        tag = request.GET.get("tag")
        if tag:
            qs = qs.filter(tags__slug=tag)

        author = request.GET.get("author")
        if author:
            qs = qs.filter(author__username=author)

        page_number = request.GET.get("page", 1)

        def _paginate_and_render():
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
                },
            )

        return await sync_to_async(_paginate_and_render)()


class SucharCreateView(AsyncLoginRequiredMixin, View):
    template_name = "suchary/suchar_form.html"
    success_url = reverse_lazy("suchary:list")

    async def get(self, request, *args, **kwargs):
        return await sync_to_async(render)(
            request,
            self.template_name,
            {"form": SucharForm()},
        )

    async def post(self, request, *args, **kwargs):
        form = SucharForm(request.POST)  # safe: no instance, no DB in __init__
        if not await sync_to_async(form.is_valid)():
            return await sync_to_async(render)(
                request,
                self.template_name,
                {"form": form},
            )

        def _save():
            suchar = form.save(commit=False)
            suchar.author = request.user
            suchar.save()
            form._save_tags(suchar)  # noqa: SLF001

        await sync_to_async(_save)()
        return redirect(self.success_url)


class SucharUpdateView(AsyncLoginRequiredMixin, AsyncUserPassesTestMixin, View):
    template_name = "suchary/suchar_form.html"
    success_url = reverse_lazy("suchary:list")

    async def _get_suchar(self, pk):
        try:
            return await Suchar.objects.select_related("author").aget(pk=pk)
        except Suchar.DoesNotExist as exc:
            raise Http404 from exc

    async def test_func(self):
        suchar = await self._get_suchar(self.kwargs["pk"])
        return suchar.author == self.request.user

    async def get(self, request, pk, *args, **kwargs):
        suchar = await self._get_suchar(pk)
        if suchar.is_published:
            return await sync_to_async(render)(
                request,
                "suchary/edit_too_late.html",
                status=403,
            )
        # SucharForm.__init__ reads existing tags from DB when given an instance
        form = await sync_to_async(SucharForm)(instance=suchar)
        return await sync_to_async(render)(request, self.template_name, {"form": form})

    async def post(self, request, pk, *args, **kwargs):
        suchar = await self._get_suchar(pk)
        if suchar.is_published:
            return await sync_to_async(render)(
                request,
                "suchary/edit_too_late.html",
                status=403,
            )
        # SucharForm.__init__ reads existing tags from DB when given an instance
        form = await sync_to_async(SucharForm)(request.POST, instance=suchar)
        if not await sync_to_async(form.is_valid)():
            return await sync_to_async(render)(
                request,
                self.template_name,
                {"form": form},
            )
        await sync_to_async(form.save)()
        return redirect(self.success_url)


@login_required
async def vote_suchar(request, pk):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        suchar = await Suchar.objects.aget(pk=pk)
    except Suchar.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)

    vote_type = request.POST.get("vote_type")
    if vote_type not in ["funny", "dry"]:
        return JsonResponse({"error": "Invalid vote type"}, status=400)

    user = await request.auser()
    vote, _ = await Vote.objects.aget_or_create(user=user, suchar=suchar)

    if vote_type == "funny":
        vote.is_funny = not vote.is_funny
    elif vote_type == "dry":
        vote.is_dry = not vote.is_dry

    if not vote.is_funny and not vote.is_dry:
        await vote.adelete()
    else:
        await sync_to_async(vote.save)()

    return redirect("suchary:list")
