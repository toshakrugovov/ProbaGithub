from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .api import (
    RoleViewSet, UserProfileViewSet, UserAddressViewSet,
    CartViewSet, CartItemViewSet, OrderItemViewSet, PaymentViewSet, PromotionViewSet,
    SupportTicketViewSet, ActivityLogViewSet, CheckEmailView, LoginView, RegisterView, ResetPasswordView, VerifyResetDataView,
    ProfileAPIView, AddressAPIView, AddressDetailAPIView, CartAPIView, CartItemAPIView,
    OrderAPIView, OrderDetailAPIView, PaymentMethodAPIView, PaymentMethodDetailAPIView,
    BalanceAPIView, ValidatePromoAPIView, AvailablePromotionsAPIView,
    CourseManagementAPIView, CourseManagementDetailAPIView,
    CourseCategoryManagementAPIView, CourseCategoryManagementDetailAPIView,
    OrderManagementAPIView, OrderManagementDetailAPIView,
    UserManagementAPIView, UserManagementDetailAPIView, SupportTicketAPIView,
    SupportTicketDetailAPIView, CatalogAPIView, FavoritesAPIView, FavoriteDetailAPIView,
    OrganizationAccountAPIView, PromotionManagementAPIView,
    PromotionManagementDetailAPIView,
    RoleManagementAPIView, RoleManagementDetailAPIView, BackupManagementAPIView,
    BackupManagementDetailAPIView, UserSettingsAPIView,
    CourseReviewAPIView
)
from django.contrib.auth import views as auth_views
from . import views
from django.conf import settings
from django.conf.urls.static import static


