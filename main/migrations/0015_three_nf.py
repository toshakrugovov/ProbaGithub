# 3НФ: только изменения для существующих моделей (userprofile, order, receipt, receiptitem, balancetransaction, organizationtransaction, coursesurvey)

import django.db.models.deletion
from django.db import migrations, models


def backfill_receiptitem_course(apps, schema_editor):
    """Заполняем course_id и line_description по данным чека и заказа."""
    ReceiptItem = apps.get_model('main', 'ReceiptItem')
    for item in ReceiptItem.objects.select_related('receipt').all():
        try:
            order = item.receipt.order
            # Ищем позицию заказа с теми же quantity, unit_price
            oi = order.items.filter(quantity=item.quantity, unit_price=item.unit_price).first()
            if oi and getattr(oi, 'course_id', None):
                item.course_id = oi.course_id
            else:
                item.line_description = getattr(item, 'product_name', None) or 'Товар'
            item.save()
        except Exception:
            if not getattr(item, 'line_description', None):
                item.line_description = getattr(item, 'product_name', None) or '—'
            item.save()


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0014_create_initial_admin'),
    ]

    operations = [
        migrations.RemoveField(model_name='userprofile', name='full_name'),
        migrations.RemoveField(model_name='order', name='vat_amount'),
        migrations.RemoveField(model_name='order', name='tax_amount'),
        migrations.RemoveField(model_name='receipt', name='vat_amount'),
        migrations.AddField(
            model_name='receiptitem',
            name='course',
            field=models.ForeignKey(blank=True, db_column='course_id', null=True, on_delete=django.db.models.deletion.SET_NULL, to='main.course'),
        ),
        migrations.AddField(
            model_name='receiptitem',
            name='line_description',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.RunPython(backfill_receiptitem_course, migrations.RunPython.noop),
        migrations.RemoveField(model_name='receiptitem', name='product_name'),
        migrations.RemoveField(model_name='receiptitem', name='line_total'),
        migrations.RemoveField(model_name='receiptitem', name='vat_amount'),
        migrations.RemoveField(model_name='balancetransaction', name='balance_before'),
        migrations.RemoveField(model_name='balancetransaction', name='balance_after'),
        migrations.RemoveField(model_name='organizationtransaction', name='balance_before'),
        migrations.RemoveField(model_name='organizationtransaction', name='balance_after'),
        migrations.RemoveField(model_name='organizationtransaction', name='tax_reserve_before'),
        migrations.RemoveField(model_name='organizationtransaction', name='tax_reserve_after'),
        migrations.RemoveField(model_name='coursesurvey', name='course'),
        migrations.RemoveField(model_name='coursesurvey', name='user'),
    ]
