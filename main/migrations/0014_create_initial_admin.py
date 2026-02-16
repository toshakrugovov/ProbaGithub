from django.db import migrations


def create_initial_admin(apps, schema_editor):
    """
    Создаёт первоначального администратора и роль 'ADMIN',
    если ещё нет ни одного суперпользователя.
    """
    User = apps.get_model('auth', 'User')
    Role = apps.get_model('main', 'Role')
    UserProfile = apps.get_model('main', 'UserProfile')

    # Если суперпользователь уже есть — ничего не делаем
    if User.objects.filter(is_superuser=True).exists():
        return

    import os

    username = os.environ.get('DJANGO_ADMIN_USERNAME', 'admin')
    email = os.environ.get('DJANGO_ADMIN_EMAIL', 'admin@example.com')

    # Пароль берём из переменных окружения, при отсутствии — безопасный дефолт
    password = (
        os.environ.get('DJANGO_ADMIN_PASSWORD')
        or os.environ.get('ADMIN_RESTORE_SECRET')
        or 'Admin123!'
    )

    # Создаём суперпользователя
    admin_user = User.objects.create_superuser(
        username=username,
        email=email,
        password=password,
    )

    # Создаём/находим роль администратора
    # Пытаемся найти по разным вариантам написания
    admin_role = (
        Role.objects.filter(role_name__iexact='admin').first()
        or Role.objects.filter(role_name__iexact='админ').first()
        or Role.objects.filter(role_name__iexact='ADMIN').first()
        or Role.objects.create(role_name='ADMIN')
    )

    # Создаём профиль администратора, если его ещё нет
    UserProfile.objects.get_or_create(
        user=admin_user,
        defaults={
            'role': admin_role,
            'full_name': 'Администратор',
        },
    )


def noop_reverse(apps, schema_editor):
    # Обратное действие специально ничего не делает,
    # чтобы не удалять случайно созданного администратора в бою.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0013_balancetransaction_allow_course_types'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(create_initial_admin, noop_reverse),
    ]

