from django.db import models
from django.contrib.auth.models import User
from django.db.models import Q
from products.models import Category
from offers.models import Offer
from django.conf import settings


class Cart(models.Model):
    """Shopping cart"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE)
    session_id = models.CharField(max_length=100, blank=True)  # For anonymous users
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        constraints = [
            models.CheckConstraint(
                check=Q(user__isnull=False) | Q(session_id__gt=''),
                name='cart_user_or_session'
            )
        ]
    
    def __str__(self):
        return f"Cart {self.id} - {self.user.username if self.user else 'Anonymous'}"

class CartItem(models.Model):
    """Items in a shopping cart"""
    cart = models.ForeignKey(Cart, related_name='items', on_delete=models.CASCADE)
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1)
    
    added_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['cart', 'offer'],
                name='unique_cart_offer'
            )
        ]
    
    def __str__(self):
        return f"{self.quantity} x {self.offer.product.name}"