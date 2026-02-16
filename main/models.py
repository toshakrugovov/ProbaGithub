import base64

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db.models import Sum, F
from decimal import InvalidOperation

# ==== Роли пользователей ====
class Role(models.Model):
    role_name = models.CharField(max_length=50, unique=True)

    class Meta:
        db_table = 'role'

    def __str__(self):
        return self.role_name


# ==== Профили пользователей (3НФ: full_name не храним — из auth_user) ====
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile', db_column='user_id')
    role = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True, blank=True, db_column='role_id')
    phone_number = models.CharField(max_length=50, blank=True, null=True)
    birth_date = models.DateField(blank=True, null=True)
    user_status = models.CharField(max_length=50, default='active')
    registered_at = models.DateTimeField(auto_now_add=True)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    secret_word = models.CharField(max_length=255, blank=True, null=True, verbose_name='Секретное слово', help_text='Используется для восстановления пароля и подтверждения важных действий')

    class Meta:
        db_table = 'userprofile'

    @property
    def full_name(self):
        """3НФ: имя выводится из auth_user."""
        if getattr(self, 'user_id', None) and hasattr(self, 'user'):
            return f"{self.user.first_name} {self.user.last_name}".strip()
        return ''

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            from django.apps import apps
            UserSettings = apps.get_model('main', 'UserSettings')
            UserSettings.get_or_create_for_user(self.user)

    def __str__(self):
        return self.full_name or (getattr(self.user, 'username', '') if hasattr(self, 'user') else '')


# ==== Адреса пользователей ====
class UserAddress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='addresses', db_column='user_id')
    address_title = models.CharField(max_length=100, blank=True, null=True)
    city_name = models.CharField(max_length=100)
    street_name = models.CharField(max_length=100)
    house_number = models.CharField(max_length=20)
    apartment_number = models.CharField(max_length=20, blank=True, null=True)
    postal_code = models.CharField(max_length=20)
    is_primary = models.BooleanField(default=False)

    class Meta:
        db_table = 'useraddress'

    def __str__(self):
        return f"{self.city_name}, {self.street_name} {self.house_number}"


# ==== Категории курсов (MPTCOURSE) ====
class CourseCategory(models.Model):
    category_name = models.CharField(max_length=100)
    category_description = models.TextField(blank=True, null=True)
    parent = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True, related_name='subcategories', db_column='parent_id'
    )

    class Meta:
        db_table = 'course_category'

    def __str__(self):
        return self.category_name


# ==== Курсы (товары = курсы) ====
class Course(models.Model):
    category = models.ForeignKey(CourseCategory, on_delete=models.SET_NULL, null=True, blank=True, db_column='category_id')
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(blank=True, null=True)
    included_content = models.TextField(
        blank=True, null=True,
        verbose_name='Что входит в состав курса',
        help_text='Описание состава курса для карточки (что входит в программу)'
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    is_available = models.BooleanField(default=True)
    added_at = models.DateTimeField(auto_now_add=True)
    cover_image_path = models.CharField(max_length=500, blank=True, null=True)

    class Meta:
        db_table = 'course'

    def __str__(self):
        return self.title

    @property
    def final_price(self):
        try:
            return (self.price or Decimal('0')) * (Decimal('1') - (self.discount or Decimal('0')) / Decimal('100'))
        except Exception:
            return self.price

    def get_ordered_images(self):
        """4 фото: сортировка по is_primary (главное первым), затем position."""
        return self.images.order_by('-is_primary', 'position', 'id')

    @property
    def main_image_url(self):
        """Главное фото (для превью)."""
        img = self.images.filter(is_primary=True).first()
        if img:
            return img.image_path
        first = self.images.order_by('position', 'id').first()
        return first.image_path if first else (self.cover_image_path or '')


# ==== Фото карточки курса (4 штуки, одно главное) ====
class CourseImage(models.Model):
    MAX_IMAGES_PER_COURSE = 4
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='images', db_column='course_id')
    image_path = models.CharField(max_length=500, verbose_name='Путь/URL изображения')
    is_primary = models.BooleanField(default=False, verbose_name='Главное фото')
    position = models.PositiveSmallIntegerField(default=0, help_text='0–3 для 4 фото')

    class Meta:
        db_table = 'course_image'
        ordering = ['-is_primary', 'position', 'id']

    def clean(self):
        if self.course_id and self.course.pk:
            others = self.course.images.exclude(pk=self.pk)
            if others.count() >= self.MAX_IMAGES_PER_COURSE:
                raise ValidationError(f'У курса может быть не более {self.MAX_IMAGES_PER_COURSE} фото.')

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_primary:
            CourseImage.objects.filter(course=self.course, is_primary=True).exclude(pk=self.pk).update(is_primary=False)


