from django.core.management.base import BaseCommand
from products.consumer_matching import dynamic_intelligence


class Command(BaseCommand):
    help = 'Analyze product database and suggest intelligence improvements'

    def add_arguments(self, parser):
        parser.add_argument(
            '--update-cache',
            action='store_true',
            help='Force update the learned categories cache',
        )
        parser.add_argument(
            '--suggest-categories',
            action='store_true', 
            help='Suggest new product categories to add',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🧠 Product Intelligence Analysis'))
        
        if options['update_cache']:
            self.stdout.write('🔄 Updating learned categories cache...')
            # Clear cache to force re-learning
            from django.core.cache import cache
            cache.clear()
            learned = dynamic_intelligence.get_learned_categories()
            
            self.stdout.write('📊 Learned Categories Summary:')
            for category, indicators in learned.items():
                self.stdout.write(f'  • {category}: {len(indicators)} indicators')
                if indicators:
                    self.stdout.write(f'    Top terms: {indicators[:5]}')
        
        if options['suggest_categories']:
            self.stdout.write('🔍 Analyzing for new product categories...')
            suggestions = dynamic_intelligence.suggest_new_categories()
            
            if suggestions:
                self.stdout.write('💡 Suggested new categories:')
                for word, data in list(suggestions.items())[:10]:
                    self.stdout.write(f'  • "{word}" ({data["count"]} products)')
                    for example in data['examples']:
                        self.stdout.write(f'    - {example}')
            else:
                self.stdout.write('✅ No new categories suggested - current system covers products well')
        
        # Show marketing noise detection
        self.stdout.write('🔇 Marketing Noise Analysis:')
        noise_terms = dynamic_intelligence.detect_marketing_noise()
        self.stdout.write(f'  Detected {len(noise_terms)} marketing noise terms')
        self.stdout.write(f'  Sample terms: {noise_terms[:10]}')
        
        # Test extraction on some sample products
        self.stdout.write('🧪 Testing extraction on sample products:')
        from products.models import Product
        from products.consumer_matching import smart_extract_search_terms_dynamic
        
        sample_products = Product.objects.filter(is_demo=False)[:5]
        for product in sample_products:
            result = smart_extract_search_terms_dynamic(product.name)
            self.stdout.write(f'  📦 {product.name[:50]}...')
            self.stdout.write(f'     → Type: {result.get("type")}, Method: {result.get("method")}')
            self.stdout.write(f'     → Clean terms: {result.get("clean_terms")}')
        
        self.stdout.write(self.style.SUCCESS('✅ Analysis complete!')) 