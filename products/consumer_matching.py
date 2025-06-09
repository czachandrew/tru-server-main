"""
Consumer-Focused Product Matching Strategy - NO AMAZON API VERSION

IMPORTANT CONSTRAINT: No Amazon API access until 100 qualified sales
- Cannot fetch Amazon product data programmatically
- Must rely on puppeteer worker for affiliate link generation
- Strategy: Focus on supplier inventory with Amazon as manual fallback

Based on inventory analysis:
- 99.9% of inventory is B2B/enterprise focused (Synnex supplier)
- Only ~15% consumer tech brands (HP, Intel, etc.) - mostly accessories/parts
- 41% enterprise infrastructure (Panduit, Eaton, APC)
- 19% accessories/cables (StarTech, C2G)

Revised Strategy: Maximize supplier inventory value, create Amazon affiliate links
only when user specifically provides ASIN, focus on cross-selling accessories.
"""

import re
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from products.models import Product
from django.db.models import Q

@dataclass
class ConsumerMatchResult:
    """Result of consumer-focused product matching (No Amazon API version)"""
    primary_recommendation: Optional[Dict] = None  
    supplier_alternatives: List[Dict] = field(default_factory=list)      
    accessory_products: List[Dict] = field(default_factory=list)  # NEW: Separate accessories
    enterprise_alternatives: List[Dict] = field(default_factory=list)     
    search_strategy: str = ""                      
    confidence_score: float = 0.0
    amazon_fallback_suggestion: Optional[str] = None  # Suggest search terms for Amazon

