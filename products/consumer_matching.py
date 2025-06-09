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
from collections import Counter
from functools import lru_cache
import pickle
import os
from django.conf import settings
from django.core.cache import cache

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

@dataclass 
class ProductSpecs:
    """Extracted product specifications for relevance scoring"""
    length: Optional[float] = None  # Cable length in feet
    price: Optional[float] = None   # Price from offers
    resolution: Optional[str] = None  # 4K, 8K, 1080p
    speed: Optional[str] = None     # 48Gbps, etc.
    version: Optional[str] = None   # HDMI 2.1, USB 3.0, etc.
    features: List[str] = field(default_factory=list)  # HDR, eARC, etc.

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
        
        # Strategy 2: IMPROVED Cable-specific search
        if any(cable_term in search_term.lower() for cable_term in ['hdmi cable', 'usb cable', 'cable', 'cord']):
            cable_products = self._precise_cable_search(search_term)
            for product in cable_products:
                if product not in [r[0] for r in all_results]:
                    all_results.append((product, 'precise_cable', 9))  # High score for precise cable matches
        
        # Strategy 3: Consumer-relevant description mining
        consumer_products = self._consumer_description_mining(search_term)
        for product in consumer_products:
            if product not in [r[0] for r in all_results]:
                all_results.append((product, 'consumer_description', 8))
        
        # Strategy 4: Exact part number matches
        part_matches = self._exact_part_search(search_term)
        for product in part_matches:
            if product not in [r[0] for r in all_results]:
                all_results.append((product, 'exact_part', 9))
        
        # Strategy 5: Weighted description search
        desc_matches = self._weighted_description_search(search_term)
        for product in desc_matches:
            if product not in [r[0] for r in all_results]:
                all_results.append((product, 'weighted_description', 7))
        
        # Strategy 6: Fuzzy name search
        name_matches = self._fuzzy_name_search(search_term)
        for product in name_matches:
            if product not in [r[0] for r in all_results]:
                all_results.append((product, 'fuzzy_name', 6))
        
        # SMART RELEVANCE SCORING: Re-rank based on specifications
        print(f"🧠 SMART RANKING: Applying relevance scoring...")
        
        # Extract reference specs from search term or use matcher's reference specs
        reference_specs = getattr(self, '_reference_specs', ProductSpecs())
        search_lower = search_term.lower()
        
        # If no reference specs provided, try to infer from search term
        if not reference_specs.length and not reference_specs.price:
            # Try to extract reference specs from search term
            if 'hdmi' in search_lower and 'cable' in search_lower:
                # Default HDMI cable assumptions (budget range)
                reference_specs.length = 6.0  # Typical short cable
                reference_specs.price = 15.0  # Budget price range
                reference_specs.resolution = '4k'
                reference_specs.features = ['hdr']
                print(f"🔧 Using default HDMI reference specs: {reference_specs.length}ft, ${reference_specs.price}")
            elif 'usb' in search_lower and 'cable' in search_lower:
                reference_specs.length = 3.0  # Typical USB cable
                reference_specs.price = 12.0  # Budget USB cable
                print(f"🔧 Using default USB reference specs: {reference_specs.length}ft, ${reference_specs.price}")
        
        # Calculate relevance scores for all results
        scored_results = []
        for product, match_type, base_score in all_results:
            candidate_specs = extract_product_specs(product)
            
            # Calculate smart relevance score
            relevance_score = calculate_relevance_score(reference_specs, candidate_specs, base_score)
            
            print(f"  📊 {product.name[:50]}...")
            print(f"      Base: {base_score:.1f}, Relevance: {relevance_score:.2f}")
            print(f"      Price: ${candidate_specs.price or 'N/A'}, Length: {candidate_specs.length or 'N/A'}ft")
            
            scored_results.append((product, match_type, relevance_score))
        
        # Sort by relevance score (highest first)
        scored_results.sort(key=lambda x: x[2], reverse=True)
        results = [result[0] for result in scored_results]
        
        # Apply better filtering for accessory searches
        if any(accessory_term in search_term.lower() for accessory_term in ['cable', 'cord', 'adapter']):
            # For accessory searches, be more strict about what we include
            filtered_results = self._filter_accessory_results(results, search_term)
        else:
            # For device searches, exclude accessories from main search results 
            filtered_results = []
            for product in results:
                if not self._is_accessory_product(product):
                    filtered_results.append(product)
                if len(filtered_results) >= 15:
                    break
        
        print(f"🔍 ENHANCED SEARCH: Found {len(filtered_results)} filtered products with smart ranking")
        for i, product in enumerate(filtered_results[:5]):
            specs = extract_product_specs(product)
            print(f"  {i+1}. {product.name} (${specs.price or 'N/A'}) ({specs.length or '?'}ft)")
        
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

    def _precise_cable_search(self, search_term: str) -> List[Product]:
        """Precise search specifically for cables, excluding adapters and devices"""
        search_lower = search_term.lower()
        
        print(f"🔌 PRECISE CABLE SEARCH: Looking for cables with term: '{search_term}'")
        
        # Define what we're looking for
        cable_indicators = []
        if 'hdmi' in search_lower:
            cable_indicators = ['hdmi']
        elif 'usb' in search_lower:
            cable_indicators = ['usb']
        elif 'ethernet' in search_lower:
            cable_indicators = ['ethernet', 'cat5', 'cat6']
        elif 'power' in search_lower:
            cable_indicators = ['power cord', 'power cable']
        
        if not cable_indicators:
            return []
        
        # Build query for actual cables
        query = Q()
        for indicator in cable_indicators:
            # Include products that clearly indicate they are cables
            cable_terms = Q(name__icontains=f'{indicator} cable') | Q(name__icontains=f'{indicator} cord')
            
            # ENHANCED: Search part numbers for multiple cable patterns
            part_terms = (
                Q(part_number__icontains=f'{indicator}-cable') | 
                Q(part_number__icontains=f'{indicator}cable') |
                Q(part_number__icontains=f'{indicator}2-cable') |  # Pattern like HDMI2-CABLE
                Q(part_number__icontains=f'{indicator}_cable')
            )
            
            query |= (cable_terms | part_terms)
        
        # EXCLUDE products that are clearly NOT cables
        exclusion_terms = [
            'monitor', 'display', 'tv', 'television', 'screen',  # Devices with HDMI ports
            'adapter', 'converter', 'splitter', 'switch',       # Adapters/converters  
            'extender', 'repeater', 'booster',                  # Signal devices
            'mount', 'bracket', 'stand'                         # Mounting hardware
        ]
        
        exclude_query = Q()
        for term in exclusion_terms:
            exclude_query |= Q(name__icontains=term)
        
        # Find products
        cable_products = Product.objects.filter(query).exclude(exclude_query)[:10]
        
        print(f"🔌 PRECISE CABLE SEARCH: Found {cable_products.count()} potential cable products")
        for product in cable_products:
            print(f"  - {product.name} (Part: {product.part_number})")
        
        return list(cable_products)
    
    def _filter_accessory_results(self, products: List[Product], search_term: str) -> List[Product]:
        """Filter accessory search results to be more relevant"""
        search_lower = search_term.lower()
        filtered = []
        
        for product in products:
            product_name = product.name.lower()
            
            # For HDMI searches, prioritize actual cables
            if 'hdmi' in search_lower:
                # INCLUDE: Products that are clearly HDMI cables
                if ('hdmi' in product_name and 
                    any(cable_term in product_name for cable_term in ['cable', 'cord']) and
                    not any(exclude_term in product_name for exclude_term in ['adapter', 'converter', 'dvi', 'vga', 'monitor', 'tv'])):
                    filtered.append(product)
                    continue
                
                # INCLUDE: HDMI products with cable in part number
                if 'hdmi' in product.part_number.lower() and 'cable' in product.part_number.lower():
                    filtered.append(product)
                    continue
            
            # For USB searches, prioritize USB cables (not adapters)
            elif 'usb' in search_lower:
                if ('usb' in product_name and 
                    any(cable_term in product_name for cable_term in ['cable', 'cord']) and
                    not any(exclude_term in product_name for exclude_term in ['adapter', 'hub', 'charger'])):
                    filtered.append(product)
                    continue
            
            # For general cable searches, include cable-like products
            elif 'cable' in search_lower:
                if any(cable_term in product_name for cable_term in ['cable', 'cord']):
                    filtered.append(product)
                    continue
            
            # Stop when we have enough relevant results
            if len(filtered) >= 10:
                break
        
        print(f"🔍 ACCESSORY FILTER: Filtered to {len(filtered)} relevant products")
        return filtered

