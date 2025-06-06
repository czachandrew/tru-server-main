# Generated by Django 4.2.7 on 2025-05-01 16:38

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("products", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AffiliateLink",
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
                    "platform",
                    models.CharField(
                        choices=[
                            ("amazon", "Amazon"),
                            ("ebay", "eBay"),
                            ("walmart", "Walmart"),
                            ("other", "Other"),
                        ],
                        max_length=50,
                    ),
                ),
                ("platform_id", models.CharField(max_length=100)),
                ("original_url", models.URLField(max_length=500)),
                ("affiliate_url", models.URLField(max_length=1000)),
                ("clicks", models.IntegerField(default=0)),
                ("conversions", models.IntegerField(default=0)),
                (
                    "revenue",
                    models.DecimalField(decimal_places=2, default=0, max_digits=10),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="affiliate_links",
                        to="products.product",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="affiliatelink",
            constraint=models.UniqueConstraint(
                fields=("product", "platform"), name="unique_product_platform_link"
            ),
        ),
    ]