class ConsumerProductMatcher:
    """Enhanced matcher focusing on supplier inventory (No Amazon API)"""
    
    def __init__(self):
        # Categories where we suggest supplier products first
        self.supplier_strong_categories = {
            'cables': ['cable', 'cord', 'adapter', 'connector', 'extension', 'hdmi', 'vga', 'usb cable'],
            'power': ['power supply', 'ups', 'surge protector', 'power cable', 'charger', 'power cord'],
            'mounting': ['mount', 'bracket', 'stand', 'rack', 'holder', 'arm'],
            'networking_enterprise': ['switch', 'router enterprise', 'access point', 'patch panel'],
            'server_parts': ['server', 'raid', 'enterprise ssd', 'rack mount'],
            'laptop_accessories': ['laptop power', 'laptop cable', 'laptop adapter', 'notebook power'],
            'monitor_accessories': ['monitor cable', 'monitor stand', 'display cable', 'monitor mount'],
            'pc_accessories': ['pc cable', 'computer cable', 'desktop power', 'pc adapter']
        }
        
        # Categories where we acknowledge Amazon is better but provide alternatives
        self.amazon_dominant_categories = {
            'laptops': ['laptop', 'notebook', 'macbook', 'thinkpad', 'inspiron', 'pavilion'],
            'desktops': ['desktop computer', 'gaming pc', 'all-in-one', 'imac', 'optiplex'],
            'monitors': ['monitor', 'display', '4k monitor', 'gaming monitor', 'ultrawide'],
            'smartphones': ['iphone', 'samsung galaxy', 'pixel', 'smartphone', 'android'],
            'tablets': ['ipad', 'surface pro', 'tablet', 'kindle fire'],
            'gaming_devices': ['gaming laptop', 'gaming desktop', 'gaming chair', 'gaming headset'],
            'audio_devices': ['headphones', 'earbuds', 'speakers', 'soundbar', 'airpods'],
            'cameras': ['camera', 'dslr', 'mirrorless', 'gopro', 'webcam']
        }
    
    def match_consumer_product(self, search_term: str, asin: str = None) -> ConsumerMatchResult:
        """
        Enhanced matching focusing on supplier inventory
        Only create Amazon affiliate links when ASIN is provided
        """
        result = ConsumerMatchResult()
        
        # Determine search category
        supplier_category = self._categorize_supplier_strength(search_term)
        amazon_category = self._categorize_amazon_dominant(search_term)
        
        if supplier_category:
            # We have strong supplier inventory for this category
            result = self._supplier_focused_strategy(search_term, supplier_category, result)
        elif amazon_category:
            # Amazon-dominant category - focus on accessories we can provide
            result = self._amazon_dominant_with_accessories_strategy(search_term, amazon_category, asin, result)
        else:
            # General search - try supplier first
            result = self._general_supplier_strategy(search_term, asin, result)
        
        return result
    
    def _categorize_supplier_strength(self, search_term: str) -> Optional[str]:
        """Find categories where our supplier inventory is strong"""
        search_lower = search_term.lower()
        
        for category, keywords in self.supplier_strong_categories.items():
            if any(keyword in search_lower for keyword in keywords):
                return category
        return None
    
    def _categorize_amazon_dominant(self, search_term: str) -> Optional[str]:
        """Find categories where Amazon is clearly dominant"""
        search_lower = search_term.lower()
        
        for category, keywords in self.amazon_dominant_categories.items():
            if any(keyword in search_lower for keyword in keywords):
                return category
        return None
    
    def _supplier_focused_strategy(self, search_term: str, category: str, result: ConsumerMatchResult) -> ConsumerMatchResult:
        """Supplier-focused strategy for categories where we have good inventory"""
        result.search_strategy = f"supplier_focused_{category}"
        
        # Search our inventory with enhanced matching
        supplier_products = self._enhanced_supplier_search(search_term)
        
        if supplier_products:
            # Use best supplier match as primary
            best_match = supplier_products[0]
            result.primary_recommendation = {
                'product': best_match,
                'source': 'supplier',
                'match_type': 'direct_supplier_match',
                'confidence': 0.9  # High confidence for our strong categories
            }
            
            # Add alternatives
            result.supplier_alternatives = [
                {'product': p, 'source': 'supplier', 'match_type': 'supplier_alternative'} 
                for p in supplier_products[1:8]
            ]
            result.confidence_score = 0.9
        else:
            # No direct matches - suggest Amazon search
            result.amazon_fallback_suggestion = search_term
            result.confidence_score = 0.3
        
        return result
    
    def _amazon_dominant_with_accessories_strategy(self, search_term: str, category: str, asin: str, result: ConsumerMatchResult) -> ConsumerMatchResult:
        """Strategy for Amazon-dominant categories - focus on accessories we can provide"""
        result.search_strategy = f"amazon_dominant_with_accessories_{category}"
        
        # If ASIN provided, create affiliate link placeholder
        if asin:
            amazon_placeholder = {
                'title': f'Amazon Product - {search_term}',
                'asin': asin,
                'price': 'See Amazon for pricing',
                'detail_page_url': f'https://amazon.com/dp/{asin}',
                'availability': 'Available on Amazon'
            }
            
            result.primary_recommendation = {
                'product': amazon_placeholder,
                'source': 'amazon_affiliate',
                'match_type': 'amazon_affiliate_link',
                'confidence': 0.95  # High confidence when ASIN provided
            }
            result.confidence_score = 0.95
        else:
            # No ASIN - suggest Amazon search but don't create placeholder
            result.amazon_fallback_suggestion = search_term
            result.confidence_score = 0.6
        
        # SEPARATE: Demo product alternatives vs accessories
        demo_alternatives = []
        accessory_products = []
        
        # 1. First, search for demo product alternatives (laptops for laptops, etc.)
        if category in ['laptops', 'desktops', 'monitors', 'gaming_devices']:
            # For device categories, search for demo products with related terms
            device_search_terms = {
                'laptops': 'laptop macbook notebook',
                'desktops': 'desktop computer pc',
                'monitors': 'monitor display screen',
                'gaming_devices': 'gaming laptop desktop'
            }.get(category, search_term)
            
            demo_products = self._enhanced_supplier_search(device_search_terms)
            
            # Add ONLY demo products as alternatives (actual competing products)
            for product in demo_products[:3]:  # Limit to top 3 demo alternatives
                if product.is_demo and self._is_actual_alternative(product, category):
                    demo_alternatives.append({
                        'product': product, 
                        'source': 'supplier', 
                        'match_type': f'{category}_demo_alternative'
                    })
        
        # 2. Then search for relevant accessories (cables, power supplies, etc.)
        accessory_products = self._find_relevant_accessories(search_term, category)
        
        # IMPORTANT: Keep alternatives and accessories separate
        result.supplier_alternatives = demo_alternatives  # Only actual alternatives
        result.accessory_products = accessory_products    # Keep accessories separate
        
        return result
    
    def _general_supplier_strategy(self, search_term: str, asin: str, result: ConsumerMatchResult) -> ConsumerMatchResult:
        """General strategy - try supplier first, Amazon as fallback"""
        result.search_strategy = "general_supplier_first"
        
        # Search supplier inventory
        supplier_products = self._enhanced_supplier_search(search_term)
        
        if supplier_products:
            # Found supplier products
            result.primary_recommendation = {
                'product': supplier_products[0],
                'source': 'supplier',
                'match_type': 'general_supplier_match',
                'confidence': 0.7
            }
            result.supplier_alternatives = [
                {'product': p, 'source': 'supplier', 'match_type': 'supplier_alternative'}
                for p in supplier_products[1:6]
            ]
            result.confidence_score = 0.7
        elif asin:
            # No supplier products but ASIN provided
            amazon_placeholder = {
                'title': f'Amazon Product - {search_term}',
                'asin': asin,
                'price': 'See Amazon for pricing',
                'detail_page_url': f'https://amazon.com/dp/{asin}',
                'availability': 'Available on Amazon'
            }
            
            result.primary_recommendation = {
                'product': amazon_placeholder,
                'source': 'amazon_affiliate',
                'match_type': 'amazon_fallback',
                'confidence': 0.8
            }
            result.confidence_score = 0.8
        else:
            # No products found, suggest Amazon search
            result.amazon_fallback_suggestion = search_term
            result.confidence_score = 0.4
        
        return result
    
    def _enhanced_supplier_search(self, search_term: str) -> List[Product]:
        """Enhanced search across multiple strategies to find the best supplier matches"""
        
        print(f"🔍 ENHANCED SEARCH: Starting search with term: '{search_term}'")
        
        all_results = []
        
        # Strategy 1: Demo products (high priority for alternatives)
        demo_products = self._demo_product_search(search_term)
        for product in demo_products:
            all_results.append((product, 'demo_product', 10))  # High score for demo products
        
        # Strategy 2: Consumer-relevant description mining
        consumer_products = self._consumer_description_mining(search_term)
        for product in consumer_products:
            if product not in [r[0] for r in all_results]:
                all_results.append((product, 'consumer_description', 8))
        
        # Strategy 3: Exact part number matches
        part_matches = self._exact_part_search(search_term)
        for product in part_matches:
            if product not in [r[0] for r in all_results]:
                all_results.append((product, 'exact_part', 9))
        
        # Strategy 4: Weighted description search
        desc_matches = self._weighted_description_search(search_term)
        for product in desc_matches:
            if product not in [r[0] for r in all_results]:
                all_results.append((product, 'weighted_description', 7))
        
        # Strategy 5: Fuzzy name search
        name_matches = self._fuzzy_name_search(search_term)
        for product in name_matches:
            if product not in [r[0] for r in all_results]:
                all_results.append((product, 'fuzzy_name', 6))
        
        # Sort by score (highest first) and return products
        all_results.sort(key=lambda x: x[2], reverse=True)
        results = [result[0] for result in all_results]
        
        # Exclude accessories from main search results 
        filtered_results = []
        for product in results:
            if not self._is_accessory_product(product):
                filtered_results.append(product)
            if len(filtered_results) >= 15:
                break
        
        print(f"🔍 ENHANCED SEARCH: Found {len(filtered_results)} non-accessory products")
        for i, product in enumerate(filtered_results[:5]):
            print(f"  {i+1}. {product.name} (Demo: {product.is_demo}) (Part: {product.part_number})")
        
        return filtered_results
    
    def _demo_product_search(self, search_term: str) -> List[Product]:
        """Search demo products that are contextually relevant to the search term"""
        if not search_term:
            return []
        
        print(f"🔍 DEMO SEARCH: Searching for demo products with term: '{search_term}'")
        
        search_lower = search_term.lower()
        
        # CONTEXTUAL RELEVANCE: Only return demo products if the search is actually for similar products
        # Define strict product category contexts
        laptop_contexts = [
            'macbook', 'laptop', 'notebook', 'ultrabook', 'thinkpad', 'dell latitude', 
            'hp elitebook', 'lenovo', 'business laptop', 'portable computer'
        ]
        
        desktop_contexts = [
            'desktop', 'workstation', 'pc', 'computer tower', 'all-in-one'
        ]
        
        # Exclude accessory searches - these should NOT get laptop alternatives
        accessory_exclusions = [
            'cable', 'cord', 'power', 'adapter', 'charger', 'mount', 'bracket',
            'stand', 'case', 'cover', 'connector', 'extension', 'hub', 'splitter',
            'hdmi', 'usb', 'ethernet', 'vga', 'dvi', 'audio', 'speaker', 'mouse', 'keyboard'
        ]
        
        # Check if this is an accessory search - if so, return no demo products
        for exclusion in accessory_exclusions:
            if exclusion in search_lower:
                print(f"🔍 DEMO SEARCH: Skipping demo products - detected accessory search: '{exclusion}'")
                return []
        
        # Determine if this is a laptop-related search
        is_laptop_context = any(context in search_lower for context in laptop_contexts)
        is_desktop_context = any(context in search_lower for context in desktop_contexts)
        
        if not (is_laptop_context or is_desktop_context):
            print(f"🔍 DEMO SEARCH: No relevant product context found - skipping demo products")
            return []
        
        # Build contextual query for demo products
        query = Q(is_demo=True)
        
        if is_laptop_context:
            # Only return laptop demo products for laptop searches
            laptop_query = Q()
            laptop_terms = ['macbook', 'laptop', 'notebook', 'ultrabook', 'elitebook', 'latitude']
            for term in laptop_terms:
                laptop_query |= Q(name__icontains=term)
                laptop_query |= Q(description__icontains=term)
            query &= laptop_query
            print(f"🔍 DEMO SEARCH: Looking for laptop demo products")
            
        elif is_desktop_context:
            # Only return desktop demo products for desktop searches
            desktop_query = Q()
            desktop_terms = ['desktop', 'workstation', 'pc', 'tower']
            for term in desktop_terms:
                desktop_query |= Q(name__icontains=term)
                desktop_query |= Q(description__icontains=term)
            query &= desktop_query
            print(f"🔍 DEMO SEARCH: Looking for desktop demo products")
        
        demo_products = list(Product.objects.filter(query)[:5])
        print(f"🔍 DEMO SEARCH: Found {len(demo_products)} contextually relevant demo products")
        for product in demo_products:
            print(f"  - {product.name} (Part: {product.part_number})")
        
        return demo_products
    
    def _consumer_description_mining(self, search_term: str) -> List[Product]:
        """Mine descriptions for consumer product references"""
        search_terms = search_term.lower().split()
        
        # Look for products that mention consumer brands/models in descriptions
        consumer_indicators = [
            'hp', 'dell', 'lenovo', 'asus', 'acer', 'microsoft', 'apple', 'intel', 'amd',
            'gaming', 'laptop', 'desktop', 'notebook', 'monitor', 'display'
        ]
        
        query = Q()
        
        # Build query for consumer-related descriptions
        for term in search_terms:
            if len(term) > 2:
                query |= Q(description__icontains=term)
        
        # Boost products that mention consumer indicators
        for indicator in consumer_indicators:
            if any(indicator in term.lower() for term in search_terms):
                query |= Q(description__icontains=indicator)
        
        # Include both partner imports AND manual/demo products
        return list(Product.objects.filter(query).filter(Q(source='partner_import') | Q(source='manual'))[:8])
    
    def _weighted_description_search(self, search_term: str) -> List[Product]:
        """Enhanced description search with keyword weighting"""
        keywords = search_term.lower().split()
        
        # Filter out stop words
        stop_words = {'the', 'and', 'or', 'for', 'with', 'by', 'in', 'on', 'at', 'a', 'an'}
        keywords = [k for k in keywords if k not in stop_words and len(k) > 2]
        
        if not keywords:
            return []
        
        # Use AND logic for multiple keywords (more precise)
        query = Q()
        for keyword in keywords:
            query &= Q(description__icontains=keyword)
        
        # Include both partner imports AND manual/demo products
        return list(Product.objects.filter(query).filter(Q(source='partner_import') | Q(source='manual'))[:10])
    
    def _exact_part_search(self, search_term: str) -> List[Product]:
        """Search for exact part number matches with enhanced extraction"""
        # Extract potential part numbers (more aggressive pattern)
        part_patterns = [
            r'\b[A-Z]{2,5}[-_]?[0-9]{3,8}[A-Z]{0,3}\b',  # Common part number formats
            r'\b[0-9]{3,5}[-_]?[A-Z]{2,5}\b',             # Numeric-alpha patterns
            r'\b[A-Z0-9\-_]{6,15}\b'                      # General alphanumeric codes
        ]
        
        potential_parts = []
        search_upper = search_term.upper()
        
        for pattern in part_patterns:
            matches = re.findall(pattern, search_upper)
            potential_parts.extend(matches)
        
        if not potential_parts:
            return []
        
        query = Q()
        for part in potential_parts:
            query |= Q(part_number__icontains=part)
            query |= Q(name__icontains=part)
            query |= Q(description__icontains=part)
        
        # Include both partner imports AND manual/demo products
        return list(Product.objects.filter(query).filter(Q(source='partner_import') | Q(source='manual'))[:5])
    
    def _fuzzy_name_search(self, search_term: str) -> List[Product]:
        """Fuzzy search on product names with stemming"""
        keywords = search_term.lower().split()[:4]  # First 4 words
        
        query = Q()
        for keyword in keywords:
            if len(keyword) > 2:
                query |= Q(name__icontains=keyword)
        
        # Include both partner imports AND manual/demo products
        return list(Product.objects.filter(query).filter(Q(source='partner_import') | Q(source='manual'))[:5])
    
    def _find_relevant_accessories(self, search_term: str, category: str) -> List[Dict]:
        """Find accessories relevant to the main product category"""
        accessory_mapping = {
            'laptops': ['laptop power', 'laptop cable', 'laptop adapter', 'notebook power', 'laptop charger'],
            'desktops': ['pc power', 'computer cable', 'desktop power', 'pc adapter'],
            'monitors': ['monitor cable', 'hdmi cable', 'vga cable', 'display cable', 'monitor mount'],
            'gaming_devices': ['gaming cable', 'gaming power', 'gaming adapter'],
            'smartphones': ['phone charger', 'usb cable', 'phone adapter'],
            'tablets': ['tablet charger', 'tablet cable', 'tablet adapter']
        }
        
        accessory_terms = accessory_mapping.get(category, ['cable', 'adapter', 'power'])
        
        query = Q()
        for term in accessory_terms:
            query |= Q(description__icontains=term)
        
        # Only get products that are clearly accessories
        products = Product.objects.filter(query, source='partner_import')[:6]
        
        return [
            {'product': p, 'source': 'supplier', 'match_type': f'{category}_accessory'} 
            for p in products
        ]

    def _is_actual_alternative(self, product: Product, category: str) -> bool:
        """
        Determine if a product is actually an alternative (competing product) 
        rather than an accessory or unrelated item
        """
        product_name = product.name.lower()
        product_desc = (product.description or "").lower()
        
        print(f"🔍 CHECKING ALTERNATIVE: {product.name}")
        print(f"  Category: {category}")
        print(f"  Name: '{product_name}'")
        print(f"  Description: '{product_desc[:100]}...'")
        
        # Define what constitutes actual alternatives for each category
        alternative_indicators = {
            'laptops': ['laptop', 'notebook', 'macbook', 'thinkpad', 'inspiron', 'pavilion', 'ultrabook', 'elitebook', 'latitude', 'xps'],
            'desktops': ['desktop', 'pc', 'workstation', 'computer', 'imac', 'optiplex', 'all-in-one'],
            'monitors': ['monitor', 'display', 'screen'],
            'gaming_devices': ['gaming laptop', 'gaming desktop', 'gaming pc']
        }
        
        # Define what are clearly accessories (should NOT be alternatives)
        accessory_indicators = [
            'cable', 'cord', 'power', 'adapter', 'charger', 'mount', 'bracket',
            'stand', 'case', 'cover', 'connector', 'extension', 'hub', 'splitter'
        ]
        
        # Check if this is clearly an accessory
        for accessory_term in accessory_indicators:
            if accessory_term in product_name or accessory_term in product_desc:
                print(f"  ❌ REJECTED: Contains accessory term '{accessory_term}'")
                return False  # This is an accessory, not an alternative
        
        # Check if this is actually an alternative for the category
        category_alternatives = alternative_indicators.get(category, [])
        for alt_term in category_alternatives:
            if alt_term in product_name or alt_term in product_desc:
                print(f"  ✅ ACCEPTED: Contains alternative term '{alt_term}'")
                return True  # This is an actual alternative
        
        # Special case: For demo products, be more lenient
        if hasattr(product, 'is_demo') and product.is_demo:
            print(f"  ✅ ACCEPTED: Demo product (overriding strict matching)")
            return True
        
        print(f"  ❌ REJECTED: No matching alternative terms found")
        return False

    def _is_accessory_product(self, product: Product) -> bool:
        """Check if a product is an accessory (cable, adapter, etc.)"""
        product_name = product.name.lower()
        product_desc = (product.description or "").lower()
        
        accessory_keywords = [
            'cable', 'cord', 'adapter', 'charger', 'power supply', 'mount', 'bracket',
            'stand', 'case', 'cover', 'connector', 'extension', 'hub', 'splitter'
        ]
        
        return any(keyword in product_name or keyword in product_desc 
                  for keyword in accessory_keywords)

