# Generated manually based on existing database schema

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Role',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role_name', models.CharField(max_length=50, unique=True)),
            ],
            options={
                'db_table': 'role',
            },
        ),
        migrations.CreateModel(
            name='Category',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('category_name', models.CharField(max_length=100)),
                ('category_description', models.TextField(blank=True, null=True)),
                ('parent_category', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='subcategories', to='main.category', db_column='parent_category_id')),
            ],
            options={
                'db_table': 'category',
            },
        ),
        migrations.CreateModel(
            name='Brand',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('brand_name', models.CharField(max_length=100, unique=True)),
                ('brand_country', models.CharField(blank=True, max_length=100, null=True)),
                ('brand_description', models.TextField(blank=True, null=True)),
            ],
            options={
                'db_table': 'brand',
            },
        ),
        migrations.CreateModel(
            name='Supplier',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('supplier_name', models.CharField(max_length=100)),
                ('contact_person', models.CharField(blank=True, max_length=100, null=True)),
                ('contact_phone', models.CharField(blank=True, max_length=50, null=True)),
                ('contact_email', models.EmailField(blank=True, max_length=254, null=True)),
                ('supply_country', models.CharField(blank=True, max_length=100, null=True)),
                ('delivery_cost', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('supplier_type', models.CharField(blank=True, max_length=50, null=True)),
            ],
            options={
                'db_table': 'supplier',
            },
        ),
        migrations.CreateModel(
            name='Product',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('product_name', models.CharField(max_length=255)),
                ('price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('discount', models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ('stock_quantity', models.IntegerField(default=0)),
                ('product_description', models.TextField(blank=True, null=True)),
                ('added_at', models.DateTimeField(auto_now_add=True)),
                ('is_available', models.BooleanField(default=True)),
                ('brand', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='main.brand', db_column='brand_id')),
                ('category', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='main.category', db_column='category_id')),
                ('supplier', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='main.supplier', db_column='supplier_id')),
            ],
            options={
                'db_table': 'product',
            },
        ),
        migrations.CreateModel(
            name='Tag',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tag_name', models.CharField(max_length=100, unique=True)),
                ('tag_description', models.TextField(blank=True, null=True)),
            ],
            options={
                'db_table': 'tag',
            },
        ),
        migrations.CreateModel(
            name='Promotion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('promo_code', models.CharField(max_length=50, unique=True)),
                ('promo_description', models.TextField(blank=True, null=True)),
                ('discount', models.DecimalField(decimal_places=2, max_digits=5)),
                ('start_date', models.DateField(blank=True, null=True)),
                ('end_date', models.DateField(blank=True, null=True)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'db_table': 'promotion',
            },
        ),
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('full_name', models.CharField(blank=True, max_length=255, null=True)),
                ('phone_number', models.CharField(blank=True, max_length=50, null=True)),
                ('birth_date', models.DateField(blank=True, null=True)),
                ('user_status', models.CharField(default='active', max_length=50)),
                ('registered_at', models.DateTimeField(auto_now_add=True)),
                ('balance', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('secret_word', models.CharField(blank=True, help_text='Используется для восстановления пароля и подтверждения важных действий', max_length=255, null=True, verbose_name='Секретное слово')),
                ('role', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='main.role', db_column='role_id')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='profile', to=settings.AUTH_USER_MODEL, db_column='user_id')),
            ],
            options={
                'db_table': 'userprofile',
            },
        ),
        migrations.CreateModel(
            name='UserAddress',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('address_title', models.CharField(blank=True, max_length=100, null=True)),
                ('city_name', models.CharField(max_length=100)),
                ('street_name', models.CharField(max_length=100)),
                ('house_number', models.CharField(max_length=20)),
                ('apartment_number', models.CharField(blank=True, max_length=20, null=True)),
                ('postal_code', models.CharField(max_length=20)),
                ('is_primary', models.BooleanField(default=False)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='addresses', to=settings.AUTH_USER_MODEL, db_column='user_id')),
            ],
            options={
                'db_table': 'useraddress',
            },
        ),
        migrations.CreateModel(
            name='ProductSize',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('size_label', models.CharField(max_length=20)),
                ('size_type', models.CharField(blank=True, max_length=50, null=True)),
                ('size_stock', models.IntegerField(default=0)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sizes', to='main.product', db_column='product_id')),
            ],
            options={
                'db_table': 'productsize',
                'unique_together': {('product', 'size_label')},
            },
        ),
        migrations.CreateModel(
            name='ProductImage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image_data', models.BinaryField()),
                ('content_type', models.CharField(default='image/jpeg', max_length=100)),
                ('is_primary', models.BooleanField(default=False)),
                ('position', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='images', to='main.product', db_column='product_id')),
            ],
            options={
                'db_table': 'productimage',
                'ordering': ['-is_primary', 'position', 'id'],
            },
        ),
        migrations.CreateModel(
            name='ProductTag',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='main.product', db_column='product_id')),
                ('tag', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='main.tag', db_column='tag_id')),
            ],
            options={
                'db_table': 'producttag',
                'unique_together': {('product', 'tag')},
            },
        ),
        migrations.CreateModel(
            name='ProductReview',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rating_value', models.IntegerField()),
                ('review_text', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='main.product', db_column='product_id')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, db_column='user_id')),
            ],
            options={
                'db_table': 'productreview',
            },
        ),
        migrations.CreateModel(
            name='OrganizationAccount',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('balance', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='Баланс')),
                ('tax_reserve', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='Резерв на налоги (13%)')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'organizationaccount',
                'verbose_name': 'Счет организации',
                'verbose_name_plural': 'Счет организации',
            },
        ),
        migrations.CreateModel(
            name='Order',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('total_amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('delivery_cost', models.DecimalField(decimal_places=2, default=1000.0, max_digits=10, verbose_name='Стоимость доставки')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('order_status', models.CharField(choices=[('processing', 'В обработке'), ('paid', 'Оплачен'), ('shipped', 'Отправлен'), ('delivered', 'Доставлен'), ('cancelled', 'Отменен')], default='processing', max_length=50)),
                ('discount_amount', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('paid_from_balance', models.BooleanField(default=False)),
                ('can_be_cancelled', models.BooleanField(default=True)),
                ('vat_rate', models.DecimalField(decimal_places=2, default=20.0, max_digits=5)),
                ('vat_amount', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('tax_rate', models.DecimalField(decimal_places=2, default=13.0, max_digits=5, verbose_name='Налог на прибыль (%)')),
                ('tax_amount', models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Сумма налога (13%)')),
                ('address', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='main.useraddress', db_column='address_id')),
                ('promo_code', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='main.promotion', db_column='promo_code_id')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, db_column='user_id')),
            ],
            options={
                'db_table': 'order',
            },
        ),
        migrations.CreateModel(
            name='OrderItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.IntegerField()),
                ('unit_price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='main.order', db_column='order_id')),
                ('product', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='main.product', db_column='product_id')),
                ('size', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='main.productsize', db_column='size_id')),
            ],
            options={
                'db_table': 'orderitem',
            },
        ),
        migrations.CreateModel(
            name='OrganizationTransaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('transaction_type', models.CharField(choices=[('order_payment', 'Поступление от заказа'), ('order_refund', 'Возврат по отмене заказа'), ('tax_payment', 'Оплата налога'), ('withdrawal', 'Вывод на карту админа')], max_length=20)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('description', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('balance_before', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('balance_after', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('tax_reserve_before', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('tax_reserve_after', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='Создано пользователем', db_column='created_by_id')),
                ('order', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='org_transactions', to='main.order', db_column='order_id')),
                ('organization_account', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='transactions', to='main.organizationaccount', db_column='organization_account_id')),
            ],
            options={
                'db_table': 'organizationtransaction',
                'ordering': ['-created_at'],
                'verbose_name': 'Транзакция счета организации',
                'verbose_name_plural': 'Транзакции счета организации',
            },
        ),
        migrations.CreateModel(
            name='SavedPaymentMethod',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('card_number', models.TextField(max_length=500)),
                ('card_holder_name', models.CharField(max_length=100)),
                ('expiry_month', models.CharField(max_length=2)),
                ('expiry_year', models.CharField(max_length=4)),
                ('card_type', models.CharField(blank=True, max_length=20, null=True)),
                ('is_default', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('balance', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='saved_payment_methods', to=settings.AUTH_USER_MODEL, db_column='user_id')),
            ],
            options={
                'db_table': 'savedpaymentmethod',
                'ordering': ['-is_default', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='Payment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('payment_method', models.CharField(max_length=50)),
                ('payment_amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('payment_status', models.CharField(max_length=50)),
                ('paid_at', models.DateTimeField(blank=True, null=True)),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='main.order', db_column='order_id')),
                ('promo_code', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='main.promotion', db_column='promo_code_id')),
                ('saved_payment_method', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='main.savedpaymentmethod', db_column='saved_payment_method_id')),
            ],
            options={
                'db_table': 'payment',
            },
        ),
        migrations.CreateModel(
            name='Favorite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('added_at', models.DateTimeField(auto_now_add=True)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='main.product', db_column='product_id')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL, db_column='user_id')),
            ],
            options={
                'db_table': 'favorite',
                'unique_together': {('user', 'product')},
            },
        ),
        migrations.CreateModel(
            name='Delivery',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('carrier_name', models.CharField(blank=True, max_length=100, null=True)),
                ('tracking_number', models.CharField(blank=True, max_length=100, null=True)),
                ('delivery_status', models.CharField(blank=True, max_length=50, null=True)),
                ('shipped_at', models.DateTimeField(blank=True, null=True)),
                ('delivered_at', models.DateTimeField(blank=True, null=True)),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='main.order', db_column='order_id')),
            ],
            options={
                'db_table': 'delivery',
            },
        ),
        migrations.CreateModel(
            name='DatabaseBackup',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('backup_file', models.FileField(blank=True, null=True, upload_to='backups/')),
                ('backup_name', models.CharField(max_length=255, verbose_name='Название бэкапа')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')),
                ('file_size', models.BigIntegerField(default=0, verbose_name='Размер файла (байт)')),
                ('schedule', models.CharField(choices=[('now', 'Прямо сейчас'), ('weekly', 'Каждую неделю'), ('monthly', 'Раз в месяц'), ('yearly', 'Раз в год')], default='now', max_length=20, verbose_name='Расписание')),
                ('notes', models.TextField(blank=True, null=True, verbose_name='Примечания')),
                ('is_automatic', models.BooleanField(default=False, verbose_name='Автоматический бэкап')),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='Создан пользователем', db_column='created_by_id')),
            ],
            options={
                'db_table': 'databasebackup',
                'verbose_name': 'Бэкап базы данных',
                'verbose_name_plural': 'Бэкапы базы данных',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='Cart',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL, db_column='user_id')),
            ],
            options={
                'db_table': 'cart',
            },
        ),
        migrations.CreateModel(
            name='CartItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.IntegerField(default=1)),
                ('unit_price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('cart', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='main.cart', db_column='cart_id')),
                ('product', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='main.product', db_column='product_id')),
                ('size', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='main.productsize', db_column='size_id')),
            ],
            options={
                'db_table': 'cartitem',
            },
        ),
        migrations.CreateModel(
            name='CardTransaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('transaction_type', models.CharField(choices=[('deposit', 'Пополнение баланса'), ('withdrawal', 'Вывод на карту')], max_length=20)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('description', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('status', models.CharField(default='completed', max_length=20)),
                ('saved_payment_method', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='transactions', to='main.savedpaymentmethod', db_column='saved_payment_method_id')),
            ],
            options={
                'db_table': 'cardtransaction',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='BalanceTransaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('transaction_type', models.CharField(choices=[('deposit', 'Пополнение'), ('withdrawal', 'Вывод'), ('order_payment', 'Оплата заказа'), ('order_refund', 'Возврат заказа')], max_length=20)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('balance_before', models.DecimalField(decimal_places=2, max_digits=10)),
                ('balance_after', models.DecimalField(decimal_places=2, max_digits=10)),
                ('description', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('status', models.CharField(default='completed', max_length=20)),
                ('order', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='transactions', to='main.order', db_column='order_id')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='balance_transactions', to=settings.AUTH_USER_MODEL, db_column='user_id')),
            ],
            options={
                'db_table': 'balancetransaction',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='SupportTicket',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('subject', models.CharField(max_length=200)),
                ('message_text', models.TextField()),
                ('response_text', models.TextField(blank=True, null=True)),
                ('ticket_status', models.CharField(default='new', max_length=50)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('assigned_to', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assigned_tickets', to=settings.AUTH_USER_MODEL, verbose_name='Ответственный менеджер', db_column='assigned_to_id')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='support_tickets', to=settings.AUTH_USER_MODEL, db_column='user_id')),
            ],
            options={
                'db_table': 'supportticket',
            },
        ),
        migrations.CreateModel(
            name='ReceiptConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('company_name', models.CharField(default='ООО «MPTCOURSE»', max_length=255)),
                ('company_inn', models.CharField(default='7700000000', max_length=20)),
                ('company_address', models.CharField(default='г. Москва, ул. Примерная, д. 1', max_length=255)),
                ('cashier_name', models.CharField(default='Кассир', max_length=255)),
                ('shift_number', models.CharField(default='1', max_length=50)),
                ('kkt_rn', models.CharField(default='0000000000000000', max_length=32)),
                ('kkt_sn', models.CharField(default='1234567890', max_length=32)),
                ('fn_number', models.CharField(default='0000000000000000', max_length=32)),
                ('site_fns', models.CharField(default='www.nalog.ru', max_length=100)),
            ],
            options={
                'db_table': 'receiptconfig',
                'verbose_name': 'Настройки чека',
                'verbose_name_plural': 'Настройки чеков',
            },
        ),
        migrations.CreateModel(
            name='Receipt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('status', models.CharField(choices=[('executed', 'Исполнен'), ('annulled', 'Аннулирован')], default='executed', max_length=20)),
                ('total_amount', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('subtotal', models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Сумма товаров')),
                ('delivery_cost', models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Доставка')),
                ('discount_amount', models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Скидка')),
                ('vat_rate', models.DecimalField(decimal_places=2, default=20.0, max_digits=5)),
                ('vat_amount', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('payment_method', models.CharField(default='cash', max_length=20)),
                ('number', models.CharField(blank=True, max_length=50, null=True)),
                ('order', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='receipt', to='main.order', db_column='order_id')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='receipts', to=settings.AUTH_USER_MODEL, db_column='user_id')),
            ],
            options={
                'db_table': 'receipt',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='ReceiptItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('product_name', models.CharField(max_length=255)),
                ('article', models.CharField(blank=True, max_length=100, null=True)),
                ('quantity', models.IntegerField(default=1)),
                ('unit_price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('line_total', models.DecimalField(decimal_places=2, max_digits=10)),
                ('vat_amount', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('receipt', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='main.receipt', db_column='receipt_id')),
            ],
            options={
                'db_table': 'receiptitem',
            },
        ),
        migrations.CreateModel(
            name='ActivityLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action_type', models.CharField(max_length=50)),
                ('target_object', models.CharField(max_length=100)),
                ('action_description', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('ip_address', models.CharField(blank=True, max_length=50, null=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, db_column='user_id')),
            ],
            options={
                'db_table': 'activitylog',
            },
        ),
        migrations.AddConstraint(
            model_name='organizationaccount',
            constraint=models.CheckConstraint(check=models.Q(('balance__gte', 0)), name='org_account_balance_non_negative'),
        ),
        migrations.AddConstraint(
            model_name='organizationaccount',
            constraint=models.CheckConstraint(check=models.Q(('tax_reserve__gte', 0)), name='org_account_tax_reserve_non_negative'),
        ),
    ]

