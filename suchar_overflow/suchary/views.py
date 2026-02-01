from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.db.models import OuterRef
from django.db.models import Q
from django.db.models import Subquery
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView
from django.views.generic import ListView

from .forms import SucharForm
from .models import Suchar
from .models import Vote


class SucharListView(ListView):
    model = Suchar
    template_name = "suchary/suchar_list.html"
    context_object_name = "suchary"
    paginate_by = 10

    def get_queryset(self):
        queryset = (
            Suchar.objects.select_related("author")
            .prefetch_related("tags")
            .annotate(
                funny_count=Count("votes", filter=Q(votes__is_funny=True)),
                dry_count=Count("votes", filter=Q(votes__is_dry=True)),
            )
        )

        if self.request.user.is_authenticated:
            queryset = queryset.annotate(
                user_is_funny=Subquery(
                    Vote.objects.filter(
                        suchar=OuterRef("pk"),
                        user=self.request.user,
                    ).values("is_funny")[:1],
                ),
                user_is_dry=Subquery(
                    Vote.objects.filter(
                        suchar=OuterRef("pk"),
                        user=self.request.user,
                    ).values("is_dry")[:1],
                ),
            )

        sort = self.request.GET.get("sort")
        if sort == "top":
            # For "Top" sorting, we can prioritize funny jokes
            queryset = queryset.order_by("-funny_count", "-dry_count", "-created_at")
        else:
            queryset = queryset.order_by("-created_at")

        q = self.request.GET.get("q")
        if q:
            queryset = queryset.filter(
                Q(text__icontains=q) | Q(tags__name__icontains=q),
            ).distinct()

        tag = self.request.GET.get("tag")
        if tag:
            queryset = queryset.filter(tags__slug=tag)

        author = self.request.GET.get("author")
        if author:
            queryset = queryset.filter(author__username=author)

        return queryset


class SucharCreateView(LoginRequiredMixin, CreateView):
    model = Suchar
    form_class = SucharForm
    template_name = "suchary/suchar_form.html"
    success_url = reverse_lazy("suchary:list")

    def form_valid(self, form):
        form.instance.author = self.request.user
        return super().form_valid(form)


@login_required
@require_POST
def vote_suchar(request, pk):
    suchar = get_object_or_404(Suchar, pk=pk)
    vote_type = request.POST.get("vote_type")

    if vote_type not in ["funny", "dry"]:
        return JsonResponse({"error": "Invalid vote type"}, status=400)

    vote, _ = Vote.objects.get_or_create(
        user=request.user,
        suchar=suchar,
    )

    if vote_type == "funny":
        vote.is_funny = not vote.is_funny
    elif vote_type == "dry":
        vote.is_dry = not vote.is_dry

    if not vote.is_funny and not vote.is_dry:
        vote.delete()
    else:
        vote.save()

    return redirect("suchary:list")
