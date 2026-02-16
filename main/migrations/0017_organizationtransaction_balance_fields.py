# Add balance_before, balance_after, tax_reserve_before, tax_reserve_after to OrganizationTransaction for history display

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0016_lessonpage_page_number_end'),
    ]

    operations = [
        migrations.AddField(
            model_name='organizationtransaction',
            name='balance_before',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, db_column='balance_before'),
        ),
        migrations.AddField(
            model_name='organizationtransaction',
            name='balance_after',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, db_column='balance_after'),
        ),
        migrations.AddField(
            model_name='organizationtransaction',
            name='tax_reserve_before',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, db_column='tax_reserve_before'),
        ),
        migrations.AddField(
            model_name='organizationtransaction',
            name='tax_reserve_after',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, db_column='tax_reserve_after'),
        ),
    ]