# ==== Страница контента курса = одно модальное окно (кнопка «плюс» добавляет новое поле) ====
# Состав курса: PDF-страница, ссылка YouTube, ссылка Rutube, PowerPoint, Word (docx). В купленном курсе видео отображается как видео.
class CourseContentPage(models.Model):
    CONTENT_TYPES = (
        ('pdf_page', 'Страница PDF'),
        ('youtube', 'YouTube (видео)'),
        ('rutube', 'Rutube (видео)'),
        ('pptx_slide', 'PowerPoint презентация'),
        ('docx', 'Документ Word'),
        ('video', 'Видео (файл)'),
    )
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='content_pages', db_column='course_id')
    sort_order = models.PositiveIntegerField(default=0)
    content_type = models.CharField(max_length=20, choices=CONTENT_TYPES)
    file_path = models.CharField(
        max_length=500,
        help_text='Путь к файлу (PDF/PPTX/DOCX) или ссылка (для YouTube/Rutube)'
    )
    title = models.CharField(max_length=255, blank=True, null=True)
    page_number = models.PositiveIntegerField(blank=True, null=True, help_text='Номер страницы PDF или слайда (для файлов)')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'course_content_page'
        ordering = ['sort_order']


# ==== Урок курса (новая логика: курс → уроки → страницы, как GetCourse) ====
class Lesson(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='lessons', db_column='course_id')
    sort_order = models.PositiveIntegerField(default=0)
    title = models.CharField(max_length=255, blank=True, null=True, verbose_name='Название урока')

    class Meta:
        db_table = 'lesson'
        ordering = ['sort_order', 'id']

    def __str__(self):
        return self.title or f'Урок {self.sort_order}'


# ==== Страница урока: картинка ИЛИ видео ИЛИ PDF-страница + текст. До 10 страниц на урок. ====
class LessonPage(models.Model):
    PAGE_TYPES = (
        ('image', 'Изображение'),
        ('video', 'Видео (YouTube/Rutube/ссылка)'),
        ('pdf_page', 'Страница PDF'),
    )
    MAX_PAGES_PER_LESSON = 10
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='pages', db_column='lesson_id')
    sort_order = models.PositiveSmallIntegerField(default=0)  # 1–10
    page_type = models.CharField(max_length=20, choices=PAGE_TYPES, default='image')
    file_path = models.CharField(max_length=500, blank=True, null=True)  # URL или путь к файлу
    page_number = models.PositiveSmallIntegerField(blank=True, null=True)  # для PDF — начальная страница (или одна страница)
    page_number_end = models.PositiveSmallIntegerField(blank=True, null=True)  # для PDF — конечная страница диапазона (пусто = одна страница)
    text = models.TextField(blank=True, null=True, verbose_name='Текст страницы')

    class Meta:
        db_table = 'lesson_page'
        ordering = ['sort_order', 'id']

    def get_embed_url(self):
        """Для видео: YouTube или Rutube embed URL; иначе file_path. Поддержка вставки кода iframe."""
        if self.page_type != 'video' or not self.file_path:
            return self.file_path or ''
        import re
        path = (self.file_path or '').strip()
        # Если вставлен код iframe — извлечь src
        if '<iframe' in path.lower() and 'src=' in path.lower():
            m = re.search(r'src\s*=\s*["\']([^"\']+)["\']', path, re.I)
            if m:
                path = m.group(1).strip()
        # Rutube: уже embed или обычная ссылка на видео
        if 'rutube.ru' in path:
            if '/play/embed/' in path:
                return path.split('?')[0].rstrip('/') + '/'  # как в примере пользователя
            m = re.search(r'rutube\.ru/(?:video/)?([a-f0-9]{32})', path, re.I)
            if m:
                return f'https://rutube.ru/play/embed/{m.group(1)}/'
            return path
        # YouTube
        m = re.search(r'(?:v=|\/)([a-zA-Z0-9_-]{11})', path)
        return f'https://www.youtube.com/embed/{m.group(1)}' if m else path


