import graphene
from graphene_django import DjangoObjectType
from graphene import relay
from products.models import Product as ProductModel, Category as CategoryModel, Manufacturer as ManufacturerModel

class Product(DjangoObjectType):
    exists = graphene.Boolean(default_value=True)
    
    class Meta:
        model = ProductModel
        name = "Product"
        fields = (
            "id", "name", "slug", "description", "specifications", 
            "manufacturer", "part_number", "categories", "weight", 
            "dimensions", "main_image", "additional_images",
            "status", "created_at", "updated_at", "offers",
            "affiliate_links"
        )

class ProductType(DjangoObjectType):
    class Meta:
        model = ProductModel
        fields = "__all__"
        name = "Product"
        interfaces = (relay.Node, )  # This enables the connection
        filter_fields = {
            'name': ['exact', 'icontains', 'istartswith'],
            'part_number': ['exact', 'icontains'],
            # add other fields as needed
        }
        connection_class = relay.Connection
    
    # GraphQL expects camelCase but Django uses snake_case
    mainImage = graphene.String(source='main_image')
    additionalImages = graphene.List(graphene.String, source='additional_images')
    partNumber = graphene.String(source='part_number')
    dimensions = graphene.Field('ecommerce_platform.schema.Dimensions')
    
    # BACKWARD COMPATIBILITY: Chrome extension expects asin field
    asin = graphene.String()
    
    def resolve_dimensions(self, info):
        return self.dimensions or {}
    
    def resolve_offers(self, info):
        """
        Custom offers resolver that includes virtual TruPrice offers in demo mode
        """
        try:
            # Get real offers
            real_offers = list(self.offers.all())
            
            # Check if we should add demo offers based on context
            request = info.context
            demo_context = getattr(request, '_demo_quote_context', None)
            
            if demo_context and demo_context.get('demo_mode'):
                # Generate virtual TruPrice offers inline (no method call)
                from decimal import Decimal
                import random
                from offers.models import Offer, Vendor
                
                virtual_offers = []
                quote_items = demo_context.get('quote_items', [])
                
                # Find quote items for this product
                for quote_item in quote_items:
                    if hasattr(quote_item, 'matches'):
                        for match in quote_item.matches.filter(product=self):
                            # Create virtual TruPrice offer with 5-10% better pricing
                            discount_percent = random.uniform(5, 10)  # 5-10% discount
                            quote_price = quote_item.unit_price
                            # Convert to Decimal for proper arithmetic
                            discount_factor = Decimal(str(1 - discount_percent / 100))
                            truprice = quote_price * discount_factor
                            
                            # Get or create TruPrice vendor
                            truprice_vendor, _ = Vendor.objects.get_or_create(
                                code='TRUPRICE',
                                defaults={
                                    'name': 'TruPrice',
                                    'vendor_type': 'supplier',
                                    'is_active': True
                                }
                            )
                            
                            # Create virtual offer (don't save to database)
                            virtual_offer = Offer(
                                id=f"virtual_truprice_{self.id}_{quote_item.id}",
                                product=self,
                                vendor=truprice_vendor,
                                offer_type='supplier',
                                selling_price=Decimal(str(round(truprice, 2))),
                                vendor_sku=f"TP-{quote_item.part_number}",
                                stock_quantity=quote_item.quantity,
                                is_in_stock=True,
                                is_active=True,
                                is_confirmed=True,  # TruPrice is always confirmed
                                source_quote=None
                            )
                            
                            # Add custom attributes for identification
                            virtual_offer._is_virtual = True
                            virtual_offer._discount_percent = discount_percent
                            virtual_offer._original_price = quote_item.unit_price
                            
                            virtual_offers.append(virtual_offer)
                            break  # Only one TruPrice offer per product
                
                return real_offers + virtual_offers
            
            return real_offers
            
        except Exception as e:
            # Log the error and return real offers as fallback
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error in resolve_offers for product {self.id}: {str(e)}")
            logger.error(f"Full traceback:", exc_info=True)
            # Fallback to default behavior
            return list(self.offers.all())
    

    

    
    def resolve_asin(self, info):
        """
        Resolve ASIN from affiliate links if available
        Chrome extension expects this field for Amazon compatibility
        """
        # Check if product has Amazon affiliate link
        from affiliates.models import AffiliateLink
        amazon_link = AffiliateLink.objects.filter(
            product=self,
            platform='amazon'
        ).first()
        
        if amazon_link:
            return amazon_link.platform_id
        
        # Fallback: check if part_number looks like an ASIN (10 chars, alphanumeric)
        if self.part_number and len(self.part_number) == 10 and self.part_number.isalnum():
            return self.part_number
            
        return None

class CategoryType(DjangoObjectType):
    class Meta:
        model = CategoryModel
        fields = "__all__"

class ManufacturerType(DjangoObjectType):
    class Meta:
        model = ManufacturerModel
        fields = "__all__"

