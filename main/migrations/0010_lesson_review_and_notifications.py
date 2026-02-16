# Generated manually: lesson review + admin comment + UserNotification

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0009_lesson_lessonpage_lessoncompletion'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='lessoncompletion',
            name='review_text',
            field=models.TextField(blank=True, null=True, verbose_name='Отзыв пользователя'),
        ),
        migrations.AddField(
            model_name='lessoncompletion',
            name='admin_comment',
            field=models.TextField(blank=True, null=True, verbose_name='Комментарий администратора'),
        ),
        migrations.AddField(
            model_name='lessoncompletion',
            name='admin_comment_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='UserNotification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('message', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('read_at', models.DateTimeField(blank=True, null=True)),
                ('lesson_completion', models.ForeignKey(blank=True, db_column='lesson_completion_id', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='notifications', to='main.lessoncompletion')),
                ('user', models.ForeignKey(db_column='user_id', on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'user_notification',
                'ordering': ['-created_at'],
            },
        ),
    ]