# ==== Покупка курса (доступ пользователя к курсу) ====
class CoursePurchase(models.Model):
    STATUSES = (('pending', 'Ожидает'), ('paid', 'Оплачен'), ('refunded', 'Возврат'), ('cancelled', 'Отменён'))
    PAYMENT_METHODS = (('card', 'Банковская карта'), ('sbp', 'СБП'), ('balance', 'Баланс'))
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_column='user_id')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, db_column='course_id')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=30, choices=STATUSES, default='pending')
    payment_method = models.CharField(max_length=50, blank=True, null=True, choices=PAYMENT_METHODS)
    promo_code = models.ForeignKey('Promotion', on_delete=models.SET_NULL, null=True, blank=True, db_column='promo_code_id')
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True, verbose_name='Переведён в архив (просмотр до конца + опрос + отзыв)')

    class Meta:
        db_table = 'course_purchase'

    @property
    def is_archived(self):
        """Курс в архиве: пройден до конца, есть опрос и отзыв."""
        return self.completed_at is not None

    def all_content_viewed(self):
        """Пользователь долистал до конца (все страницы контента просмотрены)."""
        total_pages = self.course.content_pages.count()
        if total_pages == 0:
            return True
        viewed_count = self.content_views.count()
        return viewed_count >= total_pages

    def has_survey(self):
        return CourseSurvey.objects.filter(course_purchase=self).exists()

    def has_review(self):
        return CourseReview.objects.filter(course_purchase=self).exists()

    def can_mark_archived(self):
        """Можно перевести в архив только после: все страницы + опрос + отзыв."""
        return self.all_content_viewed() and self.has_survey() and self.has_review()

    def mark_completed_if_ready(self):
        """Если все условия выполнены — ставит completed_at (архив)."""
        if self.completed_at is None and self.can_mark_archived():
            from django.utils import timezone
            self.completed_at = timezone.now()
            self.save(update_fields=['completed_at'])
            return True
        return False

    def is_lesson_completed(self, lesson):
        """Пройден ли урок по новой логике (LessonCompletion)."""
        return self.lesson_completions.filter(lesson=lesson).exists()


# ==== Прохождение урока: пройден + понравился ли + отзыв + комментарий админа ====
class LessonCompletion(models.Model):
    course_purchase = models.ForeignKey(
        CoursePurchase, on_delete=models.CASCADE, related_name='lesson_completions', db_column='course_purchase_id'
    )
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='completions', db_column='lesson_id')
    completed_at = models.DateTimeField(auto_now_add=True)
    liked = models.BooleanField(null=True, blank=True, verbose_name='Понравился урок (👍/👎)')
    review_text = models.TextField(blank=True, null=True, verbose_name='Отзыв пользователя')
    admin_comment = models.TextField(blank=True, null=True, verbose_name='Комментарий администратора')
    admin_comment_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'lesson_completion'
        unique_together = ('course_purchase', 'lesson')


# ==== Уведомления пользователю (в т.ч. комментарий админа к отзыву) ====
class UserNotification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications', db_column='user_id')
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(blank=True, null=True)
    lesson_completion = models.ForeignKey(
        LessonCompletion, on_delete=models.SET_NULL, null=True, blank=True, related_name='notifications',
        db_column='lesson_completion_id'
    )

    class Meta:
        db_table = 'user_notification'
        ordering = ['-created_at']


# ==== Просмотр страницы контента (учёт «долистал до конца») ====
class CourseContentView(models.Model):
    course_purchase = models.ForeignKey(
        CoursePurchase, on_delete=models.CASCADE, related_name='content_views', db_column='course_purchase_id'
    )
    content_page = models.ForeignKey(
        CourseContentPage, on_delete=models.CASCADE, db_column='course_content_page_id'
    )
    viewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'course_content_view'
        unique_together = ('course_purchase', 'content_page')


# ==== Опрос в конце курса (3НФ: course_id, user_id выводимы из course_purchase_id) ====
class CourseSurvey(models.Model):
    course_purchase = models.OneToOneField(CoursePurchase, on_delete=models.CASCADE, db_column='course_purchase_id')
    answers = models.JSONField(default=dict)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'course_survey'

    @property
    def course(self):
        return self.course_purchase.course if getattr(self, 'course_purchase_id', None) else None

    @property
    def user(self):
        return self.course_purchase.user if getattr(self, 'course_purchase_id', None) else None


