import graphene
from graphql import GraphQLError
from django.db import transaction
from products.models import Product, Manufacturer, Category, ProductCategory
from ..types.product import ProductType
from ..types.scalar import JSONScalar

class ProductInput(graphene.InputObjectType):
    name = graphene.String(required=True)
    description = graphene.String()
    manufacturer_id = graphene.ID(required=True)
    part_number = graphene.String(required=True)
    category_ids = graphene.List(graphene.ID)
    specifications = JSONScalar()
    weight = graphene.Float()
    dimensions = JSONScalar()
    main_image = graphene.String()
    additional_images = graphene.List(graphene.String)
    status = graphene.String()

class AmazonProductInput(graphene.InputObjectType):
    name = graphene.String(required=True)
    description = graphene.String()
    part_number = graphene.String(required=True)
    manufacturer_name = graphene.String(required=True)
    asin = graphene.String(required=True)
    url = graphene.String(required=True)
    image = graphene.String()
    price = graphene.Float()
    category_name = graphene.String()

class CreateProduct(graphene.Mutation):
    class Arguments:
        input = ProductInput(required=True)
    
    product = graphene.Field(ProductType)
    
    @staticmethod
    def mutate(root, info, input):
        try:
            with transaction.atomic():
                manufacturer = Manufacturer.objects.get(pk=input.manufacturer_id)
                
                # Check for duplicate products
                if Product.objects.filter(
                    manufacturer=manufacturer, 
                    part_number=input.part_number
                ).exists():
                    raise GraphQLError(f"Product with part number {input.part_number} already exists for {manufacturer.name}")
                
                # Create slug from name
                from django.utils.text import slugify
                slug = slugify(input.name)
                
                # Create the product
                product = Product.objects.create(
                    name=input.name,
                    slug=slug,
                    description=input.description or "",
                    specifications=input.specifications or {},
                    manufacturer=manufacturer,
                    part_number=input.part_number,
                    weight=input.weight,
                    dimensions=input.dimensions or {},
                    main_image=input.main_image or "",
                    additional_images=input.additional_images or [],
                    status=input.status or "active"
                )
                
                # Add categories if provided
                if input.category_ids:
                    categories = Category.objects.filter(id__in=input.category_ids)
                    for category in categories:
                        ProductCategory.objects.create(product=product, category=category)
                
                return CreateProduct(product=product)
        except Manufacturer.DoesNotExist:
            raise GraphQLError(f"Manufacturer with ID {input.manufacturer_id} not found")
        except Exception as e:
            raise GraphQLError(str(e))

class UpdateProduct(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        input = ProductInput(required=True)
    
    product = graphene.Field(ProductType)
    
    @staticmethod
    def mutate(root, info, id, input):
        try:
            with transaction.atomic():
                product = Product.objects.get(pk=id)
                
                # Update fields
                product.name = input.name
                if input.description is not None:
                    product.description = input.description
                
                # Handle manufacturer change
                if input.manufacturer_id:
                    manufacturer = Manufacturer.objects.get(pk=input.manufacturer_id)
                    product.manufacturer = manufacturer
                
                # Update other fields if provided
                if input.part_number:
                    product.part_number = input.part_number
                
                if input.specifications is not None:
                    product.specifications = input.specifications
                
                if input.weight is not None:
                    product.weight = input.weight
                
                if input.dimensions is not None:
                    product.dimensions = input.dimensions
                
                if input.main_image is not None:
                    product.main_image = input.main_image
                
                if input.additional_images is not None:
                    product.additional_images = input.additional_images
                
                if input.status:
                    product.status = input.status
                
                # Update slug
                from django.utils.text import slugify
                product.slug = slugify(product.name)
                
                product.save()
                
                # Update categories if provided
                if input.category_ids:
                    # Remove existing categories
                    ProductCategory.objects.filter(product=product).delete()
                    
                    # Add new categories
                    categories = Category.objects.filter(id__in=input.category_ids)
                    for category in categories:
                        ProductCategory.objects.create(product=product, category=category)
                
                return UpdateProduct(product=product)
        except Product.DoesNotExist:
            raise GraphQLError(f"Product with ID {id} not found")
        except Exception as e:
            raise GraphQLError(str(e))

class CreateProductFromAmazon(graphene.Mutation):
    class Arguments:
        input = AmazonProductInput(required=True)
    
    product = graphene.Field(ProductType)
    
    @staticmethod
    def mutate(root, info, input):
        try:
            with transaction.atomic():
                # Get or create manufacturer
                manufacturer, created = Manufacturer.objects.get_or_create(
                    name=input.manufacturer_name,
                    defaults={
                        'slug': slugify(input.manufacturer_name),
                        'description': f"Manufacturer of {input.name}"
                    }
                )
                
                # Check if product already exists
                try:
                    existing_product = Product.objects.get(
                        manufacturer=manufacturer,
                        part_number=input.part_number
                    )
                    return CreateProductFromAmazon(product=existing_product)
                except Product.DoesNotExist:
                    pass
                
                # Create slug from name
                from django.utils.text import slugify
                slug = slugify(input.name)
                
                # Create the product
                product = Product.objects.create(
                    name=input.name,
                    slug=slug,
                    description=input.description or "",
                    specifications={},
                    manufacturer=manufacturer,
                    part_number=input.part_number,
                    main_image=input.image or "",
                    additional_images=[],
                    status="active",
                    source="amazon"
                )
                
                # Handle category
                if input.category_name:
                    category, created = Category.objects.get_or_create(
                        name=input.category_name,
                        defaults={
                            'slug': slugify(input.category_name),
                            'description': f"Category for {input.category_name}"
                        }
                    )
                    ProductCategory.objects.create(product=product, category=category)
                
                # Create affiliate link for Amazon
                from affiliates.models import AffiliateLink
                affiliate_link = AffiliateLink.objects.create(
                    product=product,
                    platform="amazon",
                    platform_id=input.asin,
                    original_url=input.url,
                    affiliate_url="",  # Will be populated by background task
                    is_active=True
                )
                
                # Queue task to generate affiliate URL
                from django_q.tasks import async_task
                async_task('affiliates.tasks.generate_amazon_affiliate_url', 
                          affiliate_link.id, input.asin)
                
                return CreateProductFromAmazon(product=product)
        except Exception as e:
            raise GraphQLError(str(e))

class ProductMutation(graphene.ObjectType):
    create_product = CreateProduct.Field()
    update_product = UpdateProduct.Field()
    create_product_from_amazon = CreateProductFromAmazon.Field() 