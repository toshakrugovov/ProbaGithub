from django.contrib import admin
from django.utils import timezone
from .models import (
    Role, UserAddress, UserProfile, UserSettings,
    CourseCategory, Course, CourseImage, CourseContentPage, CoursePurchase, CourseContentView, CourseSurvey, CourseReview, CourseFavorite,
    Lesson, LessonPage, LessonCompletion,
    UserNotification,
    Cart, CartItem, Order, OrderItem, Payment, Receipt, ReceiptItem, ReceiptConfig,
    Promotion, PromoUsage, SupportTicket, ActivityLog, DatabaseBackup,
    SavedPaymentMethod, CardTransaction, BalanceTransaction,
    OrganizationAccount, OrganizationTransaction,
)

@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('id', 'role_name')
    search_fields = ('role_name',)
    
    class Meta:
        verbose_name = 'Роль'
        verbose_name_plural = 'Роли'

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'full_name', 'role', 'user_status', 'registered_at')
    list_filter = ('user_status', 'role')
    search_fields = ('user__username', 'user__email', 'full_name')
    
    class Meta:
        verbose_name = 'Профиль пользователя'
        verbose_name_plural = 'Профили пользователей'

@admin.register(CourseCategory)
class CourseCategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'category_name', 'parent')
    list_filter = ('parent',)
    search_fields = ('category_name',)

class CourseImageInline(admin.TabularInline):
    model = CourseImage
    extra = 0
    max_num = 4
    verbose_name = 'Фото курса'
    verbose_name_plural = 'Фото курса (4 шт., одно главное)'

class CourseContentPageInline(admin.TabularInline):
    model = CourseContentPage
    extra = 0
    verbose_name = 'Модальное окно (страница контента)'
    verbose_name_plural = 'Внутри курса: модальные окна (плюс — добавить ещё, чаще PDF: 1 страница = 1 окно)'

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'slug', 'category', 'price', 'discount', 'is_available', 'added_at')
    list_filter = ('category', 'is_available')
    search_fields = ('title', 'description', 'included_content', 'slug')
    prepopulated_fields = {'slug': ('title',)}
    inlines = [CourseImageInline, CourseContentPageInline]
    fieldsets = (
        (None, {'fields': ('title', 'slug', 'category', 'description', 'included_content', 'price', 'discount', 'is_available', 'cover_image_path')}),
    )

@admin.register(CourseContentPage)
class CourseContentPageAdmin(admin.ModelAdmin):
    list_display = ('id', 'course', 'sort_order', 'content_type', 'title', 'page_number')
    list_filter = ('content_type',)
    search_fields = ('course__title', 'title')

@admin.register(CoursePurchase)
class CoursePurchaseAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'course', 'amount', 'status', 'payment_method', 'paid_at', 'completed_at', 'created_at')
    list_filter = ('status', 'payment_method')
    search_fields = ('user__username', 'course__title')


@admin.register(CourseContentView)
class CourseContentViewAdmin(admin.ModelAdmin):
    list_display = ('id', 'course_purchase', 'content_page', 'viewed_at')
    list_filter = ('viewed_at',)
    search_fields = ('course_purchase__user__username',)


class LessonPageInline(admin.TabularInline):
    model = LessonPage
    extra = 0
    max_num = 10
    ordering = ['sort_order']


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ('id', 'course', 'sort_order', 'title')
    list_filter = ('course',)
    inlines = [LessonPageInline]
    ordering = ['course', 'sort_order']


@admin.register(LessonCompletion)
class LessonCompletionAdmin(admin.ModelAdmin):
    list_display = ('id', 'course_purchase', 'lesson', 'completed_at', 'liked', 'has_review', 'has_admin_comment')
    list_filter = ('liked', 'lesson__course')
    search_fields = ('course_purchase__user__username', 'lesson__title', 'review_text')
    list_editable = ()
    readonly_fields = ('completed_at',)
    fieldsets = (
        (None, {'fields': ('course_purchase', 'lesson', 'completed_at', 'liked', 'review_text')}),
        ('Комментарий администратора', {'fields': ('admin_comment', 'admin_comment_at')}),
    )

    def has_review(self, obj):
        return bool(obj.review_text and obj.review_text.strip())
    has_review.boolean = True
    has_review.short_description = 'Есть отзыв'

    def has_admin_comment(self, obj):
        return bool(obj.admin_comment and obj.admin_comment.strip())
    has_admin_comment.boolean = True
    has_admin_comment.short_description = 'Ответ админа'

    def save_model(self, request, obj, form, change):
        old_comment = None
        if change and obj.pk:
            try:
                old = LessonCompletion.objects.get(pk=obj.pk)
                old_comment = (old.admin_comment or '').strip()
            except LessonCompletion.DoesNotExist:
                pass
        obj.save()
        new_comment = (obj.admin_comment or '').strip()
        if new_comment and new_comment != old_comment:
            obj.admin_comment_at = timezone.now()
            obj.save(update_fields=['admin_comment_at'])
            user = obj.course_purchase.user
            lesson_title = obj.lesson.title or 'Урок'
            msg = f'Администратор ответил на ваш отзыв к уроку «{lesson_title}»: {new_comment[:200]}{"…" if len(new_comment) > 200 else ""}'
            UserNotification.objects.create(user=user, message=msg, lesson_completion=obj)