# ==== Отзыв о курсе ====
class CourseReview(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, db_column='course_id')
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_column='user_id')
    course_purchase = models.ForeignKey(CoursePurchase, on_delete=models.SET_NULL, null=True, blank=True, db_column='course_purchase_id')
    rating = models.PositiveSmallIntegerField()
    review_text = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'course_review'


# ==== Заявление на возврат курса ====
class CourseRefundRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'На рассмотрении'),
        ('approved', 'Одобрен'),
        ('rejected', 'Отклонён'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_column='user_id')
    course_purchase = models.ForeignKey(
        CoursePurchase, on_delete=models.CASCADE, related_name='refund_requests', db_column='course_purchase_id'
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(blank=True, null=True)
    processed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='processed_refunds', db_column='processed_by_id'
    )

    class Meta:
        db_table = 'course_refund_request'
        ordering = ['-created_at']

    def __str__(self):
        return f"REF-{self.id:05d} ({self.user.username}, {self.course_purchase.course.title})"

    @property
    def refund_number(self):
        return f"REF-{self.id:05d}"


# ==== Избранное (курсы) ====
class CourseFavorite(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_column='user_id')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, db_column='course_id')
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'course_favorite'
        unique_together = ('user', 'course')


# ==== Корзина (курсы как товары) ====
class Cart(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_column='user_id')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cart'

    def total_price(self):
        try:
            total = Decimal('0.00')
            for item in self.items.all():
                if item.unit_price and item.quantity:
                    try:
                        unit_price = Decimal(str(item.unit_price))
                        quantity = int(item.quantity)
                        total += unit_price * quantity
                    except (ValueError, TypeError, InvalidOperation):
                        continue
            return total
        except Exception:
            return Decimal('0.00')

    def __str__(self):
        return f"Корзина {self.user.username}"

class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items', db_column='cart_id')
    course = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True, blank=True, db_column='course_id')
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = 'cartitem'

    def subtotal(self):
        try:
            unit_price = Decimal(str(self.unit_price)) if self.unit_price else Decimal('0.00')
            quantity = int(self.quantity) if self.quantity else 0
            return unit_price * quantity
        except (ValueError, TypeError, InvalidOperation):
            return Decimal('0.00')

    def __str__(self):
        return f"{self.course} x {self.quantity}"


# ==== Заказы ====
class Order(models.Model):
    ORDER_STATUSES = [
        ('processing', 'В обработке'),
        ('paid', 'Оплачен'),
        ('shipped', 'Отправлен'),
        ('delivered', 'Доставлен'),
        ('cancelled', 'Отменен'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, db_column='user_id')
    address = models.ForeignKey(UserAddress, on_delete=models.SET_NULL, null=True, blank=True, db_column='address_id')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    delivery_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name='Стоимость доставки')
    created_at = models.DateTimeField(auto_now_add=True)
    order_status = models.CharField(max_length=50, default='processing', choices=ORDER_STATUSES)
    promo_code = models.ForeignKey('Promotion', on_delete=models.SET_NULL, null=True, blank=True, db_column='promo_code_id')
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paid_from_balance = models.BooleanField(default=False)
    can_be_cancelled = models.BooleanField(default=True)
    vat_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('20.00'))
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('13.00'), verbose_name='Налог на прибыль (%)')

    class Meta:
        db_table = 'order'

    @property
    def vat_amount(self):
        """3НФ: выводится из total_amount, vat_rate, tax_rate."""
        total = self.total_amount or Decimal('0')
        vat_r = self.vat_rate or Decimal('0')
        tax_r = self.tax_rate or Decimal('0')
        pre_vat = total / ((Decimal('1') + vat_r / Decimal('100')) * (Decimal('1') + tax_r / Decimal('100')))
        return (pre_vat * vat_r / Decimal('100')).quantize(Decimal('0.01'))

    @property
    def tax_amount(self):
        """3НФ: выводится из total_amount и ставок (налог от суммы с НДС)."""
        total = self.total_amount or Decimal('0')
        vat_r = self.vat_rate or Decimal('0')
        tax_r = self.tax_rate or Decimal('0')
        pre_vat = total / ((Decimal('1') + vat_r / Decimal('100')) * (Decimal('1') + tax_r / Decimal('100')))
        amount_after_vat = (pre_vat * (Decimal('1') + vat_r / Decimal('100'))).quantize(Decimal('0.01'))
        return (amount_after_vat * tax_r / Decimal('100')).quantize(Decimal('0.01'))

    def __str__(self):
        return f"Order #{self.id}"
    
    def can_cancel(self):
        return self.can_be_cancelled and self.order_status in ['processing', 'paid']
    
    def clean(self):
        from django.core.exceptions import ValidationError
        if self.pk and self.items.count() == 0:
            raise ValidationError('Заказ не может быть без позиций (курсов).')

    def save(self, *args, **kwargs):
        is_update = self.pk and kwargs.get('update_fields') is not None
        if is_update and self.items.count() == 0:
            raise ValueError(f'Невозможно обновить заказ #{self.id} без позиций.')
        return super().save(*args, **kwargs)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items', db_column='order_id')
    course = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True, blank=True, db_column='course_id')
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = 'orderitem'


