# Migration: only add course tables and course_id to cartitem/orderitem (no removal of old tables)

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0004_alter_supportticket_ticket_status'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CourseCategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('category_name', models.CharField(max_length=100)),
                ('category_description', models.TextField(blank=True, null=True)),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='subcategories', to='main.coursecategory', db_column='parent_id')),
            ],
            options={'db_table': 'course_category'},
        ),
        migrations.CreateModel(
            name='Course',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('slug', models.SlugField(max_length=255, unique=True)),
                ('description', models.TextField(blank=True, null=True)),
                ('included_content', models.TextField(blank=True, null=True)),
                ('price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('discount', models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ('is_available', models.BooleanField(default=True)),
                ('added_at', models.DateTimeField(auto_now_add=True)),
                ('cover_image_path', models.CharField(blank=True, max_length=500, null=True)),
                ('category', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='main.coursecategory', db_column='category_id')),
            ],
            options={'db_table': 'course'},
        ),
        migrations.CreateModel(
            name='CourseImage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image_path', models.CharField(max_length=500)),
                ('is_primary', models.BooleanField(default=False)),
                ('position', models.PositiveSmallIntegerField(default=0)),
                ('course', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='images', to='main.course', db_column='course_id')),
            ],
            options={'db_table': 'course_image', 'ordering': ['-is_primary', 'position', 'id']},
        ),
        migrations.CreateModel(
            name='CourseContentPage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('content_type', models.CharField(max_length=20)),
                ('file_path', models.CharField(max_length=500)),
                ('title', models.CharField(blank=True, max_length=255, null=True)),
                ('page_number', models.PositiveIntegerField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('course', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='content_pages', to='main.course', db_column='course_id')),
            ],
            options={'db_table': 'course_content_page', 'ordering': ['sort_order']},
        ),
        migrations.CreateModel(
            name='CoursePurchase',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('paid_at', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(default='pending', max_length=30)),
                ('payment_method', models.CharField(blank=True, max_length=50, null=True)),
                ('discount_amount', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('course', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='main.course', db_column='course_id')),
                ('promo_code', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='main.promotion', db_column='promo_code_id')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL, db_column='user_id')),
            ],
            options={'db_table': 'course_purchase'},
        ),
        migrations.CreateModel(
            name='CourseContentView',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('viewed_at', models.DateTimeField(auto_now_add=True)),
                ('content_page', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='main.coursecontentpage', db_column='course_content_page_id')),
                ('course_purchase', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='content_views', to='main.coursepurchase', db_column='course_purchase_id')),
            ],
            options={'db_table': 'course_content_view'},
        ),
        migrations.CreateModel(
            name='CourseSurvey',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('answers', models.JSONField(default=dict)),
                ('submitted_at', models.DateTimeField(auto_now_add=True)),
                ('course', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='main.course', db_column='course_id')),
                ('course_purchase', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to='main.coursepurchase', db_column='course_purchase_id')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL, db_column='user_id')),
            ],
            options={'db_table': 'course_survey'},
        ),
        migrations.CreateModel(
            name='CourseReview',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rating', models.PositiveSmallIntegerField()),
                ('review_text', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('course', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='main.course', db_column='course_id')),
                ('course_purchase', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='main.coursepurchase', db_column='course_purchase_id')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL, db_column='user_id')),
            ],
            options={'db_table': 'course_review'},
        ),
        migrations.CreateModel(
            name='CourseFavorite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('added_at', models.DateTimeField(auto_now_add=True)),
                ('course', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='main.course', db_column='course_id')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL, db_column='user_id')),
            ],
            options={'db_table': 'course_favorite'},
        ),
        migrations.AddField(
            model_name='cartitem',
            name='course',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='main.course', db_column='course_id'),
        ),
        migrations.AddField(
            model_name='orderitem',
            name='course',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='main.course', db_column='course_id'),
        ),
        migrations.AlterUniqueTogether(
            name='coursecontentview',
            unique_together={('course_purchase', 'content_page')},
        ),
        migrations.AlterUniqueTogether(
            name='coursefavorite',
            unique_together={('user', 'course')},
        ),
    ]
