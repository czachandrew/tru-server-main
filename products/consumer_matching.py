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
        
        # ALWAYS search for relevant accessories we can provide
        accessory_products = self._find_relevant_accessories(search_term, category)
        result.supplier_alternatives = accessory_products
        
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
        """Enhanced search of supplier products with multiple strategies"""
        
        # Strategy 1: Exact part number or model matching
        exact_matches = self._exact_part_search(search_term)
        
        # Strategy 2: Description keyword matching (weighted by relevance)
        description_matches = self._weighted_description_search(search_term)
        
        # Strategy 3: Fuzzy name matching
        name_matches = self._fuzzy_name_search(search_term)
        
        # Strategy 4: Enhanced description mining for consumer products
        consumer_matches = self._consumer_description_mining(search_term)
        
        # Combine and deduplicate
        seen_ids = set()
        results = []
        
        # Priority order: exact > consumer > description > name
        for product_list in [exact_matches, consumer_matches, description_matches, name_matches]:
            for product in product_list:
                if product.id not in seen_ids:
                    seen_ids.add(product.id)
                    results.append(product)
                    if len(results) >= 15:  # Limit total results
                        break
            if len(results) >= 15:
                break
        
        return results
    
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
        
        return list(Product.objects.filter(query, source='partner_import')[:8])
    
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
        
        return list(Product.objects.filter(query, source='partner_import')[:10])
    
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
        
        return list(Product.objects.filter(query, source='partner_import')[:5])
    
    def _fuzzy_name_search(self, search_term: str) -> List[Product]:
        """Fuzzy search on product names with stemming"""
        keywords = search_term.lower().split()[:4]  # First 4 words
        
        query = Q()
        for keyword in keywords:
            if len(keyword) > 2:
                query |= Q(name__icontains=keyword)
        
        return list(Product.objects.filter(query, source='partner_import')[:5])
    
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
        
        products = Product.objects.filter(query, source='partner_import')[:6]
        
        return [
            {'product': p, 'source': 'supplier', 'match_type': f'{category}_accessory'} 
            for p in products
        ]

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
        
        # Determine enhanced relationship fields
        relationship_data = _determine_enhanced_relationship(match_type, source, is_primary=False)
        
        formatted_results.append({
            'product': product,
            'matchType': match_type,
            'matchConfidence': 0.6,
            'isAmazonProduct': False,
            'isAlternative': True,
            # Enhanced fields
            'relationshipType': relationship_data['relationship_type'],
            'relationshipCategory': relationship_data['relationship_category'],
            'marginOpportunity': relationship_data['margin_opportunity'],
            'revenueType': relationship_data['revenue_type']
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