# Updated integration function
def get_consumer_focused_results(search_term: str, asin: str = None) -> Dict:
    """
    Main interface for consumer-focused product matching (No Amazon API version)
    Focuses on supplier inventory with Amazon affiliate links only when ASIN provided
    Returns enhanced relationship classification for better UI display
    """
    matcher = ConsumerProductMatcher()
    result = matcher.match_consumer_product(search_term, asin)
    
    # Format for GraphQL response with enhanced relationship data
    formatted_results = []
    
    # Add primary recommendation
    if result.primary_recommendation:
        product = result.primary_recommendation['product']
        source = result.primary_recommendation['source']
        match_type = result.primary_recommendation['match_type']
        confidence = result.primary_recommendation['confidence']
        
        # Determine enhanced relationship fields
        relationship_data = _determine_enhanced_relationship(match_type, source, is_primary=True)
        
        formatted_results.append({
            'product': product,
            'matchType': match_type,
            'matchConfidence': confidence,
            'isAmazonProduct': source == 'amazon_affiliate',
            'isAlternative': False,
            # Enhanced fields
            'relationshipType': relationship_data['relationship_type'],
            'relationshipCategory': relationship_data['relationship_category'],
            'marginOpportunity': relationship_data['margin_opportunity'],
            'revenueType': relationship_data['revenue_type']
        })
    
    # Add supplier alternatives with enhanced classification
    for alt in (result.supplier_alternatives or []):
        product = alt['product']
        source = alt['source']
        match_type = alt['match_type']
        
        # Use the new classification function to determine relationship
        relationship_data = _classify_product_relationship(product, search_term)
        
        formatted_results.append({
            'product': product,
            'matchType': match_type,
            'matchConfidence': 0.7,
            'isAmazonProduct': False,
            'isAlternative': True,  # These are actual alternatives (competing products)
            # Enhanced fields
            'relationshipType': relationship_data['relationship_type'],
            'relationshipCategory': relationship_data['relationship_category'],
            'marginOpportunity': relationship_data['margin_opportunity'],
            'revenueType': relationship_data['revenue_type']
        })
    
    # Add accessory products separately (NOT as alternatives)
    for accessory in (getattr(result, 'accessory_products', []) or []):
        product = accessory['product']
        source = accessory['source']
        match_type = accessory['match_type']
        
        # Force accessory classification
        formatted_results.append({
            'product': product,
            'matchType': match_type,
            'matchConfidence': 0.6,
            'isAmazonProduct': False,
            'isAlternative': False,  # Accessories are NOT alternatives
            # Enhanced fields for accessories
            'relationshipType': 'accessory',
            'relationshipCategory': match_type,  # e.g., 'laptop_accessory'
            'marginOpportunity': 'high',
            'revenueType': 'cross_sell_opportunity'
        })
    
    response = {
        'results': formatted_results,
        'searchStrategy': result.search_strategy,
        'overallConfidence': result.confidence_score
    }
    
    # Add Amazon fallback suggestion if no direct results
    if result.amazon_fallback_suggestion:
        response['amazonFallbackSuggestion'] = result.amazon_fallback_suggestion
    
    return response 