router = DefaultRouter()
router.register(r'roles', RoleViewSet)
router.register(r'user-profiles', UserProfileViewSet)
router.register(r'user-addresses', UserAddressViewSet)
router.register(r'carts', CartViewSet)
router.register(r'cart-items', CartItemViewSet)
router.register(r'order-items', OrderItemViewSet)
router.register(r'payments', PaymentViewSet)
router.register(r'promotions', PromotionViewSet)
router.register(r'support-tickets', SupportTicketViewSet)
router.register(r'activity-logs', ActivityLogViewSet)

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('contacts/', views.contacts, name='contacts'),
    path('brand-book/', views.brand_book, name='brand_book'),
    path('refund/', views.refund, name='refund'),
    path('bonus/', views.bonus, name='bonus'),
    path('delivery/', views.delivery, name='delivery'), 
    path('favorites/', views.favorites, name='favorites'), 
    path('about/', views.about, name='about'), 
    path('catalog/', views.catalog, name='catalog'),
    
    # Профиль пользователя
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('profile/my-courses/', views.my_courses_view, name='my_courses'),
    path('profile/my-courses/<int:purchase_id>/', views.course_view, name='course_view'),
    path('profile/my-courses/<int:purchase_id>/lessons/', views.course_lessons_list, name='course_lessons_list'),
    path('profile/my-courses/<int:purchase_id>/lesson/<int:lesson_id>/', views.lesson_view, name='lesson_view'),
    path('profile/my-courses/<int:purchase_id>/media/', views.serve_course_media, name='serve_course_media'),
    path('profile/my-courses/<int:purchase_id>/lesson/<int:lesson_id>/feedback/', views.lesson_feedback, name='lesson_feedback'),
    path('profile/my-courses/<int:purchase_id>/view-page/', views.course_content_view_record, name='course_content_view_record'),
    path('profile/my-courses/<int:purchase_id>/survey/', views.course_survey_submit, name='course_survey_submit'),
    path('profile/my-courses/<int:purchase_id>/review/', views.course_review_submit, name='course_review_submit'),
    path('profile/my-courses/<int:purchase_id>/refund-request/', views.course_refund_request_create, name='course_refund_request_create'),
    path('profile/orders/', views.order_history_view, name='order_history'),
    path('profile/orders/<int:pk>/', views.order_detail_view, name='order_detail'),
    path('profile/addresses/', views.addresses_view, name='addresses'),
    path('profile/payment-methods/', views.payment_methods_view, name='payment_methods'),
    path('profile/payment-methods/add/', views.add_payment_method, name='add_payment_method'),
    path('profile/payment-methods/<int:payment_id>/delete/', views.delete_payment_method, name='delete_payment_method'),
    path('profile/payment-methods/<int:payment_id>/set-default/', views.set_default_payment_method, name='set_default_payment_method'),
    path('profile/payment-methods/<int:card_id>/transactions/', views.get_card_transactions, name='get_card_transactions'),
    path('profile/payment-methods/<int:card_id>/deposit/', views.deposit_from_card, name='deposit_from_card'),
    path('profile/payment-methods/<int:card_id>/withdraw/', views.withdraw_to_card, name='withdraw_to_card'),
    path('profile/payment-methods/<int:card_id>/topup/', views.topup_card_balance, name='topup_card_balance'),

    # Receipts
    path('profile/receipts/', views.receipts_list, name='receipts_list'),
    path('profile/receipts/<int:receipt_id>/', views.receipt_view, name='receipt_view'),
    path('profile/receipts/<int:receipt_id>/pdf/', views.receipt_pdf, name='receipt_pdf'),
    path('profile/refunds/', views.refund_requests_list, name='refund_requests_list'),
    path('profile/refunds/<int:refund_id>/pdf/', views.refund_request_pdf, name='refund_request_pdf'),
    path('profile/notifications/', views.notifications_view, name='notifications'),
    path('profile/balance/', views.balance_view, name='balance'),
    path('profile/balance/deposit/', views.deposit_balance, name='deposit_balance'),
    path('profile/balance/withdraw/', views.withdraw_balance, name='withdraw_balance'),
    path('profile/orders/<int:pk>/cancel/', views.cancel_order, name='cancel_order'),

    # API
    path('api/', include(router.urls)),
    path('api/check-email/', CheckEmailView.as_view(), name='check-email'),
    path('api/login/', LoginView.as_view(), name='api-login'),
    path('api/register/', RegisterView.as_view(), name='api-register'),
    path('api/reset-password/', ResetPasswordView.as_view(), name='api-reset-password'),
    path('api/verify-reset-data/', VerifyResetDataView.as_view(), name='api-verify-reset-data'),
    
    # Новые API endpoints
    path('api/profile/', ProfileAPIView.as_view(), name='api-profile'),
    path('api/settings/', UserSettingsAPIView.as_view(), name='api-settings'),
    path('api/addresses/', AddressAPIView.as_view(), name='api-addresses'),
    path('api/addresses/<int:address_id>/', AddressDetailAPIView.as_view(), name='api-address-detail'),
    path('api/cart/', CartAPIView.as_view(), name='api-cart'),
    path('api/cart/items/<int:item_id>/', CartItemAPIView.as_view(), name='api-cart-item'),
    path('api/orders/', OrderAPIView.as_view(), name='api-orders'),
    path('api/orders/<int:order_id>/', OrderDetailAPIView.as_view(), name='api-order-detail'),
    path('api/payment-methods/', PaymentMethodAPIView.as_view(), name='api-payment-methods'),
    path('api/payment-methods/<int:card_id>/', PaymentMethodDetailAPIView.as_view(), name='api-payment-method-detail'),
    path('api/balance/', BalanceAPIView.as_view(), name='api-balance'),
    path('api/validate-promo/', ValidatePromoAPIView.as_view(), name='api-validate-promo'),
    path('api/available-promotions/', AvailablePromotionsAPIView.as_view(), name='api-available-promotions'),
    
    # API для менеджеров и админов (только курсы)
    path('api/management/courses/', CourseManagementAPIView.as_view(), name='api-management-courses'),
    path('api/management/courses/<int:course_id>/', CourseManagementDetailAPIView.as_view(), name='api-management-course-detail'),
    path('api/management/course-categories/', CourseCategoryManagementAPIView.as_view(), name='api-management-course-categories'),
    path('api/management/course-categories/<int:category_id>/', CourseCategoryManagementDetailAPIView.as_view(), name='api-management-course-category-detail'),
    path('api/management/orders/', OrderManagementAPIView.as_view(), name='api-management-orders'),
    path('api/management/orders/<int:order_id>/', OrderManagementDetailAPIView.as_view(), name='api-management-order-detail'),
    path('api/management/users/', UserManagementAPIView.as_view(), name='api-management-users'),
    path('api/management/users/<int:user_id>/', UserManagementDetailAPIView.as_view(), name='api-management-user-detail'),
    path('api/management/org-account/', OrganizationAccountAPIView.as_view(), name='api-management-org-account'),
    path('api/management/promotions/', PromotionManagementAPIView.as_view(), name='api-management-promotions'),
    path('api/management/promotions/<int:promo_id>/', PromotionManagementDetailAPIView.as_view(), name='api-management-promotion-detail'),
    path('api/management/roles/', RoleManagementAPIView.as_view(), name='api-management-roles'),
    path('api/management/roles/<int:role_id>/', RoleManagementDetailAPIView.as_view(), name='api-management-role-detail'),
    path('api/management/backups/', BackupManagementAPIView.as_view(), name='api-management-backups'),
    path('api/management/backups/<int:backup_id>/', BackupManagementDetailAPIView.as_view(), name='api-management-backup-detail'),
    
    # API для поддержки
    path('api/support/', SupportTicketAPIView.as_view(), name='api-support'),
    path('api/support/<int:ticket_id>/', SupportTicketDetailAPIView.as_view(), name='api-support-detail'),
    
    # API для каталога
    path('api/catalog/', CatalogAPIView.as_view(), name='api-catalog'),
    
    # API для избранного
    path('api/favorites/', FavoritesAPIView.as_view(), name='api-favorites'),
    path('api/favorites/<int:product_id>/', FavoriteDetailAPIView.as_view(), name='api-favorite-detail'),
    
    # API для отзывов
    path('api/courses/<int:course_id>/reviews/', CourseReviewAPIView.as_view(), name='api-course-reviews'),

    # Старые endpoints (для обратной совместимости, можно будет удалить после переписывания фронтенда)
    path('favorites/add/', views.add_to_favorites, name='api-favorites-add'),
    path('favorites/remove/<int:product_id>/', views.remove_from_favorites, name='remove_from_favorites'),
    path('product/<int:product_id>/status/', views.check_product_status, name='check_product_status'),

    # Добавление в корзину (course_id; product_id в URL для совместимости с каталогом)
    path('cart/add/<int:product_id>/', views.add_to_cart, name='add_to_cart'),
    path('cart/add/course/<int:course_id>/', views.add_to_cart_course, name='add_to_cart_course'),
    path('cart/remove-product/<int:product_id>/', views.remove_from_cart_by_product, name='remove_from_cart_by_product'),
    path('cart/', views.cart_view, name='cart'),
    path('logout/', auth_views.LogoutView.as_view(next_page='home'), name='logout'),
    path('profile/delete/', views.delete_account, name='delete_account'),
    path('custom-admin-login/', views.custom_admin_login, name='custom_admin_login'),
    path('emergency-restore/', views.emergency_restore, name='emergency_restore'),
    path('cart/remove/<int:item_id>/', views.remove_from_cart, name='remove_from_cart'),
    path('cart/update/<int:item_id>/', views.update_cart_quantity, name='update_cart_quantity'),
    path('checkout/', views.checkout, name='checkout'),
    
    # Management (custom) - Админ панель
    path('management/', views.management_dashboard, name='management_dashboard'),
    path('management/users/', views.management_users_list, name='management_users_list'),
    path('management/users/<int:user_id>/edit/', views.management_user_edit, name='management_user_edit'),
    path('management/users/<int:user_id>/toggle-block/', views.management_user_toggle_block, name='management_user_toggle_block'),
    path('management/orders/', views.management_orders_list, name='management_orders_list'),
    path('management/orders/<int:order_id>/status/', views.management_order_change_status, name='management_order_change_status'),
    path('management/analytics/export.csv', views.management_analytics_export_csv, name='management_analytics_export_csv'),
    path('management/promotions/', views.management_promotions_list, name='management_promotions_list'),
    path('management/promotions/add/', views.management_promotion_add, name='management_promotion_add'),
    path('management/promotions/<int:promo_id>/edit/', views.management_promotion_edit, name='management_promotion_edit'),
    path('management/promotions/<int:promo_id>/delete/', views.management_promotion_delete, name='management_promotion_delete'),
    
    # Админ панель (отдельные URL для админов, чтобы не попадать на страницы менеджера)
    path('admin/orders/', views.admin_orders_list, name='admin_orders_list'),
    path('admin/orders/<int:order_id>/', views.admin_order_detail, name='admin_order_detail'),
    path('admin/refunds/', views.admin_refund_list, name='admin_refund_list'),
    path('admin/refunds/<int:refund_id>/approve/', views.admin_refund_approve, name='admin_refund_approve'),
    path('admin/refunds/<int:refund_id>/pdf/', views.admin_refund_pdf, name='admin_refund_pdf'),

    # Отзывы на товары
    path('product/<int:product_id>/reviews/', views.get_product_reviews, name='get_product_reviews'),
    path('product/<int:product_id>/reviews/page/', views.product_reviews_page, name='product_reviews_page'),
    path('product/<int:product_id>/review/add/', views.add_review, name='add_review'),
    
    # Валидация промокода
    path('checkout/promo/validate/', views.validate_promo, name='validate_promo'),
    
    # Техническая поддержка
    path('support/', views.support_view, name='support'),
    path('support/create/', views.create_support_ticket, name='create_support_ticket'),
    path('support/<int:ticket_id>/', views.support_ticket_detail, name='support_ticket_detail'),
    
    # Панель менеджера
    path('manager/', views.manager_dashboard, name='manager_dashboard'),
    
    # Управление курсами
    path('manager/courses/', views.manager_courses_list, name='manager_courses_list'),
    path('manager/courses/add/', views.manager_course_add, name='manager_course_add'),
    path('manager/courses/<int:course_id>/edit/', views.manager_course_edit, name='manager_course_edit'),
    path('manager/courses/<int:course_id>/delete/', views.manager_course_delete, name='manager_course_delete'),
    path('manager/courses/<int:course_id>/lesson/add/', views.manager_lesson_add, name='manager_lesson_add'),
    path('manager/courses/<int:course_id>/lesson/<int:lesson_id>/edit/', views.manager_lesson_edit, name='manager_lesson_edit'),
    
    # Категории курсов
    path('manager/course-categories/', views.manager_course_categories_list, name='manager_course_categories_list'),
    path('manager/course-categories/add/', views.manager_course_category_add, name='manager_course_category_add'),
    path('manager/course-categories/<int:category_id>/edit/', views.manager_course_category_edit, name='manager_course_category_edit'),
    
    # Управление заказами
    path('manager/orders/', views.manager_orders_list, name='manager_orders_list'),
    path('manager/orders/<int:order_id>/', views.manager_order_detail, name='manager_order_detail'),
    
    # Управление пользователями
    path('manager/users/', views.manager_users_list, name='manager_users_list'),
    path('manager/users/<int:user_id>/toggle-block/', views.manager_user_toggle_block, name='manager_user_toggle_block'),
    
    # Управление поддержкой
    path('manager/support/', views.manager_support_list, name='manager_support_list'),
    path('manager/support/<int:ticket_id>/', views.manager_support_detail, name='manager_support_detail'),
    
    # Аналитика
    path('manager/analytics/', views.manager_analytics, name='manager_analytics'),
    path('manager/analytics/export.csv', views.manager_analytics_export_csv, name='manager_analytics_export_csv'),
    path('manager/analytics/export.pdf', views.manager_analytics_export_pdf, name='manager_analytics_export_pdf'),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)