@admin.register(UserNotification)
class UserNotificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'message_short', 'created_at', 'read_at')
    list_filter = ('created_at',)
    search_fields = ('user__username', 'message')
    readonly_fields = ('created_at',)

    def message_short(self, obj):
        return (obj.message[:80] + '…') if obj.message and len(obj.message) > 80 else (obj.message or '')
    message_short.short_description = 'Сообщение'

@admin.register(CourseSurvey)
class CourseSurveyAdmin(admin.ModelAdmin):
    list_display = ('id', 'course', 'user', 'course_purchase', 'submitted_at')
    search_fields = ('course__title', 'user__username')

@admin.register(CourseReview)
class CourseReviewAdmin(admin.ModelAdmin):
    list_display = ('id', 'course', 'user', 'rating', 'created_at')
    list_filter = ('rating',)
    search_fields = ('course__title', 'user__username', 'review_text')

@admin.register(CourseFavorite)
class CourseFavoriteAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'course', 'added_at')
    search_fields = ('user__username', 'course__title')

@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'created_at')
    search_fields = ('user__username',)
    
    class Meta:
        verbose_name = 'Корзина'
        verbose_name_plural = 'Корзины'

@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'cart', 'course', 'quantity', 'unit_price')
    search_fields = ('course__title', 'cart__user__username')
    
    class Meta:
        verbose_name = 'Элемент корзины'
        verbose_name_plural = 'Элементы корзины'

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'address', 'total_amount', 'order_status', 'created_at')
    list_filter = ('order_status',)
    search_fields = ('user__username', 'address__address_title')
    
    class Meta:
        verbose_name = 'Заказ'
        verbose_name_plural = 'Заказы'

@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'course', 'quantity', 'unit_price')
    search_fields = ('course__title', 'order__user__username')
    
    class Meta:
        verbose_name = 'Элемент заказа'
        verbose_name_plural = 'Элементы заказов'

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'payment_method', 'payment_amount', 'payment_status', 'paid_at')
    list_filter = ('payment_method', 'payment_status')
    search_fields = ('order__user__username',)
    
    class Meta:
        verbose_name = 'Платеж'
        verbose_name_plural = 'Платежи'

@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ('id', 'promo_code', 'discount', 'start_date', 'end_date', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('promo_code', 'promo_description')
    
    class Meta:
        verbose_name = 'Промокод'
        verbose_name_plural = 'Промокоды'

@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'subject', 'ticket_status', 'created_at')
    list_filter = ('ticket_status',)
    search_fields = ('subject', 'user__username')
    
    class Meta:
        verbose_name = 'Тикет поддержки'
        verbose_name_plural = 'Тикеты поддержки'

@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'action_type', 'target_object', 'created_at', 'ip_address')
    list_filter = ('action_type',)
    search_fields = ('user__username', 'target_object', 'action_description')
    
    class Meta:
        verbose_name = 'Лог активности'
        verbose_name_plural = 'Логи активности'

@admin.register(ReceiptConfig)
class ReceiptConfigAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'company_inn', 'cashier_name', 'shift_number')
    
    class Meta:
        verbose_name = 'Настройки чека'
        verbose_name_plural = 'Настройки чеков'

class ReceiptItemInline(admin.TabularInline):
    model = ReceiptItem
    extra = 0
    readonly_fields = ('product_name', 'article', 'quantity', 'unit_price', 'line_total', 'vat_amount')
    verbose_name = 'Элемент чека'
    verbose_name_plural = 'Элементы чека'