# ==== Платежи ====
class Payment(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, db_column='order_id')
    payment_method = models.CharField(max_length=50)
    payment_amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_status = models.CharField(max_length=50)
    paid_at = models.DateTimeField(blank=True, null=True)
    saved_payment_method = models.ForeignKey('SavedPaymentMethod', on_delete=models.SET_NULL, null=True, blank=True, db_column='saved_payment_method_id')
    promo_code = models.ForeignKey('Promotion', on_delete=models.SET_NULL, null=True, blank=True, db_column='promo_code_id')

    class Meta:
        db_table = 'payment'

# ==== Сохраненные способы оплаты ====
class SavedPaymentMethod(models.Model):
    """
    Сохраненные способы оплаты с шифрованием чувствительных данных.
    Номера карт и данные держателя автоматически шифруются в БД.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_payment_methods', db_column='user_id')
    # Номер карты будет храниться в зашифрованном виде
    # Используем TextField для хранения зашифрованных данных (они длиннее)
    card_number = models.TextField(max_length=500)  # Увеличено для хранения зашифрованных данных
    card_holder_name = models.CharField(max_length=100)
    expiry_month = models.CharField(max_length=2)
    expiry_year = models.CharField(max_length=4)
    card_type = models.CharField(max_length=20, blank=True, null=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    class Meta:
        db_table = 'savedpaymentmethod'
        ordering = ['-is_default', '-created_at']
    
    def __str__(self):
        return f"{self.card_type or 'Card'} ****{self.get_last_four_digits()}"
    
    def get_last_four_digits(self):
        """Получает последние 4 цифры номера карты (расшифровывает при необходимости)."""
        from .encryption import DataEncryption
        from django.conf import settings
        
        card_num = self.card_number
        if getattr(settings, 'ENABLE_DATA_ENCRYPTION', True):
            try:
                card_num = DataEncryption.decrypt_field(card_num)
            except:
                pass
        
        if card_num and len(card_num) >= 4:
            return card_num[-4:]
        return "****"
    
    def mask_card_number(self):
        """Возвращает замаскированный номер карты."""
        last_four = self.get_last_four_digits()
        if last_four and last_four != "****":
            return f"**** **** **** {last_four}"
        return "**** **** **** ****"
    
    def get_card_number(self):
        """Получает расшифрованный номер карты."""
        from .encryption import DataEncryption
        from django.conf import settings
        
        if getattr(settings, 'ENABLE_DATA_ENCRYPTION', True):
            try:
                return DataEncryption.decrypt_field(self.card_number)
            except:
                return self.card_number
        return self.card_number
    
    def set_card_number(self, value):
        """Устанавливает номер карты с автоматическим шифрованием."""
        from .encryption import DataEncryption
        from django.conf import settings
        
        if value:
            if getattr(settings, 'ENABLE_DATA_ENCRYPTION', True):
                self.card_number = DataEncryption.encrypt_field(value)
            else:
                self.card_number = value
    
    def save(self, *args, **kwargs):
        if self.balance < 0:
            raise ValueError("Баланс карты не может быть отрицательным")
        
        # Шифруем номер карты перед сохранением, если он еще не зашифрован
        from .encryption import DataEncryption
        from django.conf import settings
        
        if getattr(settings, 'ENABLE_DATA_ENCRYPTION', True) and self.card_number:
            # Проверяем, не зашифрован ли уже номер карты
            try:
                # Пытаемся расшифровать - если получается, значит уже зашифрован
                DataEncryption.decrypt_field(self.card_number)
            except:
                # Не зашифрован - шифруем
                self.card_number = DataEncryption.encrypt_field(self.card_number)
        
        super().save(*args, **kwargs)

# ==== Транзакции по картам ====
class CardTransaction(models.Model):
    TRANSACTION_TYPES = [
        ('deposit', 'Пополнение баланса'),
        ('withdrawal', 'Вывод на карту'),
    ]
    
    saved_payment_method = models.ForeignKey(SavedPaymentMethod, on_delete=models.CASCADE, related_name='transactions', db_column='saved_payment_method_id')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, default='completed')
    
    class Meta:
        db_table = 'cardtransaction'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.amount} ₽ ({self.saved_payment_method.mask_card_number()})"


# ==== Промоакции ====
class Promotion(models.Model):
    promo_code = models.CharField(max_length=50, unique=True)
    promo_description = models.TextField(blank=True, null=True)
    discount = models.DecimalField(max_digits=5, decimal_places=2)
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'promotion'

    def __str__(self):
        return self.promo_code


class PromoUsage(models.Model):
    """Использование промокода (по заказу или по покупке курса)"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_column='user_id')
    promotion = models.ForeignKey(Promotion, on_delete=models.CASCADE, db_column='promotion_id')
    order = models.ForeignKey('Order', on_delete=models.SET_NULL, null=True, blank=True, db_column='order_id')
    course_purchase = models.ForeignKey(CoursePurchase, on_delete=models.SET_NULL, null=True, blank=True, db_column='course_purchase_id')
    used_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'promo_usage'
        unique_together = [['user', 'promotion']]

    def __str__(self):
        return f"{self.user.username} - {self.promotion.promo_code}"


