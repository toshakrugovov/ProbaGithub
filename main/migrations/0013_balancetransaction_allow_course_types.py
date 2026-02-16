# Allow transaction_type 'course_payment' and 'course_refund' in balancetransaction.

from django.db import migrations


def update_balance_transaction_type_constraint(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            ALTER TABLE balancetransaction
            DROP CONSTRAINT IF EXISTS balancetransaction_transaction_type_check;
        """)
        cursor.execute("""
            ALTER TABLE balancetransaction
            ADD CONSTRAINT balancetransaction_transaction_type_check
            CHECK (transaction_type IN (
                'deposit', 'withdrawal', 'order_payment', 'order_refund',
                'course_payment', 'course_refund'
            ));
        """)


def reverse_constraint(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            ALTER TABLE balancetransaction
            DROP CONSTRAINT IF EXISTS balancetransaction_transaction_type_check;
        """)
        cursor.execute("""
            ALTER TABLE balancetransaction
            ADD CONSTRAINT balancetransaction_transaction_type_check
            CHECK (transaction_type IN (
                'deposit', 'withdrawal', 'order_payment', 'order_refund'
            ));
        """)


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0012_organizationtransaction_allow_course_types'),
    ]

    operations = [
        migrations.RunPython(update_balance_transaction_type_constraint, reverse_constraint),
    ]
