# Add course_purchase_id to promo_usage (for promo use on course purchases)

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0005_course_tables_only'),
    ]

    operations = [
        migrations.AddField(
            model_name='promousage',
            name='course_purchase',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to='main.coursepurchase',
                db_column='course_purchase_id',
            ),
        ),
    ]