# ==== Поддержка ====
class SupportTicket(models.Model):
    TICKET_STATUS_CHOICES = [
        ('new', 'Новое'),
        ('in_progress', 'В работе'),
        ('resolved', 'Решено'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='support_tickets', db_column='user_id')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_tickets', verbose_name='Ответственный менеджер', db_column='assigned_to_id')
    subject = models.CharField(max_length=200)
    message_text = models.TextField()
    response_text = models.TextField(blank=True, null=True)
    ticket_status = models.CharField(max_length=50, choices=TICKET_STATUS_CHOICES, default='new', verbose_name='Статус')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'supportticket'


# ==== Логи активности ====
class DatabaseBackup(models.Model):
    BACKUP_SCHEDULE_CHOICES = [
        ('now', 'Прямо сейчас'),
        ('weekly', 'Каждую неделю'),
        ('monthly', 'Раз в месяц'),
        ('yearly', 'Раз в год'),
    ]
    
    backup_file = models.FileField(upload_to='backups/', null=True, blank=True)
    backup_name = models.CharField(max_length=255, verbose_name='Название бэкапа')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name='Создан пользователем', db_column='created_by_id')
    file_size = models.BigIntegerField(default=0, verbose_name='Размер файла (байт)')
    schedule = models.CharField(max_length=20, choices=BACKUP_SCHEDULE_CHOICES, default='now', verbose_name='Расписание')
    notes = models.TextField(blank=True, null=True, verbose_name='Примечания')
    is_automatic = models.BooleanField(default=False, verbose_name='Автоматический бэкап')
    
    class Meta:
        db_table = 'databasebackup'
        verbose_name = 'Бэкап базы данных'
        verbose_name_plural = 'Бэкапы базы данных'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.backup_name} ({self.created_at.strftime('%d.%m.%Y %H:%M')})"
    
    def get_file_size_mb(self):
        if self.file_size:
            return round(self.file_size / (1024 * 1024), 2)
        return 0

class ActivityLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, db_column='user_id')
    action_type = models.CharField(max_length=50)
    target_object = models.CharField(max_length=100)
    action_description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        db_table = 'activitylog'

# ==== Транзакции баланса ====
class BalanceTransaction(models.Model):
    TRANSACTION_TYPES = [
        ('deposit', 'Пополнение'),
        ('withdrawal', 'Вывод'),
        ('order_payment', 'Оплата заказа'),
        ('order_refund', 'Возврат заказа'),
        ('course_payment', 'Оплата курса'),
        ('course_refund', 'Возврат за курс'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='balance_transactions', db_column='user_id')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True, null=True)
    order = models.ForeignKey('Order', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions', db_column='order_id')
    course_purchase = models.ForeignKey(CoursePurchase, on_delete=models.SET_NULL, null=True, blank=True, db_column='course_purchase_id')
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, default='completed')
    
    class Meta:
        db_table = 'balancetransaction'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.amount} ₽ ({self.user.username})"

