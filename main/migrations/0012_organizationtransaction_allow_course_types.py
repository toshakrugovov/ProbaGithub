# Allow transaction_type 'course_payment' and 'course_refund' in organizationtransaction.
# The DB may have a CHECK constraint that only allowed the original four types.

from django.db import migrations


def update_transaction_type_constraint(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            ALTER TABLE organizationtransaction
            DROP CONSTRAINT IF EXISTS organizationtransaction_transaction_type_check;
        """)
        cursor.execute("""
            ALTER TABLE organizationtransaction
            ADD CONSTRAINT organizationtransaction_transaction_type_check
            CHECK (transaction_type IN (
                'order_payment', 'order_refund', 'course_payment', 'course_refund',
                'tax_payment', 'withdrawal'
            ));
        """)


def reverse_constraint(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            ALTER TABLE organizationtransaction
            DROP CONSTRAINT IF EXISTS organizationtransaction_transaction_type_check;
        """)
        cursor.execute("""
            ALTER TABLE organizationtransaction
            ADD CONSTRAINT organizationtransaction_transaction_type_check
            CHECK (transaction_type IN (
                'order_payment', 'order_refund', 'tax_payment', 'withdrawal'
            ));
        """)


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0011_course_refund_request'),
    ]

    operations = [
        migrations.RunPython(update_transaction_type_constraint, reverse_constraint),
    ]
