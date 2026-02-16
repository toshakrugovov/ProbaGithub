from rest_framework import serializers
from .models import (
	Role, UserProfile, UserAddress, Cart, CartItem, Order, OrderItem, Payment,
	Promotion, SupportTicket, ActivityLog,
	SavedPaymentMethod, CardTransaction, BalanceTransaction, Receipt, ReceiptItem,
	OrganizationAccount, OrganizationTransaction,
	CourseCategory, Course, CourseFavorite,
)

class RoleSerializer(serializers.ModelSerializer):
	class Meta:
		model = Role
		fields = '__all__'

class UserAddressSerializer(serializers.ModelSerializer):
	class Meta:
		model = UserAddress
		fields = '__all__'

class UserProfileSerializer(serializers.ModelSerializer):
	user = serializers.StringRelatedField()
	class Meta:
		model = UserProfile
		fields = '__all__'


class CourseCategorySerializer(serializers.ModelSerializer):
	class Meta:
		model = CourseCategory
		fields = '__all__'


class CourseSerializer(serializers.ModelSerializer):
	final_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
	main_image_url = serializers.SerializerMethodField()
	images = serializers.SerializerMethodField()

	class Meta:
		model = Course
		fields = ['id', 'title', 'slug', 'description', 'included_content', 'price', 'discount', 'final_price',
		          'is_available', 'added_at', 'cover_image_path', 'category', 'main_image_url', 'images']

	def get_main_image_url(self, obj):
		return getattr(obj, 'main_image_url', None) or obj.cover_image_path or ''

	def get_images(self, obj):
		ordered = obj.get_ordered_images() if hasattr(obj, 'get_ordered_images') else []
		return [img.image_path for img in ordered] if ordered else [obj.cover_image_path or ''] if obj.cover_image_path else []


class CartItemSerializer(serializers.ModelSerializer):
	course_id = serializers.IntegerField(source='course.id', read_only=True, allow_null=True)
	course_title = serializers.CharField(source='course.title', read_only=True, allow_null=True)
	course_cover_image = serializers.SerializerMethodField()

	class Meta:
		model = CartItem
		fields = ['id', 'cart', 'course', 'quantity', 'unit_price', 'course_id', 'course_title', 'course_cover_image']

	def get_course_cover_image(self, obj):
		if obj.course:
			return getattr(obj.course, 'cover_image_path', None) or getattr(obj.course, 'main_image_url', None) or ''
		return ''

class CartSerializer(serializers.ModelSerializer):
	items = CartItemSerializer(many=True, read_only=True)
	class Meta:
		model = Cart
		fields = '__all__'

class OrderItemSerializer(serializers.ModelSerializer):
	class Meta:
		model = OrderItem
		fields = '__all__'

class OrderSerializer(serializers.ModelSerializer):
	# Делаем total_amount необязательным при создании (будет вычисляться автоматически)
	total_amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
	# Добавляем items (товары заказа) в сериализатор
	items = OrderItemSerializer(many=True, read_only=True)
	# Добавляем user_id и username для отладки
	user_id = serializers.IntegerField(source='user.id', read_only=True, allow_null=True)
	user_username = serializers.CharField(source='user.username', read_only=True, allow_null=True)
	
	class Meta:
		model = Order
		fields = '__all__'
		extra_kwargs = {
			'promo_code': {'required': False, 'allow_null': True}
		}
	
	def create(self, validated_data):
		# Убеждаемся, что total_amount установлен
		from decimal import Decimal
		
		if 'total_amount' not in validated_data or validated_data.get('total_amount') is None:
			# Если total_amount не указан, вычисляем его
			# Пытаемся вычислить из order items, если они переданы в контексте
			order_items = self.context.get('order_items', [])
			
			if order_items:
				total = Decimal('0.00')
				for item in order_items:
					if hasattr(item, 'unit_price') and hasattr(item, 'quantity'):
						total += Decimal(str(item.unit_price)) * int(item.quantity)
				
				# Добавляем delivery_cost если есть
				delivery_cost = validated_data.get('delivery_cost', Decimal('1000.00'))
				total += Decimal(str(delivery_cost))
				
				# Вычитаем discount если есть
				discount = validated_data.get('discount_amount', Decimal('0.00'))
				total -= Decimal(str(discount))
				
				# Учитываем НДС и налоги, если они есть
				vat_amount = validated_data.get('vat_amount', Decimal('0.00'))
				tax_amount = validated_data.get('tax_amount', Decimal('0.00'))
				total += Decimal(str(vat_amount)) + Decimal(str(tax_amount))
				
				validated_data['total_amount'] = total.quantize(Decimal('0.01'))
			else:
				# Если нет order items, вычисляем из delivery_cost и discount_amount
				delivery_cost = validated_data.get('delivery_cost', Decimal('1000.00'))
				discount = validated_data.get('discount_amount', Decimal('0.00'))
				vat_amount = validated_data.get('vat_amount', Decimal('0.00'))
				tax_amount = validated_data.get('tax_amount', Decimal('0.00'))
				
				# Базовое значение: delivery_cost - discount + налоги
				base_amount = delivery_cost - discount
				total = base_amount + vat_amount + tax_amount
				validated_data['total_amount'] = max(total.quantize(Decimal('0.01')), Decimal('0.00'))
		
		# Убеждаемся, что total_amount это Decimal
		if isinstance(validated_data.get('total_amount'), (int, float, str)):
			validated_data['total_amount'] = Decimal(str(validated_data['total_amount'])).quantize(Decimal('0.01'))
		
		return super().create(validated_data)

class PaymentSerializer(serializers.ModelSerializer):
	class Meta:
		model = Payment
		fields = '__all__'

class PromotionSerializer(serializers.ModelSerializer):
	class Meta:
		model = Promotion
		fields = '__all__'

class SupportTicketSerializer(serializers.ModelSerializer):
	status_display = serializers.CharField(source='get_ticket_status_display', read_only=True)
	
	class Meta:
		model = SupportTicket
		fields = '__all__'

class ActivityLogSerializer(serializers.ModelSerializer):
	class Meta:
		model = ActivityLog
		fields = '__all__'

class SavedPaymentMethodSerializer(serializers.ModelSerializer):
	class Meta:
		model = SavedPaymentMethod
		fields = '__all__'

class CardTransactionSerializer(serializers.ModelSerializer):
	class Meta:
		model = CardTransaction
		fields = '__all__'

class BalanceTransactionSerializer(serializers.ModelSerializer):
	class Meta:
		model = BalanceTransaction
		fields = '__all__'

class ReceiptSerializer(serializers.ModelSerializer):
	class Meta:
		model = Receipt
		fields = '__all__'

class ReceiptItemSerializer(serializers.ModelSerializer):
	class Meta:
		model = ReceiptItem
		fields = '__all__'

class OrganizationAccountSerializer(serializers.ModelSerializer):
	class Meta:
		model = OrganizationAccount
		fields = '__all__'

class OrganizationTransactionSerializer(serializers.ModelSerializer):
	class Meta:
		model = OrganizationTransaction
		fields = '__all__'