def _determine_enhanced_relationship(match_type: str, source: str, is_primary: bool) -> Dict[str, str]:
    """
    Map match types to enhanced relationship classification
    
    Returns enhanced relationship data for better UI display and business logic
    """
    
    # Amazon products
    if source == 'amazon_affiliate':
        return {
            'relationship_type': 'primary' if is_primary else 'alternative',
            'relationship_category': 'amazon_affiliate',
            'margin_opportunity': 'affiliate_only',
            'revenue_type': 'affiliate_commission'
        }
    
    # Primary supplier matches
    if is_primary and source == 'supplier':
        if 'direct' in match_type or 'exact' in match_type:
            return {
                'relationship_type': 'primary',
                'relationship_category': 'exact_supplier_match',
                'margin_opportunity': 'high',
                'revenue_type': 'product_sale'
            }
        else:
            return {
                'relationship_type': 'primary',
                'relationship_category': 'supplier_match',
                'margin_opportunity': 'medium',
                'revenue_type': 'product_sale'
            }
    
    # Supplier alternatives and accessories
    if source == 'supplier':
        # Accessory products (cables, mounts, power supplies)
        if any(accessory in match_type for accessory in ['accessory', 'cable', 'power', 'mount']):
            return {
                'relationship_type': 'accessory',
                'relationship_category': match_type,  # e.g., 'laptop_accessory', 'monitor_cable'
                'margin_opportunity': 'high',
                'revenue_type': 'cross_sell_opportunity'
            }
        
        # Direct alternatives (similar products)
        elif 'alternative' in match_type:
            return {
                'relationship_type': 'equivalent',
                'relationship_category': 'supplier_alternative',
                'margin_opportunity': 'medium',
                'revenue_type': 'product_sale'
            }
        
        # Enterprise-grade alternatives
        elif 'enterprise' in match_type:
            return {
                'relationship_type': 'enterprise_alternative',
                'relationship_category': 'enterprise_grade',
                'margin_opportunity': 'high',
                'revenue_type': 'product_sale'
            }
    
    # Default fallback
    return {
        'relationship_type': 'related',
        'relationship_category': 'general_match',
        'margin_opportunity': 'medium',
        'revenue_type': 'product_sale'
    }

