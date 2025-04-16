# Generated by Django 4.2.7 on 2025-04-16 20:47

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("products", "0001_initial"),
        ("vendors", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Offer",
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
                ("cost_price", models.DecimalField(decimal_places=2, max_digits=10)),
                ("selling_price", models.DecimalField(decimal_places=2, max_digits=10)),
                (
                    "msrp",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=10, null=True
                    ),
                ),
                ("vendor_sku", models.CharField(blank=True, max_length=100)),
                ("vendor_url", models.URLField(blank=True, max_length=500)),
                ("stock_quantity", models.IntegerField(default=0)),
                ("is_in_stock", models.BooleanField(default=True)),
                ("availability_updated_at", models.DateTimeField(auto_now=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="offers",
                        to="products.product",
                    ),
                ),
                (
                    "vendor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="offers",
                        to="vendors.vendor",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="offer",
            constraint=models.UniqueConstraint(
                fields=("product", "vendor"), name="unique_product_vendor_offer"
            ),
        ),
    ]
