from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.db.models import Sum
from django.db.models.functions import Coalesce
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
        queryset = Suchar.objects.annotate(
            score=Coalesce(Sum("votes__value"), 0),
        )

        sort = self.request.GET.get("sort")
        if sort == "top":
            queryset = queryset.order_by("-score", "-created_at")
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
    value = int(request.POST.get("value", 0))

    if value not in [1, -1]:
        return JsonResponse({"error": "Invalid vote value"}, status=400)

    vote, created = Vote.objects.get_or_create(
        user=request.user,
        suchar=suchar,
        defaults={"value": value},
    )

    if not created:
        if vote.value == value:
            vote.delete()  # Toggle off
        else:
            vote.value = value
            vote.save()

    return redirect("suchary:list")