def _classify_product_relationship(product: Product, search_context: str) -> Dict[str, str]:
    """
    Classify the relationship of a product to the search context
    This function determines if something is an accessory, alternative, or unrelated
    """
    product_name = product.name.lower()
    product_desc = (product.description or "").lower()
    search_lower = search_context.lower()
    
    # Accessory indicators
    accessory_keywords = [
        'cable', 'cord', 'adapter', 'charger', 'power supply', 'mount', 'bracket', 
        'stand', 'case', 'cover', 'protector', 'connector', 'extension', 'hub',
        'splitter', 'switch', 'surge protector', 'ups', 'battery', 'keystone',
        'jack', 'plug', 'socket', 'outlet'
    ]
    
    # Alternative product indicators (actual competing products)
    alternative_keywords = [
        'laptop', 'notebook', 'desktop', 'computer', 'monitor', 'display', 
        'keyboard', 'mouse', 'tablet', 'phone', 'printer', 'scanner',
        'router', 'modem', 'server', 'workstation'
    ]
    
    # Check if this is clearly an accessory
    is_accessory = any(keyword in product_name or keyword in product_desc 
                      for keyword in accessory_keywords)
    
    # Check if this is a competing product
    is_alternative = any(keyword in product_name or keyword in product_desc 
                        for keyword in alternative_keywords)
    
    # Special case: If searching for a laptop and finding a cable, it's an accessory
    if any(device in search_lower for device in ['laptop', 'macbook', 'notebook', 'computer']):
        if is_accessory:
            return {
                'relationship_type': 'accessory',
                'relationship_category': 'laptop_accessory',
                'margin_opportunity': 'high',
                'revenue_type': 'cross_sell_opportunity'
            }
        elif is_alternative:
            return {
                'relationship_type': 'equivalent', 
                'relationship_category': 'laptop_alternative',
                'margin_opportunity': 'medium',
                'revenue_type': 'product_sale'
            }
    
    # Default: If it's clearly an accessory, mark as such
    if is_accessory:
        return {
            'relationship_type': 'accessory',
            'relationship_category': 'general_accessory',
            'margin_opportunity': 'high',
            'revenue_type': 'cross_sell_opportunity'
        }
    
    # If it's an alternative product, mark as equivalent
    if is_alternative:
        return {
            'relationship_type': 'equivalent',
            'relationship_category': 'product_alternative', 
            'margin_opportunity': 'medium',
            'revenue_type': 'product_sale'
        }
    
    # Default: Related but unclear relationship
    return {
        'relationship_type': 'related',
        'relationship_category': 'unclear_match',
        'margin_opportunity': 'low',
        'revenue_type': 'product_sale'
    } 