# Updated integration function
def get_consumer_focused_results(search_term: str, asin: str = None, reference_product_name: str = None) -> Dict:
    """
    Main interface for consumer-focused product matching (No Amazon API version)
    Focuses on supplier inventory with Amazon affiliate links only when ASIN provided
    Returns enhanced relationship classification for better UI display
    
    Args:
        search_term: The search query (e.g., "hdmi cable")
        asin: Optional Amazon ASIN for affiliate link creation
        reference_product_name: Optional reference product for better matching (e.g., the Silkland cable)
    """
    matcher = ConsumerProductMatcher()
    
    # If reference product provided, extract specs for better matching  
    if reference_product_name:
        # Update the matcher with reference specs for smarter ranking
        matcher._reference_specs = extract_product_specs(None, reference_product_name)
        print(f"📋 REFERENCE PRODUCT: {reference_product_name[:60]}...")
        print(f"   Extracted specs: Length={matcher._reference_specs.length}ft, Price=${matcher._reference_specs.price or 'N/A'}")
    
    result = matcher.match_consumer_product(search_term, asin)
    
    # ADDITIONAL: Search for Amazon alternatives (like ANKER) 
    amazon_alternatives = _search_amazon_alternatives(search_term)
    
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
    
    # Add Amazon alternatives (like ANKER cable)
    for amazon_alt in amazon_alternatives:
        formatted_results.append({
            'product': amazon_alt,
            'matchType': 'amazon_alternative',
            'matchConfidence': 0.8,
            'isAmazonProduct': True,
            'isAlternative': True,
            'relationshipType': 'equivalent',
            'relationshipCategory': 'amazon_alternative',
            'marginOpportunity': 'affiliate_only',
            'revenueType': 'affiliate_commission'
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

def _search_amazon_alternatives(search_term: str) -> List[Dict]:
    """Search for known Amazon alternatives (like ANKER, AmazonBasics, etc.)"""
    # For now, return mock ANKER cable data
    # In production, this would query your Amazon product database or API
    
    if 'hdmi' in search_term.lower():
        return [{
            'name': 'ANKER Ultra High Speed HDMI Cable (4K@120Hz, 8K@60Hz, 48Gbps) - 6ft',
            'asin': 'B08M5HSRPT',  # Example ASIN
            'price': '$12.99',
            'detail_page_url': 'https://amazon.com/dp/B08M5HSRPT',
            'availability': 'Available on Amazon',
            'brand': 'ANKER',
            'features': ['4K@120Hz', '8K@60Hz', '48Gbps', 'Braided']
        }]
    
    return []

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

class DynamicProductIntelligence:
    """
    Self-updating product intelligence system that learns from your database
    """
    
    def __init__(self):
        self.cache_timeout = 3600 * 24  # 24 hours
        
    @lru_cache(maxsize=1)
    def get_learned_categories(self):
        """Learn product categories from actual database content"""
        cache_key = "learned_categories_v1"
        cached = cache.get(cache_key)
        if cached:
            return cached
            
        print("🧠 Learning product categories from database...")
        
        # Analyze all product names and descriptions
        from products.models import Product
        all_products = Product.objects.all()
        
        categories = {
            'laptop_indicators': Counter(),
            'cable_indicators': Counter(),
            'monitor_indicators': Counter(),
            'adapter_indicators': Counter(),
            'brand_indicators': Counter(),
            'marketing_noise': Counter()
        }
        
        for product in all_products:
            text = (product.name + " " + (product.description or "")).lower()
            words = text.split()
            
            # Learn laptop indicators
            if any(term in text for term in ['macbook', 'thinkpad', 'laptop', 'notebook']):
                for word in words:
                    if len(word) > 3:
                        categories['laptop_indicators'][word] += 1
            
            # Learn cable indicators  
            if any(term in text for term in ['cable', 'cord', 'hdmi', 'usb']):
                for word in words:
                    if len(word) > 3:
                        categories['cable_indicators'][word] += 1
            
            # Learn monitor indicators
            if any(term in text for term in ['monitor', 'display', 'screen', 'lcd']):
                for word in words:
                    if len(word) > 3:
                        categories['monitor_indicators'][word] += 1
                        
            # Learn adapter indicators
            if any(term in text for term in ['adapter', 'converter', 'dongle', 'hub']):
                for word in words:
                    if len(word) > 3:
                        categories['adapter_indicators'][word] += 1
            
            # Detect potential brands (capitalized words that appear frequently)
            import re
            brands = re.findall(r'\b[A-Z][a-z]+\b', product.name)
            for brand in brands:
                categories['brand_indicators'][brand.lower()] += 1
        
        # Filter to most significant indicators
        learned = {}
        for category, counter in categories.items():
            # Keep terms that appear in at least 3 products but not too common (spam filter)
            filtered = {word: count for word, count in counter.items() 
                       if 3 <= count <= len(all_products) * 0.1 and len(word) > 2}
            learned[category] = list(filtered.keys())
            
        print(f"✅ Learned {len(learned['laptop_indicators'])} laptop indicators")
        print(f"✅ Learned {len(learned['cable_indicators'])} cable indicators") 
        print(f"✅ Learned {len(learned['brand_indicators'])} brand indicators")
        
        cache.set(cache_key, learned, self.cache_timeout)
        return learned
    
    def detect_marketing_noise(self, min_threshold=10):
        """Automatically detect marketing fluff words"""
        cache_key = f"marketing_noise_v1_{min_threshold}"
        cached = cache.get(cache_key)
        if cached:
            return cached
            
        print("🔍 Analyzing marketing noise patterns...")
        
        from products.models import Product
        all_text = ""
        for product in Product.objects.all():
            all_text += (product.name + " " + (product.description or "")).lower()
        
        # Common patterns in marketing text
        marketing_patterns = [
            r'\b(certified|premium|ultra|high|advanced|enhanced|improved)\b',
            r'\b(professional|quality|durable|reliable|perfect|ideal)\b',
            r'\b(best|top|leading|superior|excellent|outstanding)\b',
            r'\b(new|latest|modern|innovative|cutting[-\s]edge)\b'
        ]
        
        import re
        detected_noise = set()
        for pattern in marketing_patterns:
            matches = re.findall(pattern, all_text)
            detected_noise.update(matches)
        
        # Filter by frequency (must appear at least min_threshold times)
        word_counts = Counter(all_text.split())
        frequent_noise = [word for word in detected_noise 
                         if word_counts[word] >= min_threshold]
        
        print(f"✅ Detected {len(frequent_noise)} marketing noise terms")
        cache.set(cache_key, frequent_noise, self.cache_timeout)
        return frequent_noise
    
    def get_category_confidence(self, text, category_type):
        """Calculate confidence that text belongs to a category"""
        learned = self.get_learned_categories()
        indicators = learned.get(f'{category_type}_indicators', [])
        
        text_lower = text.lower()
        matches = sum(1 for indicator in indicators if indicator in text_lower)
        confidence = matches / len(indicators) if indicators else 0
        
        return min(confidence * 2, 1.0)  # Cap at 1.0
    
    def suggest_new_categories(self):
        """Analyze database to suggest new product categories to add"""
        from products.models import Product
        
        # Find common word patterns that don't fit existing categories
        all_products = Product.objects.all()
        word_frequency = Counter()
        
        existing_categories = ['laptop', 'cable', 'monitor', 'adapter', 'power', 'storage']
        
        for product in all_products:
            # Skip products that clearly fit existing categories
            text = product.name.lower()
            if any(cat in text for cat in existing_categories):
                continue
                
            words = text.split()
            for word in words:
                if len(word) > 4:  # Focus on substantial words
                    word_frequency[word] += 1
        
        # Find clusters of products with similar uncommon words
        potential_categories = {}
        for word, count in word_frequency.most_common(50):
            if count >= 5:  # At least 5 products
                similar_products = Product.objects.filter(name__icontains=word)
                if similar_products.count() >= 5:
                    potential_categories[word] = {
                        'count': count,
                        'examples': [p.name for p in similar_products[:3]]
                    }
        
        return potential_categories

# Global instance
dynamic_intelligence = DynamicProductIntelligence()

def smart_extract_search_terms_dynamic(product_name: str) -> Dict[str, any]:
    """
    Enhanced version using dynamic learning from your database
    """
    try:
        name_lower = product_name.lower()
        
        # Get learned categories
        learned = dynamic_intelligence.get_learned_categories()
        
        # Calculate confidence for each category type
        confidences = {
            'laptop': dynamic_intelligence.get_category_confidence(name_lower, 'laptop'),
            'cable': dynamic_intelligence.get_category_confidence(name_lower, 'cable'), 
            'monitor': dynamic_intelligence.get_category_confidence(name_lower, 'monitor'),
            'adapter': dynamic_intelligence.get_category_confidence(name_lower, 'adapter')
        }
        
        # Get the most confident category
        best_category = max(confidences, key=confidences.get)
        best_confidence = confidences[best_category]
        
        print(f"🎯 Category confidences: {confidences}")
        print(f"🏆 Best match: {best_category} ({best_confidence:.2f})")
        
        # If confidence is too low, fall back to static rules
        if best_confidence < 0.3:
            print("⚠️ Low confidence, using static extraction")
            return smart_extract_search_terms(product_name)  # Fallback to original
        
        # Use learned indicators to build search terms
        category_indicators = learned.get(f'{best_category}_indicators', [])
        
        # Extract relevant terms from the product name
        relevant_terms = []
        for indicator in category_indicators[:10]:  # Top 10 indicators
            if indicator in name_lower:
                relevant_terms.append(indicator)
        
        # Remove marketing noise
        noise_terms = dynamic_intelligence.detect_marketing_noise()
        clean_terms = [term for term in relevant_terms if term not in noise_terms]
        
        return {
            'type': best_category,
            'confidence': best_confidence,
            'clean_terms': clean_terms[:5],  # Top 5 clean terms
            'learned_from': f"{len(category_indicators)} database examples",
            'method': 'dynamic_learning'
        }
        
    except Exception as e:
        print(f"⚠️ Dynamic extraction failed: {e}, falling back to static")
        return smart_extract_search_terms(product_name)

def smart_extract_search_terms(product_name: str) -> Dict[str, any]:
    """
    Original static version - kept as fallback
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
            'technical_specs': extract_cable_specs(name_lower),
            'method': 'static_rules'
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
            'technical_specs': extract_cable_specs(name_lower),
            'method': 'static_rules'
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
            'technical_specs': extract_laptop_specs(name_lower),
            'method': 'static_rules'
        }
    
    # Fallback: extract key terms and clean them
    else:
        clean_terms = extract_clean_terms(product_name)
        return {
            'type': detected_type or 'unknown',
            'subtype': None,
            'clean_terms': clean_terms,
            'technical_specs': {},
            'original_name': product_name[:50] + '...' if len(product_name) > 50 else product_name,
            'method': 'static_fallback'
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

def extract_product_specs(product: Product, product_name_override: str = None) -> ProductSpecs:
    """Extract technical specifications from product name and description"""
    # Handle case where only product name is provided (no product object)
    if product is None and product_name_override:
        text = product_name_override
    else:
        text = product_name_override or product.name
        if product and product.description:
            text += " " + product.description
    
    text_lower = text.lower()
    
    specs = ProductSpecs()
    
    # Extract cable length
    length_patterns = [
        r'(\d+(?:\.\d+)?)\s*(?:ft|feet|foot)',
        r'(\d+(?:\.\d+)?)\s*(?:m|meter|metres)',
        r'(\d+)-(?:ft|foot|feet)',
    ]
    for pattern in length_patterns:
        match = re.search(pattern, text_lower)
        if match:
            specs.length = float(match.group(1))
            break
    
    # Extract resolution
    if '8k' in text_lower or '8k@' in text_lower:
        specs.resolution = '8k'
    elif '4k' in text_lower or '4k@' in text_lower:
        specs.resolution = '4k'  
    elif '1440p' in text_lower:
        specs.resolution = '1440p'
    elif '1080p' in text_lower:
        specs.resolution = '1080p'
    
    # Extract speed/bandwidth
    speed_match = re.search(r'(\d+)\s*gbps', text_lower)
    if speed_match:
        specs.speed = speed_match.group(1) + 'gbps'
    
    # Extract version
    version_patterns = [
        r'hdmi\s*(\d+\.\d+)',
        r'usb\s*(\d+\.\d+)',
        r'usb[-\s]*([c3-9])',
    ]
    for pattern in version_patterns:
        match = re.search(pattern, text_lower)
        if match:
            specs.version = match.group(1)
            break
    
    # Extract features
    feature_keywords = ['hdr', 'hdr10', 'eARC', 'hdcp', 'dolby', 'atmos', 'braided']
    specs.features = [keyword for keyword in feature_keywords if keyword.lower() in text_lower]
    
    # Get price from offers (only if product object exists)
    if product:
        try:
            offers = list(product.offers.all())
            if offers:
                specs.price = float(offers[0].selling_price)
        except:
            pass
    
    return specs

def calculate_relevance_score(reference_specs: ProductSpecs, candidate_specs: ProductSpecs, base_score: float = 1.0) -> float:
    """Calculate relevance score based on spec similarity"""
    score = base_score
    
    # Price similarity (most important for consumers)
    if reference_specs.price and candidate_specs.price:
        ref_price = reference_specs.price
        cand_price = candidate_specs.price
        
        # Prefer similar price ranges
        if ref_price <= 20:  # Budget range
            if cand_price <= 30:
                score += 0.5  # Good match
            elif cand_price <= 50:
                score += 0.2  # Acceptable
            else:
                score -= 0.3  # Too expensive
        elif ref_price <= 50:  # Mid range
            if 20 <= cand_price <= 80:
                score += 0.4  # Good match
            else:
                score -= 0.2
        else:  # Premium range
            if cand_price >= 30:
                score += 0.3  # Good match
            else:
                score -= 0.1  # Too cheap (might be lower quality)
    
    # Length similarity (important for cables)
    if reference_specs.length and candidate_specs.length:
        length_diff = abs(reference_specs.length - candidate_specs.length)
        if length_diff <= 1:  # Very close
            score += 0.4
        elif length_diff <= 3:  # Close enough
            score += 0.2
        elif length_diff <= 6:  # Somewhat close
            score += 0.1
        else:  # Too different
            score -= 0.2
    
    # Resolution/quality matching
    if reference_specs.resolution and candidate_specs.resolution:
        if reference_specs.resolution == candidate_specs.resolution:
            score += 0.3  # Exact match
        elif (reference_specs.resolution in ['4k', '8k'] and 
              candidate_specs.resolution in ['4k', '8k']):
            score += 0.1  # Both high-res
    
    # Speed/bandwidth matching
    if reference_specs.speed and candidate_specs.speed:
        if reference_specs.speed == candidate_specs.speed:
            score += 0.2
    
    # Feature overlap
    if reference_specs.features and candidate_specs.features:
        common_features = set(reference_specs.features) & set(candidate_specs.features)
        score += len(common_features) * 0.1
    
    return max(score, 0.1)  # Minimum score 