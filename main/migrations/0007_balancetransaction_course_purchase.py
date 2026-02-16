# Add course_purchase_id to balancetransaction

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0006_promousage_course_purchase'),
    ]

    operations = [
        migrations.AddField(
            model_name='balancetransaction',
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