def smart_extract_search_terms(product_name: str) -> Dict[str, any]:
    """
    Intelligently extract clean search terms from verbose Amazon product names
    Returns structured data about the product type and relevant search terms
    """
    name_lower = product_name.lower()
    
    # Step 1: Identify core product type
    product_types = {
        'laptop': ['macbook', 'laptop', 'notebook', 'ultrabook', 'thinkpad', 'chromebook'],
        'desktop': ['desktop', 'pc', 'workstation', 'all-in-one', 'imac', 'mini pc'],
        'monitor': ['monitor', 'display', 'screen', 'lcd', 'led', 'oled'],
        'cable': ['cable', 'cord', 'wire'],
        'adapter': ['adapter', 'converter', 'dongle', 'hub'],
        'power': ['charger', 'power supply', 'power adapter', 'psu'],
        'storage': ['ssd', 'hard drive', 'hdd', 'nvme', 'storage'],
        'networking': ['router', 'modem', 'switch', 'access point', 'wifi'],
        'audio': ['headphones', 'speakers', 'soundbar', 'earbuds', 'microphone'],
        'gaming': ['gaming', 'xbox', 'playstation', 'nintendo', 'steam deck'],
        'phone': ['iphone', 'samsung', 'pixel', 'smartphone', 'phone'],
        'tablet': ['ipad', 'tablet', 'kindle', 'surface']
    }
    
    detected_type = None
    for product_type, keywords in product_types.items():
        if any(keyword in name_lower for keyword in keywords):
            detected_type = product_type
            break
    
    # Step 2: Extract specific product identifiers
    # HDMI cables
    if 'hdmi' in name_lower:
        detected_type = 'cable'
        version = re.search(r'hdmi\s*(\d+\.?\d*)', name_lower)
        return {
            'type': 'cable',
            'subtype': 'hdmi',
            'version': version.group(1) if version else None,
            'clean_terms': ['hdmi', 'cable'],
            'technical_specs': extract_cable_specs(name_lower)
        }
    
    # USB cables/adapters
    elif 'usb' in name_lower:
        detected_type = 'adapter' if 'adapter' in name_lower else 'cable'
        usb_version = re.search(r'usb[-\s]*([c3-9]|3\.0|2\.0)', name_lower)
        return {
            'type': detected_type,
            'subtype': 'usb',
            'version': usb_version.group(1) if usb_version else None,
            'clean_terms': ['usb', detected_type],
            'technical_specs': extract_cable_specs(name_lower)
        }
    
    # MacBooks (special handling)
    elif 'macbook' in name_lower:
        model = 'pro' if 'pro' in name_lower else 'air' if 'air' in name_lower else None
        size = re.search(r'(\d+)[-\s]*inch', name_lower)
        return {
            'type': 'laptop',
            'subtype': 'macbook',
            'model': model,
            'size': size.group(1) if size else None,
            'clean_terms': ['macbook', model, 'laptop'] if model else ['macbook', 'laptop'],
            'technical_specs': extract_laptop_specs(name_lower)
        }
    
    # Laptops (general)
    elif detected_type == 'laptop':
        brand = extract_brand(name_lower, ['dell', 'hp', 'lenovo', 'asus', 'acer', 'msi', 'alienware'])
        size = re.search(r'(\d+)[-\s]*inch', name_lower)
        return {
            'type': 'laptop',
            'subtype': brand if brand else 'generic',
            'size': size.group(1) if size else None,
            'clean_terms': [term for term in ['laptop', 'notebook', brand] if term],
            'technical_specs': extract_laptop_specs(name_lower)
        }
    
    # Monitors
    elif detected_type == 'monitor':
        size = re.search(r'(\d+)[-\s]*inch', name_lower)
        resolution = extract_resolution(name_lower)
        return {
            'type': 'monitor',
            'subtype': 'display',
            'size': size.group(1) if size else None,
            'resolution': resolution,
            'clean_terms': ['monitor', 'display', 'screen'],
            'technical_specs': {'size': size.group(1) if size else None, 'resolution': resolution}
        }
    
    # Fallback: extract key terms and clean them
    else:
        clean_terms = extract_clean_terms(product_name)
        return {
            'type': detected_type or 'unknown',
            'subtype': None,
            'clean_terms': clean_terms,
            'technical_specs': {},
            'original_name': product_name[:50] + '...' if len(product_name) > 50 else product_name
        }

