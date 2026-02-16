# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0015_three_nf'),
    ]

    operations = [
        migrations.AddField(
            model_name='lessonpage',
            name='page_number_end',
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
    ]
