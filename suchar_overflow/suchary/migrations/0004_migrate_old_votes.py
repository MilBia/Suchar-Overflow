
from django.db import migrations

def migrate_votes(apps, schema_editor):
    Vote = apps.get_model('suchary', 'Vote')
    # Update Upvotes (1) -> Funny
    Vote.objects.filter(value=1).update(is_funny=True)
    # Update Downvotes (-1) -> Dry
    Vote.objects.filter(value=-1).update(is_dry=True)

def reverse_votes(apps, schema_editor):
    Vote = apps.get_model('suchary', 'Vote')
    # If is_funny is True, set value = 1
    Vote.objects.filter(is_funny=True).update(value=1)
    # If is_dry is True, set value = -1 (Overwrites is_funny if both are set, which shouldn't happen in old data)
    Vote.objects.filter(is_dry=True).update(value=-1)

class Migration(migrations.Migration):

    dependencies = [
        ('suchary', '0003_vote_is_dry_vote_is_funny_alter_vote_value'),
    ]

    operations = [
        migrations.RunPython(migrate_votes, reverse_votes),
    ]
