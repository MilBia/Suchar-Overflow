from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('suchary', '0006_suchar_published_at'),
    ]

    operations = [
        migrations.AlterField(
            model_name='suchar',
            name='text',
            field=models.TextField(max_length=2000, verbose_name='Suchar text'),
        ),
    ]
