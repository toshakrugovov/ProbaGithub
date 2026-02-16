# Lesson-based course structure (GetCourse-style): Course -> Lessons -> LessonPages; LessonCompletion for progress

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0008_organizationtransaction_course_purchase'),
    ]

    operations = [
        migrations.CreateModel(
            name='Lesson',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('title', models.CharField(blank=True, max_length=255, null=True, verbose_name='Название урока')),
                ('course', models.ForeignKey(db_column='course_id', on_delete=django.db.models.deletion.CASCADE, related_name='lessons', to='main.course')),
            ],
            options={
                'db_table': 'lesson',
                'ordering': ['sort_order', 'id'],
            },
        ),
        migrations.CreateModel(
            name='LessonPage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sort_order', models.PositiveSmallIntegerField(default=0)),
                ('page_type', models.CharField(choices=[('image', 'Изображение'), ('video', 'Видео (YouTube/Rutube/ссылка)'), ('pdf_page', 'Страница PDF')], default='image', max_length=20)),
                ('file_path', models.CharField(blank=True, max_length=500, null=True)),
                ('page_number', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('text', models.TextField(blank=True, null=True, verbose_name='Текст страницы')),
                ('lesson', models.ForeignKey(db_column='lesson_id', on_delete=django.db.models.deletion.CASCADE, related_name='pages', to='main.lesson')),
            ],
            options={
                'db_table': 'lesson_page',
                'ordering': ['sort_order', 'id'],
            },
        ),
        migrations.CreateModel(
            name='LessonCompletion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('completed_at', models.DateTimeField(auto_now_add=True)),
                ('liked', models.BooleanField(blank=True, null=True, verbose_name='Понравился урок (👍/👎)')),
                ('course_purchase', models.ForeignKey(db_column='course_purchase_id', on_delete=django.db.models.deletion.CASCADE, related_name='lesson_completions', to='main.coursepurchase')),
                ('lesson', models.ForeignKey(db_column='lesson_id', on_delete=django.db.models.deletion.CASCADE, related_name='completions', to='main.lesson')),
            ],
            options={
                'db_table': 'lesson_completion',
                'unique_together': {('course_purchase', 'lesson')},
            },
        ),
    ]
