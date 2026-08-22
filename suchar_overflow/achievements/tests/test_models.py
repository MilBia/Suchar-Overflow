import pytest
from django.utils import timezone

from suchar_overflow.achievements.models import SchedulerRun


@pytest.mark.django_db
def test_scheduler_run_default_ordering_is_by_job_id():
    SchedulerRun.objects.create(job_id="b-job", ran_at=timezone.now())
    SchedulerRun.objects.create(job_id="a-job", ran_at=timezone.now())

    assert list(SchedulerRun.objects.values_list("job_id", flat=True)) == [
        "a-job",
        "b-job",
    ]
