-- =============================================================================
-- MPTCOURSE — полный скрипт БД для pgAdmin
-- =============================================================================
-- База данных: mptcourse
-- В pgAdmin: создать БД mptcourse (правый клик по Databases → Create → Database → mptcourse),
-- затем подключиться к ней, открыть Query Tool (F5), загрузить этот файл и выполнить (F5).
-- =============================================================================
-- Содержит: таблицы, индексы, 3 функции, 3 представления, 3 триггера, начальные данные.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Django: типы контента (перед auth_permission)
CREATE TABLE IF NOT EXISTS django_content_type (
    id SERIAL PRIMARY KEY,
    app_label VARCHAR(100) NOT NULL,
    model VARCHAR(100) NOT NULL,
    UNIQUE(app_label, model)
);

CREATE TABLE IF NOT EXISTS auth_user (
    id SERIAL PRIMARY KEY,
    password VARCHAR(128) NOT NULL,
    last_login TIMESTAMP WITH TIME ZONE,
    is_superuser BOOLEAN NOT NULL DEFAULT FALSE,
    username VARCHAR(150) NOT NULL UNIQUE,
    first_name VARCHAR(150) NOT NULL DEFAULT '',
    last_name VARCHAR(150) NOT NULL DEFAULT '',
    email VARCHAR(254) NOT NULL DEFAULT '',
    is_staff BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    date_joined TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS auth_group (
    id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS auth_permission (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    content_type_id INTEGER NOT NULL REFERENCES django_content_type(id) ON DELETE CASCADE,
    codename VARCHAR(100) NOT NULL,
    UNIQUE(content_type_id, codename)
);

CREATE TABLE IF NOT EXISTS auth_user_groups (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES auth_user(id) ON DELETE CASCADE,
    group_id INTEGER NOT NULL REFERENCES auth_group(id) ON DELETE CASCADE,
    UNIQUE(user_id, group_id)
);

CREATE TABLE IF NOT EXISTS auth_user_user_permissions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES auth_user(id) ON DELETE CASCADE,
    permission_id INTEGER NOT NULL REFERENCES auth_permission(id) ON DELETE CASCADE,
    UNIQUE(user_id, permission_id)
);

CREATE TABLE IF NOT EXISTS django_migrations (
    id SERIAL PRIMARY KEY,
    app VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    applied TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS django_session (
    session_key VARCHAR(40) PRIMARY KEY,
    session_data TEXT NOT NULL,
    expire_date TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE IF NOT EXISTS django_admin_log (
    id SERIAL PRIMARY KEY,
    action_time TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    object_id TEXT,
    object_repr VARCHAR(200) NOT NULL,
    action_flag SMALLINT NOT NULL CHECK (action_flag >= 0),
    change_message TEXT NOT NULL,
    content_type_id INTEGER REFERENCES django_content_type(id) ON DELETE SET NULL,
    user_id INTEGER NOT NULL REFERENCES auth_user(id) ON DELETE CASCADE
);

-- Роли
CREATE TABLE IF NOT EXISTS role (
    id BIGSERIAL PRIMARY KEY,
    role_name VARCHAR(50) NOT NULL UNIQUE
);

-- Промоакции (для скидок на курсы)
CREATE TABLE IF NOT EXISTS promotion (
    id BIGSERIAL PRIMARY KEY,
    promo_code VARCHAR(50) NOT NULL UNIQUE,
    promo_description TEXT,
    discount DECIMAL(5,2) NOT NULL CHECK (discount >= 0 AND discount <= 100),
    start_date DATE,
    end_date DATE,
    is_active BOOLEAN DEFAULT TRUE,
    CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date)
);

-- Профили пользователей (3НФ: full_name не храним — выводится из auth_user.first_name, last_name)
CREATE TABLE IF NOT EXISTS userprofile (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE REFERENCES auth_user(id) ON DELETE CASCADE,
    role_id BIGINT REFERENCES role(id) ON DELETE SET NULL,
    phone_number VARCHAR(50),
    birth_date DATE,
    user_status VARCHAR(50) DEFAULT 'active',
    registered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    balance DECIMAL(10,2) DEFAULT 0 CHECK (balance >= 0),
    secret_word VARCHAR(255)
);

-- Адреса пользователей
CREATE TABLE IF NOT EXISTS useraddress (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES auth_user(id) ON DELETE CASCADE,
    address_title VARCHAR(100),
    city_name VARCHAR(100) NOT NULL,
    street_name VARCHAR(100) NOT NULL,
    house_number VARCHAR(20) NOT NULL,
    apartment_number VARCHAR(20),
    postal_code VARCHAR(20) NOT NULL,
    is_primary BOOLEAN DEFAULT FALSE
);

-- Сохранённые способы оплаты
CREATE TABLE IF NOT EXISTS savedpaymentmethod (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES auth_user(id) ON DELETE CASCADE,
    card_number TEXT NOT NULL,
    card_holder_name VARCHAR(100) NOT NULL,
    expiry_month VARCHAR(2) NOT NULL,
    expiry_year VARCHAR(4) NOT NULL,
    card_type VARCHAR(20),
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    balance DECIMAL(10,2) DEFAULT 0 CHECK (balance >= 0)
);

-- Категории курсов
CREATE TABLE IF NOT EXISTS course_category (
    id BIGSERIAL PRIMARY KEY,
    category_name VARCHAR(100) NOT NULL,
    category_description TEXT,
    parent_id BIGINT REFERENCES course_category(id) ON DELETE SET NULL
);

-- Курсы
CREATE TABLE IF NOT EXISTS course (
    id BIGSERIAL PRIMARY KEY,
    category_id BIGINT REFERENCES course_category(id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL,
    slug VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    included_content TEXT,
    price DECIMAL(10,2) NOT NULL CHECK (price >= 0),
    discount DECIMAL(5,2) DEFAULT 0 CHECK (discount >= 0 AND discount <= 100),
    is_available BOOLEAN DEFAULT TRUE,
    added_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    cover_image_path VARCHAR(500)
);
COMMENT ON COLUMN course.included_content IS 'Что входит в состав курса (описание для карточки)';

-- Фото карточки курса: 4 штуки, одно главное (is_primary)
CREATE TABLE IF NOT EXISTS course_image (
    id BIGSERIAL PRIMARY KEY,
    course_id BIGINT NOT NULL REFERENCES course(id) ON DELETE CASCADE,
    image_path VARCHAR(500) NOT NULL,
    is_primary BOOLEAN DEFAULT FALSE,
    position SMALLINT NOT NULL DEFAULT 0 CHECK (position >= 0 AND position <= 3)
);
CREATE INDEX IF NOT EXISTS idx_course_image_course ON course_image(course_id);
COMMENT ON TABLE course_image IS 'До 4 фото на курс, одно помечается главным (is_primary)';

-- Страница контента курса = одно модальное окно. Состав: PDF-страница, YouTube, Rutube, PowerPoint, Word (docx). file_path = путь к файлу или URL (для youtube/rutube).
CREATE TABLE IF NOT EXISTS course_content_page (
    id BIGSERIAL PRIMARY KEY,
    course_id BIGINT NOT NULL REFERENCES course(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL DEFAULT 0 CHECK (sort_order >= 0),
    content_type VARCHAR(20) NOT NULL CHECK (content_type IN ('video', 'pdf_page', 'pptx_slide', 'youtube', 'rutube', 'docx')),
    file_path VARCHAR(500) NOT NULL,
    title VARCHAR(255),
    page_number INTEGER CHECK (page_number IS NULL OR page_number > 0),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Покупка курса (доступ пользователя к курсу)
CREATE TABLE IF NOT EXISTS course_purchase (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES auth_user(id) ON DELETE CASCADE,
    course_id BIGINT NOT NULL REFERENCES course(id) ON DELETE CASCADE,
    amount DECIMAL(10,2) NOT NULL CHECK (amount >= 0),
    paid_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(30) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'paid', 'refunded', 'cancelled')),
    payment_method VARCHAR(50),
    promo_code_id BIGINT REFERENCES promotion(id) ON DELETE SET NULL,
    discount_amount DECIMAL(10,2) DEFAULT 0 CHECK (discount_amount >= 0),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE
);
COMMENT ON COLUMN course_purchase.completed_at IS 'Когда курс переведён в архив: долистал до конца + опрос + отзыв';
COMMENT ON COLUMN course_purchase.payment_method IS 'card | sbp | balance';

-- Просмотр страницы контента (для учёта «долистал до конца»)
CREATE TABLE IF NOT EXISTS course_content_view (
    id BIGSERIAL PRIMARY KEY,
    course_purchase_id BIGINT NOT NULL REFERENCES course_purchase(id) ON DELETE CASCADE,
    course_content_page_id BIGINT NOT NULL REFERENCES course_content_page(id) ON DELETE CASCADE,
    viewed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(course_purchase_id, course_content_page_id)
);
CREATE INDEX IF NOT EXISTS idx_course_content_view_purchase ON course_content_view(course_purchase_id);

-- ========== Уроки курса (логика GetCourse: курс → уроки → страницы уроков) ==========
CREATE TABLE IF NOT EXISTS lesson (
    id BIGSERIAL PRIMARY KEY,
    course_id BIGINT NOT NULL REFERENCES course(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL DEFAULT 0 CHECK (sort_order >= 0),
    title VARCHAR(255)
);
CREATE INDEX IF NOT EXISTS idx_lesson_course ON lesson(course_id);

-- Страница урока: изображение, видео (YouTube/Rutube) или PDF-страница + текст. До 10 страниц на урок.
CREATE TABLE IF NOT EXISTS lesson_page (
    id BIGSERIAL PRIMARY KEY,
    lesson_id BIGINT NOT NULL REFERENCES lesson(id) ON DELETE CASCADE,
    sort_order SMALLINT NOT NULL DEFAULT 0 CHECK (sort_order >= 0),
    page_type VARCHAR(20) NOT NULL DEFAULT 'image' CHECK (page_type IN ('image', 'video', 'pdf_page')),
    file_path VARCHAR(500),
    page_number SMALLINT CHECK (page_number IS NULL OR page_number > 0),
    text TEXT
);
CREATE INDEX IF NOT EXISTS idx_lesson_page_lesson ON lesson_page(lesson_id);

-- Прохождение урока: пройден + понравился ли + отзыв + комментарий админа
CREATE TABLE IF NOT EXISTS lesson_completion (
    id BIGSERIAL PRIMARY KEY,
    course_purchase_id BIGINT NOT NULL REFERENCES course_purchase(id) ON DELETE CASCADE,
    lesson_id BIGINT NOT NULL REFERENCES lesson(id) ON DELETE CASCADE,
    completed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    liked BOOLEAN,
    review_text TEXT,
    admin_comment TEXT,
    admin_comment_at TIMESTAMP WITH TIME ZONE,
    UNIQUE(course_purchase_id, lesson_id)
);
CREATE INDEX IF NOT EXISTS idx_lesson_completion_purchase ON lesson_completion(course_purchase_id);
CREATE INDEX IF NOT EXISTS idx_lesson_completion_lesson ON lesson_completion(lesson_id);

-- Уведомления пользователю (в т.ч. комментарий админа к отзыву по уроку)
CREATE TABLE IF NOT EXISTS user_notification (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES auth_user(id) ON DELETE CASCADE,
    message TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    read_at TIMESTAMP WITH TIME ZONE,
    lesson_completion_id BIGINT REFERENCES lesson_completion(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_user_notification_user ON user_notification(user_id);
CREATE INDEX IF NOT EXISTS idx_user_notification_lesson_completion ON user_notification(lesson_completion_id);

-- Заявление на возврат средств за курс
CREATE TABLE IF NOT EXISTS course_refund_request (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES auth_user(id) ON DELETE CASCADE,
    course_purchase_id BIGINT NOT NULL REFERENCES course_purchase(id) ON DELETE CASCADE,
    amount DECIMAL(10,2) NOT NULL CHECK (amount >= 0),
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP WITH TIME ZONE,
    processed_by_id INTEGER REFERENCES auth_user(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_course_refund_request_user ON course_refund_request(user_id);
CREATE INDEX IF NOT EXISTS idx_course_refund_request_purchase ON course_refund_request(course_purchase_id);

-- Опросник в конце курса (5-балльная шкала), для аналитики (3НФ: course_id, user_id выводимы из course_purchase_id)
CREATE TABLE IF NOT EXISTS course_survey (
    id BIGSERIAL PRIMARY KEY,
    course_purchase_id BIGINT NOT NULL REFERENCES course_purchase(id) ON DELETE CASCADE,
    answers JSONB NOT NULL DEFAULT '{}',
    submitted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(course_purchase_id)
);

-- Отзыв о курсе (аналитика)
CREATE TABLE IF NOT EXISTS course_review (
    id BIGSERIAL PRIMARY KEY,
    course_id BIGINT NOT NULL REFERENCES course(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES auth_user(id) ON DELETE CASCADE,
    course_purchase_id BIGINT REFERENCES course_purchase(id) ON DELETE SET NULL,
    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
    review_text TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Избранные курсы (избранное — товары/курсы)
CREATE TABLE IF NOT EXISTS course_favorite (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES auth_user(id) ON DELETE CASCADE,
    course_id BIGINT NOT NULL REFERENCES course(id) ON DELETE CASCADE,
    added_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, course_id)
);

-- Корзина (курсы как товары)
CREATE TABLE IF NOT EXISTS cart (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES auth_user(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Элемент корзины (курс + количество, цена)
CREATE TABLE IF NOT EXISTS cartitem (
    id BIGSERIAL PRIMARY KEY,
    cart_id BIGINT NOT NULL REFERENCES cart(id) ON DELETE CASCADE,
    course_id BIGINT REFERENCES course(id) ON DELETE SET NULL,
    quantity INTEGER DEFAULT 1 CHECK (quantity > 0),
    unit_price DECIMAL(10,2) NOT NULL CHECK (unit_price >= 0)
);

-- Заказ (оплата корзины курсов) (3НФ: vat_amount, tax_amount выводимы из total_amount и ставок)
CREATE TABLE IF NOT EXISTS "order" (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES auth_user(id) ON DELETE SET NULL,
    address_id BIGINT REFERENCES useraddress(id) ON DELETE SET NULL,
    total_amount DECIMAL(10,2) NOT NULL CHECK (total_amount >= 0),
    delivery_cost DECIMAL(10,2) DEFAULT 0 CHECK (delivery_cost >= 0),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    order_status VARCHAR(50) DEFAULT 'processing'
        CHECK (order_status IN ('processing', 'paid', 'shipped', 'delivered', 'cancelled')),
    promo_code_id BIGINT REFERENCES promotion(id) ON DELETE SET NULL,
    discount_amount DECIMAL(10,2) DEFAULT 0 CHECK (discount_amount >= 0),
    paid_from_balance BOOLEAN DEFAULT FALSE,
    can_be_cancelled BOOLEAN DEFAULT TRUE,
    vat_rate DECIMAL(5,2) DEFAULT 20.00 CHECK (vat_rate >= 0),
    tax_rate DECIMAL(5,2) DEFAULT 13.00 CHECK (tax_rate >= 0)
);

-- Элемент заказа (курс в заказе)
CREATE TABLE IF NOT EXISTS orderitem (
    id BIGSERIAL PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES "order"(id) ON DELETE CASCADE,
    course_id BIGINT REFERENCES course(id) ON DELETE SET NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price DECIMAL(10,2) NOT NULL CHECK (unit_price >= 0)
);

-- Платеж по заказу
CREATE TABLE IF NOT EXISTS payment (
    id BIGSERIAL PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES "order"(id) ON DELETE CASCADE,
    payment_method VARCHAR(50) NOT NULL,
    payment_amount DECIMAL(10,2) NOT NULL CHECK (payment_amount >= 0),
    payment_status VARCHAR(50) NOT NULL,
    paid_at TIMESTAMP WITH TIME ZONE,
    saved_payment_method_id BIGINT REFERENCES savedpaymentmethod(id) ON DELETE SET NULL,
    promo_code_id BIGINT REFERENCES promotion(id) ON DELETE SET NULL
);

-- Чек по заказу (3НФ: vat_amount выводим из subtotal, delivery_cost, discount_amount, vat_rate)
CREATE TABLE IF NOT EXISTS receipt (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES auth_user(id) ON DELETE SET NULL,
    order_id BIGINT NOT NULL UNIQUE REFERENCES "order"(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'executed' CHECK (status IN ('executed', 'annulled')),
    total_amount DECIMAL(10,2) DEFAULT 0 CHECK (total_amount >= 0),
    subtotal DECIMAL(10,2) DEFAULT 0 CHECK (subtotal >= 0),
    delivery_cost DECIMAL(10,2) DEFAULT 0 CHECK (delivery_cost >= 0),
    discount_amount DECIMAL(10,2) DEFAULT 0 CHECK (discount_amount >= 0),
    vat_rate DECIMAL(5,2) DEFAULT 20.00 CHECK (vat_rate >= 0),
    payment_method VARCHAR(20) DEFAULT 'cash',
    number VARCHAR(50)
);

-- Строка чека (3НФ: product_name из course_id; line_total=quantity*unit_price; vat_amount выводим)
CREATE TABLE IF NOT EXISTS receiptitem (
    id BIGSERIAL PRIMARY KEY,
    receipt_id BIGINT NOT NULL REFERENCES receipt(id) ON DELETE CASCADE,
    course_id BIGINT REFERENCES course(id) ON DELETE SET NULL,
    line_description VARCHAR(255),
    article VARCHAR(100),
    quantity INTEGER DEFAULT 1 CHECK (quantity > 0),
    unit_price DECIMAL(10,2) NOT NULL CHECK (unit_price >= 0)
);

-- Использование промокода (по заказу или по покупке курса)
CREATE TABLE IF NOT EXISTS promo_usage (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES auth_user(id) ON DELETE CASCADE,
    promotion_id BIGINT NOT NULL REFERENCES promotion(id) ON DELETE CASCADE,
    order_id BIGINT REFERENCES "order"(id) ON DELETE SET NULL,
    course_purchase_id BIGINT REFERENCES course_purchase(id) ON DELETE SET NULL,
    used_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, promotion_id)
);

-- Транзакции по картам
CREATE TABLE IF NOT EXISTS cardtransaction (
    id BIGSERIAL PRIMARY KEY,
    saved_payment_method_id BIGINT NOT NULL REFERENCES savedpaymentmethod(id) ON DELETE CASCADE,
    transaction_type VARCHAR(20) NOT NULL CHECK (transaction_type IN ('deposit', 'withdrawal')),
    amount DECIMAL(10,2) NOT NULL CHECK (amount >= 0),
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'completed'
);

-- Транзакции баланса (3НФ: balance_before, balance_after выводимы из истории транзакций)
CREATE TABLE IF NOT EXISTS balancetransaction (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES auth_user(id) ON DELETE CASCADE,
    transaction_type VARCHAR(20) NOT NULL CHECK (transaction_type IN ('deposit', 'withdrawal', 'order_payment', 'order_refund', 'course_payment', 'course_refund')),
    amount DECIMAL(10,2) NOT NULL CHECK (amount >= 0),
    description TEXT,
    order_id BIGINT REFERENCES "order"(id) ON DELETE SET NULL,
    course_purchase_id BIGINT REFERENCES course_purchase(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'completed'
);

-- Поддержка
CREATE TABLE IF NOT EXISTS supportticket (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES auth_user(id) ON DELETE SET NULL,
    assigned_to_id INTEGER REFERENCES auth_user(id) ON DELETE SET NULL,
    subject VARCHAR(200) NOT NULL,
    message_text TEXT NOT NULL,
    response_text TEXT,
    ticket_status VARCHAR(50) DEFAULT 'new',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Логи активности (аудит)
CREATE TABLE IF NOT EXISTS activitylog (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES auth_user(id) ON DELETE SET NULL,
    action_type VARCHAR(50) NOT NULL,
    target_object VARCHAR(100) NOT NULL,
    action_description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    ip_address VARCHAR(50)
);

-- Бэкапы БД
CREATE TABLE IF NOT EXISTS databasebackup (
    id BIGSERIAL PRIMARY KEY,
    backup_file VARCHAR(100),
    backup_name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by_id INTEGER REFERENCES auth_user(id) ON DELETE SET NULL,
    file_size BIGINT DEFAULT 0 CHECK (file_size >= 0),
    schedule VARCHAR(20) DEFAULT 'now' CHECK (schedule IN ('now', 'weekly', 'monthly', 'yearly')),
    notes TEXT,
    is_automatic BOOLEAN DEFAULT FALSE
);

-- Счёт организации
CREATE TABLE IF NOT EXISTS organizationaccount (
    id BIGSERIAL PRIMARY KEY,
    balance DECIMAL(12,2) DEFAULT 0 CHECK (balance >= 0),
    tax_reserve DECIMAL(12,2) DEFAULT 0 CHECK (tax_reserve >= 0),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Транзакции счёта организации (3НФ: balance_*, tax_reserve_* выводимы из истории)
CREATE TABLE IF NOT EXISTS organizationtransaction (
    id BIGSERIAL PRIMARY KEY,
    organization_account_id BIGINT NOT NULL REFERENCES organizationaccount(id) ON DELETE CASCADE,
    transaction_type VARCHAR(20) NOT NULL CHECK (transaction_type IN ('order_payment', 'order_refund', 'course_payment', 'course_refund', 'tax_payment', 'withdrawal')),
    amount DECIMAL(10,2) NOT NULL CHECK (amount >= 0),
    description TEXT,
    order_id BIGINT REFERENCES "order"(id) ON DELETE SET NULL,
    course_purchase_id BIGINT REFERENCES course_purchase(id) ON DELETE SET NULL,
    created_by_id INTEGER REFERENCES auth_user(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Настройки чеков (MPTCOURSE)
CREATE TABLE IF NOT EXISTS receiptconfig (
    id BIGSERIAL PRIMARY KEY,
    company_name VARCHAR(255) DEFAULT 'ООО «MPTCOURSE»',
    company_inn VARCHAR(20) DEFAULT '7700000000',
    company_address VARCHAR(255) DEFAULT 'г. Москва, ул. Примерная, д. 1',
    cashier_name VARCHAR(255) DEFAULT 'Кассир',
    shift_number VARCHAR(50) DEFAULT '1',
    kkt_rn VARCHAR(32) DEFAULT '0000000000000000',
    kkt_sn VARCHAR(32) DEFAULT '1234567890',
    fn_number VARCHAR(32) DEFAULT '0000000000000000',
    site_fns VARCHAR(100) DEFAULT 'www.nalog.ru'
);

-- Настройки пользователя
CREATE TABLE IF NOT EXISTS usersettings (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE REFERENCES auth_user(id) ON DELETE CASCADE,
    theme VARCHAR(10) DEFAULT 'light' CHECK (theme IN ('light', 'dark', 'auto')),
    date_format VARCHAR(20) DEFAULT 'DD.MM.YYYY' CHECK (date_format IN ('DD.MM.YYYY', 'YYYY-MM-DD', 'MM/DD/YYYY', 'DD MMM YYYY')),
    number_format VARCHAR(10) DEFAULT 'ru' CHECK (number_format IN ('ru', 'en', 'space')),
    page_size INTEGER DEFAULT 20 CHECK (page_size > 0),
    saved_filters JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Индексы
CREATE INDEX IF NOT EXISTS idx_course_category_parent ON course_category(parent_id);
CREATE INDEX IF NOT EXISTS idx_course_category ON course(category_id);
CREATE INDEX IF NOT EXISTS idx_course_slug ON course(slug);
CREATE INDEX IF NOT EXISTS idx_course_content_course ON course_content_page(course_id);
CREATE INDEX IF NOT EXISTS idx_course_image_course ON course_image(course_id);
CREATE INDEX IF NOT EXISTS idx_course_purchase_user ON course_purchase(user_id);
CREATE INDEX IF NOT EXISTS idx_course_purchase_course ON course_purchase(course_id);
CREATE INDEX IF NOT EXISTS idx_course_purchase_status ON course_purchase(status);
CREATE INDEX IF NOT EXISTS idx_course_purchase_completed ON course_purchase(completed_at);
CREATE INDEX IF NOT EXISTS idx_course_survey_purchase ON course_survey(course_purchase_id);
CREATE INDEX IF NOT EXISTS idx_course_review_course ON course_review(course_id);
CREATE INDEX IF NOT EXISTS idx_course_favorite_user ON course_favorite(user_id);
CREATE INDEX IF NOT EXISTS idx_cart_user ON cart(user_id);
CREATE INDEX IF NOT EXISTS idx_cartitem_cart ON cartitem(cart_id);
CREATE INDEX IF NOT EXISTS idx_cartitem_course ON cartitem(course_id);
CREATE INDEX IF NOT EXISTS idx_order_user ON "order"(user_id);
CREATE INDEX IF NOT EXISTS idx_order_status ON "order"(order_status);
CREATE INDEX IF NOT EXISTS idx_orderitem_order ON orderitem(order_id);
CREATE INDEX IF NOT EXISTS idx_orderitem_course ON orderitem(course_id);
CREATE INDEX IF NOT EXISTS idx_payment_order ON payment(order_id);
CREATE INDEX IF NOT EXISTS idx_receipt_order ON receipt(order_id);
CREATE INDEX IF NOT EXISTS idx_receiptitem_receipt ON receiptitem(receipt_id);
CREATE INDEX IF NOT EXISTS idx_receiptitem_course ON receiptitem(course_id);
CREATE INDEX IF NOT EXISTS idx_promo_usage_order ON promo_usage(order_id);
CREATE INDEX IF NOT EXISTS idx_balancetransaction_user ON balancetransaction(user_id);
CREATE INDEX IF NOT EXISTS idx_balancetransaction_order ON balancetransaction(order_id);
CREATE INDEX IF NOT EXISTS idx_balancetransaction_course_purchase ON balancetransaction(course_purchase_id);
CREATE INDEX IF NOT EXISTS idx_organizationtransaction_order ON organizationtransaction(order_id);
CREATE INDEX IF NOT EXISTS idx_organizationtransaction_course_purchase ON organizationtransaction(course_purchase_id);
CREATE INDEX IF NOT EXISTS idx_userprofile_user ON userprofile(user_id);
CREATE INDEX IF NOT EXISTS idx_useraddress_user ON useraddress(user_id);
CREATE INDEX IF NOT EXISTS idx_activitylog_user ON activitylog(user_id);
CREATE INDEX IF NOT EXISTS idx_usersettings_user ON usersettings(user_id);

-- =============================================================================
-- ТРИ ФУНКЦИИ (бизнес-логика для сайта курсов)
-- =============================================================================

-- 1) Итоговая цена курса с учётом скидки (для отображения на карточке)
CREATE OR REPLACE FUNCTION course_final_price(p_course_id BIGINT)
RETURNS DECIMAL(10,2) AS $$
DECLARE
    v_price DECIMAL(10,2);
    v_discount DECIMAL(5,2);
BEGIN
    SELECT price, COALESCE(discount, 0) INTO v_price, v_discount
    FROM course WHERE id = p_course_id;
    IF v_price IS NULL THEN
        RETURN 0;
    END IF;
    RETURN ROUND(v_price * (1 - v_discount / 100.00), 2);
EXCEPTION
    WHEN OTHERS THEN
        RETURN 0;
END;
$$ LANGUAGE plpgsql;

-- 2) Обновление баланса пользователя с записью в balancetransaction (оплата курса/заказа, пополнение, возврат)
CREATE OR REPLACE FUNCTION update_user_balance(
    p_user_id INTEGER,
    p_amount DECIMAL(10,2),
    p_transaction_type VARCHAR(20),
    p_description TEXT DEFAULT NULL,
    p_order_id BIGINT DEFAULT NULL,
    p_course_purchase_id BIGINT DEFAULT NULL
)
RETURNS JSON AS $$
DECLARE
    v_current_balance DECIMAL(10,2);
    v_new_balance DECIMAL(10,2);
    v_transaction_id BIGINT;
BEGIN
    SELECT COALESCE(balance, 0) INTO v_current_balance
    FROM userprofile WHERE user_id = p_user_id;

    IF p_transaction_type IN ('withdrawal', 'order_payment', 'course_payment') AND v_current_balance < p_amount THEN
        RETURN json_build_object('success', false, 'error', 'Недостаточно средств на балансе');
    END IF;

    IF p_transaction_type IN ('deposit', 'order_refund', 'course_refund') THEN
        v_new_balance := v_current_balance + p_amount;
    ELSIF p_transaction_type IN ('withdrawal', 'order_payment', 'course_payment') THEN
        v_new_balance := v_current_balance - p_amount;
    ELSE
        RETURN json_build_object('success', false, 'error', 'Неизвестный тип транзакции');
    END IF;

    UPDATE userprofile SET balance = v_new_balance WHERE user_id = p_user_id;

    INSERT INTO balancetransaction (user_id, transaction_type, amount, description, order_id, course_purchase_id, status)
    VALUES (p_user_id, p_transaction_type, p_amount, p_description, p_order_id, p_course_purchase_id, 'completed')
    RETURNING id INTO v_transaction_id;

    RETURN json_build_object('success', true, 'balance_after', v_new_balance, 'transaction_id', v_transaction_id);
EXCEPTION
    WHEN OTHERS THEN
        RETURN json_build_object('success', false, 'error', SQLERRM);
END;
$$ LANGUAGE plpgsql;

-- 3) Процент прохождения курса (доля просмотренных страниц контента) для «мои курсы»
CREATE OR REPLACE FUNCTION course_progress_percent(p_course_purchase_id BIGINT)
RETURNS NUMERIC AS $$
DECLARE
    v_total INTEGER;
    v_viewed INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_total
    FROM course_content_page ccp
    JOIN course_purchase cp ON cp.course_id = ccp.course_id
    WHERE cp.id = p_course_purchase_id;
    IF v_total = 0 THEN
        RETURN 100;
    END IF;
    SELECT COUNT(*) INTO v_viewed
    FROM course_content_view WHERE course_purchase_id = p_course_purchase_id;
    RETURN ROUND(100.0 * v_viewed / v_total, 1);
EXCEPTION
    WHEN OTHERS THEN
        RETURN 0;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- ТРИ ПРЕДСТАВЛЕНИЯ (аналитика и «мои курсы»)
-- =============================================================================

-- 1) Аналитика по курсам: продажи, выручка, отзывы, опросы
CREATE OR REPLACE VIEW v_course_analytics AS
SELECT
    c.id AS course_id,
    c.title,
    c.price,
    c.discount,
    COUNT(DISTINCT cp.id) FILTER (WHERE cp.status = 'paid') AS purchases_count,
    COALESCE(SUM(cp.amount) FILTER (WHERE cp.status = 'paid'), 0) AS total_revenue,
    COUNT(DISTINCT cr.id) AS reviews_count,
    COALESCE(AVG(cr.rating) FILTER (WHERE cr.id IS NOT NULL), 0) AS avg_rating,
    COUNT(DISTINCT cs.id) AS surveys_count
FROM course c
LEFT JOIN course_purchase cp ON c.id = cp.course_id
LEFT JOIN course_review cr ON c.id = cr.course_id
LEFT JOIN course_survey cs ON cp.id = cs.course_purchase_id
GROUP BY c.id, c.title, c.price, c.discount;

-- 2) Количество ответов на опросы по курсам (3НФ: course_survey связь через course_purchase_id)
CREATE OR REPLACE VIEW v_course_survey_analytics AS
SELECT
    c.id AS course_id,
    c.title AS course_title,
    COUNT(cs.id) AS responses_count
FROM course c
LEFT JOIN course_purchase cp ON c.id = cp.course_id
LEFT JOIN course_survey cs ON cp.id = cs.course_purchase_id
GROUP BY c.id, c.title;

-- 3) «Мои курсы»: купленные курсы пользователя с прогрессом и статусом
CREATE OR REPLACE VIEW v_user_my_courses AS
SELECT
    u.id AS user_id,
    u.username,
    cp.id AS course_purchase_id,
    c.id AS course_id,
    c.title AS course_title,
    cp.status AS purchase_status,
    cp.paid_at,
    cp.completed_at,
    (SELECT COUNT(*) FROM course_content_page ccp WHERE ccp.course_id = c.id) AS content_total_pages,
    (SELECT COUNT(*) FROM course_content_view ccv WHERE ccv.course_purchase_id = cp.id) AS content_viewed_pages,
    course_progress_percent(cp.id) AS progress_percent
FROM auth_user u
JOIN course_purchase cp ON cp.user_id = u.id
JOIN course c ON c.id = cp.course_id;

-- =============================================================================
-- ТРИ ТРИГГЕРА (аудит изменений заказов, баланса, оплаты курса)
-- =============================================================================

CREATE OR REPLACE FUNCTION tr_audit_order_changes()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.order_status IS DISTINCT FROM NEW.order_status OR OLD.total_amount IS DISTINCT FROM NEW.total_amount THEN
        INSERT INTO activitylog (user_id, action_type, target_object, action_description, created_at)
        VALUES (
            COALESCE(NEW.user_id, OLD.user_id),
            'order_change',
            'order',
            'Заказ #' || NEW.id || ': статус «' || COALESCE(OLD.order_status,'') || '» → «' || COALESCE(NEW.order_status,'') || '», сумма ' || COALESCE(OLD.total_amount,0) || ' → ' || COALESCE(NEW.total_amount,0),
            CURRENT_TIMESTAMP
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_audit_order_changes ON "order";
CREATE TRIGGER trigger_audit_order_changes
    AFTER UPDATE ON "order"
    FOR EACH ROW
    WHEN (OLD.order_status IS DISTINCT FROM NEW.order_status OR OLD.total_amount IS DISTINCT FROM NEW.total_amount)
    EXECUTE FUNCTION tr_audit_order_changes();

CREATE OR REPLACE FUNCTION tr_audit_balance_changes()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.balance IS DISTINCT FROM NEW.balance THEN
        INSERT INTO activitylog (user_id, action_type, target_object, action_description, created_at)
        VALUES (
            NEW.user_id,
            'balance_change',
            'userprofile',
            'Баланс пользователя ' || NEW.user_id || ': ' || COALESCE(OLD.balance,0) || ' → ' || COALESCE(NEW.balance,0),
            CURRENT_TIMESTAMP
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_audit_balance_changes ON userprofile;
CREATE TRIGGER trigger_audit_balance_changes
    AFTER UPDATE OF balance ON userprofile
    FOR EACH ROW
    WHEN (OLD.balance IS DISTINCT FROM NEW.balance)
    EXECUTE FUNCTION tr_audit_balance_changes();

CREATE OR REPLACE FUNCTION tr_audit_course_purchase_paid()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'paid' AND (OLD.status IS NULL OR OLD.status <> 'paid') THEN
        INSERT INTO activitylog (user_id, action_type, target_object, action_description, created_at)
        VALUES (
            NEW.user_id,
            'course_purchased',
            'course_purchase',
            'Оплата курса: покупка #' || NEW.id || ', курс #' || NEW.course_id || ', сумма ' || NEW.amount,
            CURRENT_TIMESTAMP
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_audit_course_purchase_paid ON course_purchase;
CREATE TRIGGER trigger_audit_course_purchase_paid
    AFTER INSERT OR UPDATE OF status ON course_purchase
    FOR EACH ROW
    WHEN (NEW.status = 'paid')
    EXECUTE FUNCTION tr_audit_course_purchase_paid();

-- =============================================================================
-- Начальные данные
-- =============================================================================
INSERT INTO role (id, role_name) VALUES (1, 'ADMIN'), (2, 'USER'), (3, 'MANAGER') ON CONFLICT (id) DO NOTHING;

INSERT INTO receiptconfig (id, company_name, company_inn, company_address, cashier_name, shift_number, kkt_rn, kkt_sn, fn_number, site_fns)
VALUES (1, 'ООО «MPTCOURSE»', '7700000000', 'г. Москва, ул. Примерная, д. 1', 'Кассир', '1', '0000000000000000', '1234567890', '0000000000000000', 'www.nalog.ru')
ON CONFLICT (id) DO NOTHING;

INSERT INTO course_category (id, category_name, category_description, parent_id)
VALUES
(1, 'Программирование', 'Курсы по разработке ПО', NULL),
(2, 'Дизайн', 'Курсы по дизайну', NULL),
(3, 'Маркетинг', 'Курсы по маркетингу', NULL)
ON CONFLICT (id) DO NOTHING;

INSERT INTO course (id, category_id, title, slug, description, price, discount, is_available, added_at)
VALUES
(1, 1, 'Введение в Python', 'intro-python', 'Базовый курс по языку Python.', 2990.00, 0, TRUE, CURRENT_TIMESTAMP),
(2, 1, 'Django с нуля', 'django-from-zero', 'Веб-фреймворк Django: от установки до деплоя.', 4990.00, 10, TRUE, CURRENT_TIMESTAMP)
ON CONFLICT (slug) DO NOTHING;

INSERT INTO course_content_page (course_id, sort_order, content_type, file_path, title, page_number)
VALUES
(1, 1, 'video', 'courses/intro-python/lesson1.mp4', 'Урок 1: Установка', NULL),
(1, 2, 'pdf_page', 'courses/intro-python/slides.pdf', 'Презентация', 1),
(1, 3, 'pdf_page', 'courses/intro-python/slides.pdf', 'Презентация', 2),
(2, 1, 'pptx_slide', 'courses/django/module1.pptx', 'Модуль 1', 1),
(2, 2, 'video', 'courses/django/lesson1.mp4', 'Видео урока 1', NULL);

INSERT INTO promotion (id, promo_code, promo_description, discount, start_date, end_date, is_active)
VALUES (1, 'WELCOME10', 'Скидка 10% для новых', 10.00, CURRENT_DATE - INTERVAL '30 days', CURRENT_DATE + INTERVAL '30 days', TRUE)
ON CONFLICT (id) DO NOTHING;

INSERT INTO organizationaccount (id, balance, tax_reserve, created_at, updated_at)
VALUES (1, 0.00, 0.00, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
ON CONFLICT (id) DO NOTHING;

-- Последовательности (после вставок)
SELECT setval('course_category_id_seq', COALESCE((SELECT MAX(id) FROM course_category), 1));
SELECT setval('course_id_seq', COALESCE((SELECT MAX(id) FROM course), 1));
SELECT setval('course_image_id_seq', COALESCE((SELECT MAX(id) FROM course_image), 1));
SELECT setval('course_content_page_id_seq', COALESCE((SELECT MAX(id) FROM course_content_page), 1));
SELECT setval('course_purchase_id_seq', COALESCE((SELECT MAX(id) FROM course_purchase), 1));
SELECT setval('course_content_view_id_seq', COALESCE((SELECT MAX(id) FROM course_content_view), 1));
SELECT setval('lesson_id_seq', COALESCE((SELECT MAX(id) FROM lesson), 1));
SELECT setval('lesson_page_id_seq', COALESCE((SELECT MAX(id) FROM lesson_page), 1));
SELECT setval('lesson_completion_id_seq', COALESCE((SELECT MAX(id) FROM lesson_completion), 1));
SELECT setval('user_notification_id_seq', COALESCE((SELECT MAX(id) FROM user_notification), 1));
SELECT setval('course_refund_request_id_seq', COALESCE((SELECT MAX(id) FROM course_refund_request), 1));
SELECT setval('course_survey_id_seq', COALESCE((SELECT MAX(id) FROM course_survey), 1));
SELECT setval('course_review_id_seq', COALESCE((SELECT MAX(id) FROM course_review), 1));
SELECT setval('course_favorite_id_seq', COALESCE((SELECT MAX(id) FROM course_favorite), 1));
SELECT setval('cart_id_seq', COALESCE((SELECT MAX(id) FROM cart), 1));
SELECT setval('cartitem_id_seq', COALESCE((SELECT MAX(id) FROM cartitem), 1));
SELECT setval('order_id_seq', COALESCE((SELECT MAX(id) FROM "order"), 1));
SELECT setval('orderitem_id_seq', COALESCE((SELECT MAX(id) FROM orderitem), 1));
SELECT setval('payment_id_seq', COALESCE((SELECT MAX(id) FROM payment), 1));
SELECT setval('receipt_id_seq', COALESCE((SELECT MAX(id) FROM receipt), 1));
SELECT setval('receiptitem_id_seq', COALESCE((SELECT MAX(id) FROM receiptitem), 1));
SELECT setval('promo_usage_id_seq', COALESCE((SELECT MAX(id) FROM promo_usage), 1));
