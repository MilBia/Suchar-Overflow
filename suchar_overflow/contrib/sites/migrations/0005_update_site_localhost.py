from django.conf import settings
from django.db import migrations


def update_site_forward(apps, schema_editor):
    """Set site domain and name."""
    Site = apps.get_model("sites", "Site")
    Site.objects.update_or_create(
        id=settings.SITE_ID,
        defaults={
            "domain": "localhost:8000",
            "name": "Suchar Overflow",
        },
    )


def update_site_backward(apps, schema_editor):
    """Revert site domain and name to default."""
    Site = apps.get_model("sites", "Site")
    Site.objects.update_or_create(
        id=settings.SITE_ID,
        defaults={
            "domain": "example.com",
            "name": "Suchar Overflow",
        },
    )


class Migration(migrations.Migration):

    dependencies = [("sites", "0004_alter_options_ordering_domain")]

    operations = [migrations.RunPython(update_site_forward, update_site_backward)]