# ==== Чеки ====
class ReceiptConfig(models.Model):
    company_name = models.CharField(max_length=255, default='ООО «MPTCOURSE»')
    company_inn = models.CharField(max_length=20, default='7700000000')
    company_address = models.CharField(max_length=255, default='г. Москва, ул. Примерная, д. 1')
    cashier_name = models.CharField(max_length=255, default='Кассир')
    shift_number = models.CharField(max_length=50, default='1')
    kkt_rn = models.CharField(max_length=32, default='0000000000000000')
    kkt_sn = models.CharField(max_length=32, default='1234567890')
    fn_number = models.CharField(max_length=32, default='0000000000000000')
    site_fns = models.CharField(max_length=100, default='www.nalog.ru')

    class Meta:
        db_table = 'receiptconfig'
        verbose_name = 'Настройки чека'
        verbose_name_plural = 'Настройки чеков'

    def __str__(self):
        return 'Настройки чека'


class Receipt(models.Model):
    STATUS_CHOICES = [
        ('executed', 'Исполнен'),
        ('annulled', 'Аннулирован'),
    ]
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='receipts', db_column='user_id')
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='receipt', db_column='order_id')
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='executed')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name='Сумма товаров')
    delivery_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name='Доставка')
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name='Скидка')
    vat_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('20.00'))
    payment_method = models.CharField(max_length=20, default='cash')
    number = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        db_table = 'receipt'
        ordering = ['-created_at']

    @property
    def vat_amount(self):
        """3НФ: выводится из subtotal, delivery_cost, discount_amount, vat_rate."""
        base = (self.subtotal or Decimal('0')) + (self.delivery_cost or Decimal('0')) - (self.discount_amount or Decimal('0'))
        return (base * (self.vat_rate or Decimal('0')) / Decimal('100')).quantize(Decimal('0.01'))

    def __str__(self):
        return f"Чек #{self.id} по заказу #{self.order_id}"


class ReceiptItem(models.Model):
    receipt = models.ForeignKey(Receipt, on_delete=models.CASCADE, related_name='items', db_column='receipt_id')
    course = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True, blank=True, db_column='course_id')
    line_description = models.CharField(max_length=255, blank=True, null=True)
    article = models.CharField(max_length=100, blank=True, null=True)
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = 'receiptitem'

    @property
    def product_name(self):
        """3НФ: из course или line_description."""
        if self.course_id and getattr(self, 'course', None):
            return self.course.title
        return self.line_description or '—'

    @property
    def line_total(self):
        return (Decimal(str(self.quantity or 0)) * (self.unit_price or Decimal('0'))).quantize(Decimal('0.01'))

    @property
    def vat_amount(self):
        """Выводится из line_total и vat_rate чека."""
        try:
            r = self.receipt
            vat_rate = r.vat_rate if r else Decimal('20.00')
        except Exception:
            vat_rate = Decimal('20.00')
        return (self.line_total * vat_rate / Decimal('100')).quantize(Decimal('0.01'))

    def __str__(self):
        return f"{self.product_name} x {self.quantity}"


# ==== Счет организации ====
class OrganizationAccount(models.Model):
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name='Баланс')
    tax_reserve = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name='Резерв на налоги (13%)')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'organizationaccount'
        verbose_name = 'Счет организации'
        verbose_name_plural = 'Счет организации'
        constraints = [
            models.CheckConstraint(
                check=models.Q(balance__gte=0),
                name='org_account_balance_non_negative'
            ),
            models.CheckConstraint(
                check=models.Q(tax_reserve__gte=0),
                name='org_account_tax_reserve_non_negative'
            ),
        ]
    
    def __str__(self):
        return f"Счет организации: {self.balance} ₽ (Налог: {self.tax_reserve} ₽)"
    
    @classmethod
    def get_account(cls):
        try:
            account, created = cls.objects.get_or_create(
                pk=1,
                defaults={
                    'balance': Decimal('0.00'),
                    'tax_reserve': Decimal('0.00')
                }
            )
            return account
        except Exception:
            try:
                return cls.objects.get(pk=1)
            except cls.DoesNotExist:
                return cls.objects.create(
                    pk=1,
                    balance=Decimal('0.00'),
                    tax_reserve=Decimal('0.00')
                )
    
    def can_withdraw(self, amount):
        return self.balance >= amount
    
    def can_pay_tax(self, amount):
        return self.balance >= amount and self.tax_reserve >= amount