def extract_cable_specs(name_lower: str) -> Dict[str, str]:
    """Extract technical specs relevant to cables"""
    specs = {}
    
    # Length
    length = re.search(r'(\d+(?:\.\d+)?)\s*(?:ft|feet|foot|meter|m)\b', name_lower)
    if length:
        specs['length'] = length.group(1)
    
    # Speed/bandwidth
    speed = re.search(r'(\d+)\s*gbps', name_lower)
    if speed:
        specs['speed'] = speed.group(1)
    
    # Resolution support
    if '4k' in name_lower:
        specs['resolution'] = '4k'
    elif '8k' in name_lower:
        specs['resolution'] = '8k'
    
    return specs

def extract_laptop_specs(name_lower: str) -> Dict[str, str]:
    """Extract technical specs relevant to laptops"""
    specs = {}
    
    # Screen size
    size = re.search(r'(\d+)[-\s]*inch', name_lower)
    if size:
        specs['screen_size'] = size.group(1)
    
    # Processor
    if 'm1' in name_lower or 'm2' in name_lower:
        specs['processor'] = 'm1' if 'm1' in name_lower else 'm2'
    elif 'intel' in name_lower:
        specs['processor'] = 'intel'
    elif 'amd' in name_lower:
        specs['processor'] = 'amd'
    
    return specs