@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'user', 'created_at', 'status', 'total_amount', 'vat_amount', 'payment_method')
    list_filter = ('status', 'payment_method', 'created_at')
    search_fields = ('order__id', 'user__username', 'number')
    inlines = [ReceiptItemInline]
    
    class Meta:
        verbose_name = 'Чек'
        verbose_name_plural = 'Чеки'

@admin.register(DatabaseBackup)
class DatabaseBackupAdmin(admin.ModelAdmin):
    list_display = ('id', 'backup_name', 'created_at', 'created_by', 'get_file_size_mb', 'schedule', 'is_automatic')
    list_filter = ('schedule', 'is_automatic', 'created_at')
    search_fields = ('backup_name', 'notes')
    readonly_fields = ('created_at', 'file_size', 'backup_file')
    fieldsets = (
        ('Основная информация', {
            'fields': ('backup_name', 'backup_file', 'created_at', 'created_by', 'file_size')
        }),
        ('Настройки', {
            'fields': ('schedule', 'is_automatic', 'notes')
        }),
    )
    
    class Meta:
        verbose_name = 'Бэкап базы данных'
        verbose_name_plural = 'Бэкапы базы данных'

@admin.register(UserAddress)
class UserAddressAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'address_title', 'city_name', 'street_name', 'house_number', 'is_primary')
    list_filter = ('is_primary', 'city_name')
    search_fields = ('user__username', 'city_name', 'street_name', 'address_title')
    
    class Meta:
        verbose_name = 'Адрес пользователя'
        verbose_name_plural = 'Адреса пользователей'

@admin.register(SavedPaymentMethod)
class SavedPaymentMethodAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'card_type', 'get_last_four_digits', 'is_default', 'balance', 'created_at')
    list_filter = ('card_type', 'is_default', 'created_at')
    search_fields = ('user__username', 'card_holder_name')
    readonly_fields = ('created_at',)
    
    class Meta:
        verbose_name = 'Сохраненный способ оплаты'
        verbose_name_plural = 'Сохраненные способы оплаты'

@admin.register(CardTransaction)
class CardTransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'saved_payment_method', 'transaction_type', 'amount', 'status', 'created_at')
    list_filter = ('transaction_type', 'status', 'created_at')
    search_fields = ('saved_payment_method__user__username', 'description')
    
    class Meta:
        verbose_name = 'Транзакция по карте'
        verbose_name_plural = 'Транзакции по картам'

@admin.register(BalanceTransaction)
class BalanceTransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'transaction_type', 'amount', 'status', 'created_at')
    list_filter = ('transaction_type', 'status', 'created_at')
    search_fields = ('user__username', 'description')
    
    class Meta:
        verbose_name = 'Транзакция баланса'
        verbose_name_plural = 'Транзакции баланса'

@admin.register(PromoUsage)
class PromoUsageAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'promotion', 'order', 'course_purchase', 'used_at')
    list_filter = ('used_at',)
    search_fields = ('user__username', 'promotion__promo_code')
    
    class Meta:
        verbose_name = 'Использование промокода'
        verbose_name_plural = 'Использования промокодов'

@admin.register(OrganizationAccount)
class OrganizationAccountAdmin(admin.ModelAdmin):
    list_display = ('id', 'balance', 'tax_reserve', 'created_at', 'updated_at')
    readonly_fields = ('created_at', 'updated_at')
    
    class Meta:
        verbose_name = 'Счет организации'
        verbose_name_plural = 'Счета организаций'

@admin.register(OrganizationTransaction)
class OrganizationTransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'organization_account', 'transaction_type', 'amount', 'created_at')
    list_filter = ('transaction_type', 'created_at')
    search_fields = ('description',)
    
    class Meta:
        verbose_name = 'Транзакция организации'
        verbose_name_plural = 'Транзакции организаций'

@admin.register(ReceiptItem)
class ReceiptItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'receipt', 'course', 'line_description', 'quantity', 'unit_price')
    search_fields = ('product_name', 'article', 'receipt__order__id')
    
    class Meta:
        verbose_name = 'Элемент чека'
        verbose_name_plural = 'Элементы чека'

@admin.register(UserSettings)
class UserSettingsAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'theme', 'date_format', 'number_format', 'page_size', 'updated_at')
    list_filter = ('theme', 'date_format', 'number_format')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('created_at', 'updated_at')
    
    class Meta:
        verbose_name = 'Настройки пользователя'
        verbose_name_plural = 'Настройки пользователей'