# ==== Транзакции счета организации ====
class OrganizationTransaction(models.Model):
    TRANSACTION_TYPES = [
        ('order_payment', 'Поступление от заказа'),
        ('order_refund', 'Возврат по отмене заказа'),
        ('course_payment', 'Поступление от курса'),
        ('course_refund', 'Возврат за курс'),
        ('tax_payment', 'Оплата налога'),
        ('withdrawal', 'Вывод на карту админа'),
    ]
    
    organization_account = models.ForeignKey(OrganizationAccount, on_delete=models.CASCADE, related_name='transactions', db_column='organization_account_id')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True, null=True)
    order = models.ForeignKey('Order', on_delete=models.SET_NULL, null=True, blank=True, related_name='org_transactions', db_column='order_id')
    course_purchase = models.ForeignKey(CoursePurchase, on_delete=models.SET_NULL, null=True, blank=True, db_column='course_purchase_id')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Создано пользователем', db_column='created_by_id')
    created_at = models.DateTimeField(auto_now_add=True)
    # Состояние счёта до и после транзакции (для отображения в истории)
    balance_before = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, db_column='balance_before')
    balance_after = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, db_column='balance_after')
    tax_reserve_before = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, db_column='tax_reserve_before')
    tax_reserve_after = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, db_column='tax_reserve_after')

    class Meta:
        db_table = 'organizationtransaction'
        ordering = ['-created_at']
        verbose_name = 'Транзакция счета организации'
        verbose_name_plural = 'Транзакции счета организации'
    
    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.amount} ₽ ({self.created_at.strftime('%d.%m.%Y %H:%M')})"


# ==== Настройки пользователя ====
class UserSettings(models.Model):
    """
    Настройки пользователя, хранящиеся на сервере.
    Включает тему, формат даты/чисел, размер страниц, сохраненные фильтры.
    """
    THEME_CHOICES = [
        ('light', 'Светлая'),
        ('dark', 'Темная'),
        ('auto', 'Автоматическая'),
    ]
    
    DATE_FORMAT_CHOICES = [
        ('DD.MM.YYYY', 'ДД.ММ.ГГГГ'),
        ('YYYY-MM-DD', 'ГГГГ-ММ-ДД'),
        ('MM/DD/YYYY', 'ММ/ДД/ГГГГ'),
        ('DD MMM YYYY', 'ДД МММ ГГГГ'),
    ]
    
    NUMBER_FORMAT_CHOICES = [
        ('ru', 'Русский (1 234,56)'),
        ('en', 'Английский (1,234.56)'),
        ('space', 'С пробелами (1 234.56)'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='settings', db_column='user_id')
    theme = models.CharField(max_length=10, choices=THEME_CHOICES, default='light', verbose_name='Тема')
    date_format = models.CharField(max_length=20, choices=DATE_FORMAT_CHOICES, default='DD.MM.YYYY', verbose_name='Формат даты')
    number_format = models.CharField(max_length=10, choices=NUMBER_FORMAT_CHOICES, default='ru', verbose_name='Формат чисел')
    page_size = models.IntegerField(default=20, verbose_name='Размер страницы', help_text='Количество элементов на странице')
    saved_filters = models.JSONField(default=dict, blank=True, null=True, verbose_name='Сохраненные фильтры')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'usersettings'
        verbose_name = 'Настройки пользователя'
        verbose_name_plural = 'Настройки пользователей'
    
    def __str__(self):
        return f"Настройки пользователя {self.user.username}"
    
    @classmethod
    def get_or_create_for_user(cls, user):
        """Получает или создает настройки для пользователя"""
        settings, created = cls.objects.get_or_create(
            user=user,
            defaults={
                'theme': 'light',
                'date_format': 'DD.MM.YYYY',
                'number_format': 'ru',
                'page_size': 20,
                'saved_filters': {}
            }
        )
        return settings
    
    def save(self, *args, **kwargs):
        """Переопределяем save для автоматического обновления updated_at"""
        from django.utils import timezone
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)
