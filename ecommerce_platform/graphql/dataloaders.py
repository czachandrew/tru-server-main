from promise import Promise
from promise.dataloader import DataLoader
from products.models import Product, Manufacturer, Category
from offers.models import Offer

class ProductLoader(DataLoader):
    def batch_load_fn(self, keys):
        products = {p.id: p for p in Product.objects.filter(id__in=keys)}
        return Promise.resolve([products.get(id) for id in keys])

class ManufacturerLoader(DataLoader):
    def batch_load_fn(self, keys):
        manufacturers = {m.id: m for m in Manufacturer.objects.filter(id__in=keys)}
        return Promise.resolve([manufacturers.get(id) for id in keys])

class CategoryLoader(DataLoader):
    def batch_load_fn(self, keys):
        categories = {c.id: c for c in Category.objects.filter(id__in=keys)}
        return Promise.resolve([categories.get(id) for id in keys])

class OfferLoader(DataLoader):
    def batch_load_fn(self, keys):
        offers = {o.id: o for o in Offer.objects.filter(id__in=keys)}
        return Promise.resolve([offers.get(id) for id in keys]) 