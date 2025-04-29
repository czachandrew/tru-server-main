# products/management/commands/create_sample_data.py
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from products.models import Manufacturer, Category, Product
from vendors.models import Vendor
from offers.models import Offer
from affiliates.models import AffiliateLink

class Command(BaseCommand):
    help = 'Creates sample data for testing GraphQL'

    def handle(self, *args, **kwargs):
        self.stdout.write('Creating sample data...')
        
        # Create manufacturers
        arduino = Manufacturer.objects.create(
            name='Arduino',
            slug='arduino',
            description='Open-source electronics platform'
        )
        
        raspberry = Manufacturer.objects.create(
            name='Raspberry Pi Foundation',
            slug='raspberry-pi',
            description='Single-board computers'
        )
        
        # Create categories
        electronics = Category.objects.create(
            name='Electronics',
            slug='electronics',
            description='Electronic components and boards'
        )
        
        microcontrollers = Category.objects.create(
            name='Microcontrollers',
            slug='microcontrollers',
            description='Programmable microcontrollers',
            parent=electronics
        )
        
        # Create products
        arduino_uno = Product.objects.create(
            name='Arduino Uno R3',
            slug='arduino-uno-r3',
            description='ATmega328P microcontroller board',
            manufacturer=arduino,
            part_number='A000066',
            main_image='https://store.arduino.cc/products/arduino-uno-rev3',
            specifications={
                'processor': 'ATmega328P',
                'clock_speed': '16 MHz',
                'digital_pins': 14,
                'analog_pins': 6
            },
            status='active'
        )
        arduino_uno.categories.add(microcontrollers)
        
        pi_4 = Product.objects.create(
            name='Raspberry Pi 4 Model B',
            slug='raspberry-pi-4-model-b',
            description='Powerful single-board computer',
            manufacturer=raspberry,
            part_number='SC0193',
            main_image='https://www.raspberrypi.org/products/raspberry-pi-4-model-b/',
            specifications={
                'processor': 'Broadcom BCM2711',
                'ram': '4GB',
                'usb_ports': 4,
                'hdmi_ports': 2
            },
            status='active'
        )
        pi_4.categories.add(electronics)
        
        # Create vendors
        digikey = Vendor.objects.create(
            name='Digikey',
            code='digikey',
            contact_email='contact@digikey.com',
            is_active=True
        )
        
        mouser = Vendor.objects.create(
            name='Mouser',
            code='mouser',
            contact_email='contact@mouser.com',
            is_active=True
        )
        
        # Create offers
        Offer.objects.create(
            product=arduino_uno,
            vendor=digikey,
            cost_price=20.00,
            selling_price=23.50,
            msrp=25.00,
            vendor_sku='1050-1024-ND',
            vendor_url='https://www.digikey.com/arduino-uno',
            stock_quantity=100,
            is_in_stock=True
        )
        
        Offer.objects.create(
            product=arduino_uno,
            vendor=mouser,
            cost_price=19.50,
            selling_price=22.95,
            msrp=25.00,
            vendor_sku='782-A000066',
            vendor_url='https://www.mouser.com/arduino-uno',
            stock_quantity=75,
            is_in_stock=True
        )
        
        Offer.objects.create(
            product=pi_4,
            vendor=digikey,
            cost_price=45.00,
            selling_price=55.00,
            msrp=55.00,
            vendor_sku='1690-RASPBERRYPI4B/4GB-ND',
            vendor_url='https://www.digikey.com/raspberry-pi-4',
            stock_quantity=50,
            is_in_stock=True
        )
        
        # Create affiliate links
        AffiliateLink.objects.create(
            product=arduino_uno,
            platform='amazon',
            platform_id='B008GRTSV6',
            original_url='https://www.amazon.com/dp/B008GRTSV6',
            affiliate_url='https://www.amazon.com/dp/B008GRTSV6?tag=yourstore-20',
            is_active=True
        )
        
        AffiliateLink.objects.create(
            product=pi_4,
            platform='amazon',
            platform_id='B07TC2BK1X',
            original_url='https://www.amazon.com/dp/B07TC2BK1X',
            affiliate_url='https://www.amazon.com/dp/B07TC2BK1X?tag=yourstore-20',
            is_active=True
        )
        
        # After creating your products, mark some as featured
        arduino_uno.is_featured = True
        arduino_uno.save()

        # And perhaps a few more products
        raspberry_pi = Product.objects.get(part_number='RP4B')  # Assuming you have this product
        if raspberry_pi:
            raspberry_pi.is_featured = True
            raspberry_pi.save()
        
        self.stdout.write(self.style.SUCCESS('Sample data created successfully!'))