def extract_resolution(name_lower: str) -> Optional[str]:
    """Extract display resolution"""
    if '4k' in name_lower or '3840' in name_lower:
        return '4k'
    elif '1440p' in name_lower or '2560' in name_lower:
        return '1440p'
    elif '1080p' in name_lower or '1920' in name_lower:
        return '1080p'
    return None

def extract_brand(name_lower: str, brand_list: List[str]) -> Optional[str]:
    """Extract brand name from product name"""
    for brand in brand_list:
        if brand in name_lower:
            return brand
    return None

def extract_clean_terms(product_name: str) -> List[str]:
    """Extract clean, relevant terms from any product name"""
    name_lower = product_name.lower()
    
    # Remove marketing fluff
    marketing_noise = [
        'certified', 'premium', 'ultra', 'high speed', 'professional', 'pro', 'max',
        'upgrade', 'enhanced', 'advanced', 'superior', 'quality', 'durable',
        'compatible', 'support', 'supports', 'perfect', 'ideal', 'best',
        'new', 'latest', 'improved', 'optimized', 'designed'
    ]
    
    # Remove brackets and parentheses content (usually specs/marketing)
    clean_name = re.sub(r'\[.*?\]|\(.*?\)', '', name_lower)
    
    # Remove marketing noise
    for noise in marketing_noise:
        clean_name = clean_name.replace(noise, ' ')
    
    # Extract meaningful words (3+ characters, not numbers-only)
    words = re.findall(r'\b[a-z]{3,}\b', clean_name)
    
    # Remove stop words
    stop_words = {'the', 'and', 'for', 'with', 'from', 'this', 'that', 'are', 'you', 'your'}
    meaningful_words = [word for word in words if word not in stop_words]
    
    # Return top 5 most relevant terms
    return meaningful_words[:5] 