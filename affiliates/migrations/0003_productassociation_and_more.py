# Generated by Django 4.2.7 on 2025-06-10 13:58

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        (
            "products",
            "0004_product_future_demand_count_product_last_demand_date_and_more",
        ),
        ("affiliates", "0002_alter_affiliatelink_affiliate_url_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductAssociation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "original_search_term",
                    models.CharField(
                        help_text="Original search term used (e.g., 'Dell XPS keyboard')",
                        max_length=255,
                    ),
                ),
                (
                    "search_context",
                    models.JSONField(
                        blank=True,
                        help_text="Additional context like browser, product page URL, etc.",
                        null=True,
                    ),
                ),
                (
                    "association_type",
                    models.CharField(
                        choices=[
                            ("search_alternative", "Search Alternative"),
                            ("same_brand_alternative", "Same Brand Alternative"),
                            ("cross_brand_alternative", "Cross Brand Alternative"),
                            ("upgrade_option", "Upgrade Option"),
                            ("budget_option", "Budget Option"),
                            ("compatible_accessory", "Compatible Accessory"),
                            ("bundle_item", "Bundle Item"),
                        ],
                        default="search_alternative",
                        max_length=30,
                    ),
                ),
                (
                    "confidence_score",
                    models.DecimalField(
                        decimal_places=2,
                        default=1.0,
                        help_text="Confidence score 0.00-1.00 for this association",
                        max_digits=3,
                    ),
                ),
                (
                    "search_count",
                    models.IntegerField(
                        default=1,
                        help_text="Number of times this association was created/reinforced",
                    ),
                ),
                (
                    "click_count",
                    models.IntegerField(
                        default=0,
                        help_text="Number of times users clicked on this alternative",
                    ),
                ),
                (
                    "conversion_count",
                    models.IntegerField(
                        default=0,
                        help_text="Number of times this alternative led to purchases",
                    ),
                ),
                ("first_seen", models.DateTimeField(auto_now_add=True)),
                ("last_seen", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "created_via_platform",
                    models.CharField(
                        choices=[
                            ("amazon", "Amazon"),
                            ("ebay", "eBay"),
                            ("walmart", "Walmart"),
                            ("other", "Other"),
                        ],
                        default="amazon",
                        help_text="Platform where this association was discovered",
                        max_length=50,
                    ),
                ),
                (
                    "source_product",
                    models.ForeignKey(
                        blank=True,
                        help_text="Original product that was searched for (can be null for search terms)",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="associations_as_source",
                        to="products.product",
                    ),
                ),
                (
                    "target_product",
                    models.ForeignKey(
                        help_text="Product that was found as an alternative",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="associations_as_target",
                        to="products.product",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["original_search_term"],
                        name="affiliates__origina_a97b8e_idx",
                    ),
                    models.Index(
                        fields=["association_type"],
                        name="affiliates__associa_e0abac_idx",
                    ),
                    models.Index(
                        fields=["confidence_score"],
                        name="affiliates__confide_c0430a_idx",
                    ),
                    models.Index(
                        fields=["search_count"], name="affiliates__search__cc2870_idx"
                    ),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="productassociation",
            constraint=models.UniqueConstraint(
                fields=("source_product", "target_product", "association_type"),
                name="unique_product_association",
            ),
        ),
    ]
