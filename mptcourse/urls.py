from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework import permissions
from main import views
from main.metrics_view import metrics_export
from main.metrics_influxdb_view import metrics_influxdb_export, metrics_influxdb_check, metrics_influxdb_cleanup, metrics_influxdb_telegraf_view

schema_view = get_schema_view(
    openapi.Info(
        title="MPTCOURSE API",
        default_version='v1',
        description="API документация",
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
)

urlpatterns = [
    # favicon, чтобы не падать на кастомном handler404/500
    path('favicon.ico', views.favicon_view, name='favicon'),
    # Кастомные админские пути (должны быть ПЕРЕД admin.site.urls)
    path('admin/users/', views.admin_users_list, name='admin_users_list'),
    path('admin/users/create/', views.admin_user_create, name='admin_user_create'),
    path('admin/users/import-csv/', views.admin_users_import_csv, name='admin_users_import_csv'),
    path('admin/users/<int:user_id>/edit/', views.admin_user_edit, name='admin_user_edit'),
    path('admin/users/<int:user_id>/delete/', views.admin_user_delete, name='admin_user_delete'),
    path('admin/roles/', views.admin_roles_list, name='admin_roles_list'),
    path('admin/dashboard/', views.management_dashboard, name='admin_dashboard'),
    path('admin/courses/', views.admin_courses_list, name='admin_courses_list'),
    path('admin/courses/add/', views.admin_course_add, name='admin_course_add'),
    path('admin/courses/<int:course_id>/edit/', views.admin_course_edit, name='admin_course_edit'),
    path('admin/courses/<int:course_id>/delete/', views.admin_course_delete, name='admin_course_delete'),
    path('admin/courses/<int:course_id>/lesson/add/', views.admin_lesson_add, name='admin_lesson_add'),
    path('admin/courses/<int:course_id>/lesson/<int:lesson_id>/edit/', views.admin_lesson_edit, name='admin_lesson_edit'),
    path('admin/course-categories/', views.admin_course_categories_list, name='admin_course_categories_list'),
    path('admin/course-categories/add/', views.admin_course_category_add, name='admin_course_category_add'),
    path('admin/course-categories/<int:category_id>/edit/', views.admin_course_category_edit, name='admin_course_category_edit'),
    path('admin/products/', views.admin_redirect_to_dashboard, name='admin_products_list'),
    path('admin/products/add/', views.admin_redirect_to_dashboard, name='admin_product_add'),
    path('admin/products/import-csv/', views.admin_redirect_to_dashboard, name='admin_products_import_csv'),
    path('admin/products/<int:product_id>/edit/', views.admin_redirect_to_dashboard, name='admin_product_edit'),
    path('admin/products/<int:product_id>/delete/', views.admin_redirect_to_dashboard, name='admin_product_delete'),
    path('admin/orders/', views.admin_orders_list, name='admin_orders_list'),
    path('admin/orders/<int:order_id>/', views.admin_order_detail, name='admin_order_detail'),
    path('admin/support/', views.admin_support_list, name='admin_support_list'),
    path('admin/support/<int:ticket_id>/', views.admin_support_detail, name='admin_support_detail'),
    path('admin/lesson-feedback-stats/', views.admin_lesson_feedback_stats, name='admin_lesson_feedback_stats'),
    path('admin/courses/<int:course_id>/lesson-feedback/', views.admin_course_lesson_feedback_list, name='admin_course_lesson_feedback_list'),
    path('admin/lesson-completion/<int:completion_id>/comment/', views.admin_lesson_completion_comment, name='admin_lesson_completion_comment'),
    path('admin/refunds/', views.admin_refund_list, name='admin_refund_list'),
    path('admin/refunds/<int:refund_id>/approve/', views.admin_refund_approve, name='admin_refund_approve'),
    path('admin/refunds/<int:refund_id>/pdf/', views.admin_refund_pdf, name='admin_refund_pdf'),
    path('admin/analytics/', views.admin_analytics, name='admin_analytics'),
    path('admin/analytics/export.csv', views.admin_analytics_export_csv, name='admin_analytics_export_csv'),
    path('admin/analytics/export.pdf', views.admin_analytics_export_pdf, name='admin_analytics_export_pdf'),
    path('admin/activity-logs/', views.admin_activity_logs, name='admin_activity_logs'),
    path('admin/activity-logs/<int:log_id>/', views.admin_activity_log_detail, name='admin_activity_log_detail'),
    path('admin/promotions/', views.admin_promotions_list, name='admin_promotions_list'),
    path('admin/promotions/add/', views.admin_promotion_add, name='admin_promotion_add'),
    path('admin/promotions/<int:promo_id>/edit/', views.admin_promotion_edit, name='admin_promotion_edit'),
    path('admin/promotions/<int:promo_id>/delete/', views.admin_promotion_delete, name='admin_promotion_delete'),
    path('admin/categories/', views.admin_redirect_to_dashboard, name='admin_categories_list'),
    path('admin/categories/add/', views.admin_redirect_to_dashboard, name='admin_category_add'),
    path('admin/categories/import-csv/', views.admin_redirect_to_dashboard, name='admin_categories_import_csv'),
    path('admin/categories/<int:category_id>/edit/', views.admin_redirect_to_dashboard, name='admin_category_edit'),
    path('admin/brands/add/', views.admin_redirect_to_dashboard, name='admin_brand_add'),
    path('admin/brands/<int:brand_id>/edit/', views.admin_redirect_to_dashboard, name='admin_brand_edit'),
    path('admin/suppliers/', views.admin_redirect_to_dashboard, name='admin_suppliers_list'),
    path('admin/suppliers/add/', views.admin_redirect_to_dashboard, name='admin_supplier_add'),
    path('admin/suppliers/<int:supplier_id>/edit/', views.admin_redirect_to_dashboard, name='admin_supplier_edit'),
    path('admin/suppliers/<int:supplier_id>/delete/', views.admin_redirect_to_dashboard, name='admin_supplier_delete'),
    path('admin/backups/', views.admin_backups_list, name='admin_backups_list'),
    path('admin/backups/create/', views.admin_backup_create, name='admin_backup_create'),
    path('admin/backups/<int:backup_id>/download/', views.admin_backup_download, name='admin_backup_download'),
    path('admin/backups/<int:backup_id>/delete/', views.admin_backup_delete, name='admin_backup_delete'),
    path('admin/backups/<int:backup_id>/restore/', views.admin_backup_restore, name='admin_backup_restore'),
    path('admin/backups/delete-db/', views.admin_db_delete, name='admin_db_delete'),
    path('admin/org-account/', views.admin_org_account, name='admin_org_account'),
    path('admin/settings/', views.admin_settings, name='admin_settings'),
    # Экстренное восстановление БД (работает без подключения к БД)
    path('admin-secret-check/', views.admin_secret_check, name='admin_secret_check'),
    path('emergency-restore/', views.emergency_restore, name='emergency_restore'),
    # Django Admin (после кастомных путей)
    path('admin/', admin.site.urls),
    path('', include('main.urls')),
    re_path(r'^swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    # Prometheus metrics endpoints
    path('metrics/', metrics_export, name='metrics'),  # Кастомные + стандартные метрики
    path('prometheus/metricks', metrics_export, name='prometheus_metrics'),  # Для совместимости с Prometheus конфигом
    path('prometheus/metrics', metrics_export, name='prometheus_metrics_correct'),  # Правильный путь
    # InfluxDB metrics endpoints
    path('influxdb/metrics', metrics_influxdb_export, name='influxdb_metrics'),  # Отправка метрик в InfluxDB
    path('influxdb/check', metrics_influxdb_check, name='influxdb_check'),  # Проверка записанных метрик в InfluxDB
    path('influxdb/telegraf', metrics_influxdb_telegraf_view, name='influxdb_telegraf'),  # Просмотр метрик, отправленных через Telegraf
    path('influxdb/cleanup', metrics_influxdb_cleanup, name='influxdb_cleanup'),  # Удаление старых метрик с английскими статусами
    # Catch-all для обработки 404 ошибок (должен быть последним)
    re_path(r'^.*$', views.handler404, name='404'),
]

# Обработчики ошибок
handler404 = 'main.views.handler404'
handler500 = 'main.views.handler500'

# В Docker Nginx раздает статику и медиа, но для разработки оставляем
if settings.DEBUG:
    from django.contrib.staticfiles.urls import staticfiles_urlpatterns
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += staticfiles_urlpatterns()