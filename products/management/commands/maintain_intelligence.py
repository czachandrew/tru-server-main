from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings
from products.consumer_matching import dynamic_intelligence
from products.models import Product
import json
from datetime import datetime, timedelta


class Command(BaseCommand):
    help = 'Automated weekly maintenance of product intelligence system'

    def add_arguments(self, parser):
        parser.add_argument(
            '--email-report',
            action='store_true',
            help='Send analysis report via email',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🔄 Weekly Intelligence Maintenance'))
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'product_count': Product.objects.count(),
            'new_products_this_week': 0,
            'intelligence_updates': [],
            'recommendations': []
        }
        
        # Check for new products added this week
        week_ago = datetime.now() - timedelta(days=7)
        new_products = Product.objects.filter(created_at__gte=week_ago)
        report['new_products_this_week'] = new_products.count()
        
        if new_products.count() > 0:
            self.stdout.write(f'📦 {new_products.count()} new products added this week')
            
            # Analyze new product categories
            new_categories = self._analyze_new_product_patterns(new_products)
            if new_categories:
                report['intelligence_updates'].append({
                    'type': 'new_categories_detected',
                    'categories': new_categories
                })
        
        # Update learned categories cache
        if not options['dry_run']:
            from django.core.cache import cache
            cache.delete('learned_categories_v1')
            learned = dynamic_intelligence.get_learned_categories()
            report['intelligence_updates'].append({
                'type': 'cache_refreshed',
                'categories_learned': {k: len(v) for k, v in learned.items()}
            })
        
        # Check for declining confidence scores
        low_confidence_products = self._find_low_confidence_products()
        if low_confidence_products:
            report['recommendations'].append({
                'type': 'improve_classification',
                'affected_products': len(low_confidence_products),
                'examples': low_confidence_products[:3]
            })
        
        # Suggest system improvements
        improvements = self._suggest_system_improvements()
        report['recommendations'].extend(improvements)
        
        # Generate report
        self._generate_report(report)
        
        if options['email_report']:
            self._send_email_report(report)
        
        self.stdout.write(self.style.SUCCESS('✅ Maintenance complete!'))

    def _analyze_new_product_patterns(self, new_products):
        """Analyze new products for emerging categories"""
        from collections import Counter
        
        word_frequency = Counter()
        for product in new_products:
            words = product.name.lower().split()
            for word in words:
                if len(word) > 4:  # Substantial words only
                    word_frequency[word] += 1
        
        # Find words that appear in multiple new products
        emerging_patterns = []
        for word, count in word_frequency.most_common(20):
            if count >= 3:  # Appears in at least 3 new products
                similar_products = new_products.filter(name__icontains=word)
                emerging_patterns.append({
                    'pattern': word,
                    'frequency': count,
                    'examples': [p.name for p in similar_products[:2]]
                })
        
        return emerging_patterns

    def _find_low_confidence_products(self):
        """Find products that consistently get low confidence scores"""
        from products.consumer_matching import smart_extract_search_terms_dynamic
        
        sample_products = Product.objects.filter(is_demo=False)[:20]
        low_confidence = []
        
        for product in sample_products:
            try:
                result = smart_extract_search_terms_dynamic(product.name)
                confidence = result.get('confidence', 0)
                if confidence < 0.4:  # Low confidence threshold
                    low_confidence.append({
                        'name': product.name,
                        'confidence': confidence,
                        'detected_type': result.get('type'),
                        'method': result.get('method')
                    })
            except:
                continue
        
        return low_confidence

    def _suggest_system_improvements(self):
        """Suggest specific improvements based on current data"""
        suggestions = []
        
        # Check product count vs category coverage
        total_products = Product.objects.count()
        if total_products > 50000:
            suggestions.append({
                'type': 'scale_improvement',
                'priority': 'high',
                'description': 'Consider machine learning model for 50k+ products',
                'action': 'Implement TF-IDF or BERT-based classification'
            })
        
        # Check for missing categories
        learned = dynamic_intelligence.get_learned_categories()
        cable_indicators = len(learned.get('cable_indicators', []))
        laptop_indicators = len(learned.get('laptop_indicators', []))
        
        if cable_indicators > laptop_indicators * 3:
            suggestions.append({
                'type': 'category_imbalance',
                'priority': 'medium', 
                'description': 'Cable category over-represented vs laptops',
                'action': 'Add more laptop-specific learning patterns'
            })
        
        return suggestions

    def _generate_report(self, report):
        """Generate human-readable report"""
        self.stdout.write('📊 Weekly Intelligence Report:')
        self.stdout.write(f'  • Total products: {report["product_count"]}')
        self.stdout.write(f'  • New products this week: {report["new_products_this_week"]}')
        
        if report['intelligence_updates']:
            self.stdout.write('  • Intelligence updates:')
            for update in report['intelligence_updates']:
                self.stdout.write(f'    - {update["type"]}')
        
        if report['recommendations']:
            self.stdout.write('  • Recommendations:')
            for rec in report['recommendations']:
                self.stdout.write(f'    - {rec["type"]}: {rec.get("description", "N/A")}')

    def _send_email_report(self, report):
        """Send email report to administrators"""
        if hasattr(settings, 'ADMINS') and settings.ADMINS:
            subject = f'TruPrice Intelligence Weekly Report - {datetime.now().strftime("%Y-%m-%d")}'
            message = f"""
            Weekly Product Intelligence Report
            
            Summary:
            - Total products: {report['product_count']}
            - New products this week: {report['new_products_this_week']}
            - Intelligence updates: {len(report['intelligence_updates'])}
            - Recommendations: {len(report['recommendations'])}
            
            Full report: {json.dumps(report, indent=2)}
            """
            
            try:
                admin_emails = [email for name, email in settings.ADMINS]
                send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, admin_emails)
                self.stdout.write('📧 Email report sent')
            except Exception as e:
                self.stdout.write(f'⚠️ Email failed: {e}') 