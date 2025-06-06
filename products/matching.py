"""
Advanced Product Matching System
Handles Amazon products vs database products with multiple matching strategies
"""

import re
import json
from difflib import SequenceMatcher
from collections import Counter
from django.db.models import Q
from products.models import Product

class ProductMatcher:
    """
    Multi-strategy product matching system
    """
    
    def __init__(self):
        self.debug = True
    
    def find_matches(self, amazon_product, limit=10):
        """
        Find potential matches for an Amazon product in the database
        
        Returns list of (match_type, confidence, database_product) tuples
        """
        matches = []
        
        # Strategy 1: Exact part number match (highest confidence)
        exact_matches = self._find_exact_part_matches(amazon_product)
        matches.extend(exact_matches)
        
        # Strategy 2: Manufacturer + similar part number
        if amazon_product.manufacturer:
            similar_part_matches = self._find_similar_part_matches(amazon_product)
            matches.extend(similar_part_matches)
        
        # Strategy 3: Description-based technical matching
        desc_matches = self._find_description_matches(amazon_product)
        matches.extend(desc_matches)
        
        # Strategy 4: Name similarity matching
        name_matches = self._find_name_matches(amazon_product)
        matches.extend(name_matches)
        
        # Remove duplicates and sort by confidence
        unique_matches = self._deduplicate_matches(matches)
        sorted_matches = sorted(unique_matches, key=lambda x: x[1], reverse=True)
        
        return sorted_matches[:limit]
    
    def _find_exact_part_matches(self, amazon_product):
        """Find exact part number matches"""
        matches = []
        
        if not amazon_product.part_number:
            return matches
        
        # Skip ASIN-like part numbers
        if re.match(r'^B[0-9A-Z]{9}$', amazon_product.part_number):
            return matches
        
        # Find exact matches
        exact_products = Product.objects.filter(
            part_number__iexact=amazon_product.part_number
        ).exclude(source='amazon')
        
        for product in exact_products:
            matches.append(('exact_part', 1.0, product))
            if self.debug:
                print(f"✅ EXACT PART MATCH: {product.part_number}")
        
        return matches
    
    def _find_similar_part_matches(self, amazon_product):
        """Find similar part numbers within same manufacturer"""
        matches = []
        
        if not amazon_product.part_number or not amazon_product.manufacturer:
            return matches
        
        # Skip ASIN-like part numbers
        if re.match(r'^B[0-9A-Z]{9}$', amazon_product.part_number):
            return matches
        
        # Find products from same manufacturer
        manufacturer_products = Product.objects.filter(
            manufacturer=amazon_product.manufacturer
        ).exclude(source='amazon')
        
        amazon_part_upper = amazon_product.part_number.upper()
        
        for product in manufacturer_products:
            if product.part_number:
                db_part_upper = product.part_number.upper()
                
                # Calculate similarity
                similarity = SequenceMatcher(None, amazon_part_upper, db_part_upper).ratio()
                
                if similarity > 0.8:  # High similarity threshold
                    confidence = similarity * 0.9  # Slightly lower than exact match
                    matches.append(('similar_part', confidence, product))
                    if self.debug:
                        print(f"🔶 SIMILAR PART ({similarity:.2f}): {product.part_number}")
        
        return matches
    
    def _find_description_matches(self, amazon_product):
        """Find matches based on technical specifications in descriptions"""
        matches = []
        
        if not amazon_product.description or len(amazon_product.description) < 50:
            return matches
        
        # Extract technical specifications from Amazon product
        amazon_specs = self._extract_technical_specs(amazon_product.description)
        
        if not amazon_specs:
            return matches
        
        # Find products with descriptions to compare
        database_products = Product.objects.filter(
            description__isnull=False
        ).exclude(
            description=''
        ).exclude(source='amazon')
        
        # Limit search for performance
        database_products = database_products[:1000]
        
        for product in database_products:
            db_specs = self._extract_technical_specs(product.description)
            
            if db_specs:
                # Calculate specification overlap
                confidence = self._calculate_spec_similarity(amazon_specs, db_specs)
                
                if confidence > 0.4:  # Minimum threshold for description matches
                    matches.append(('description', confidence, product))
                    if self.debug:
                        print(f"🔷 DESCRIPTION MATCH ({confidence:.2f}): {product.name[:40]}...")
        
        return matches
    
    def _find_name_matches(self, amazon_product):
        """Find matches based on product name similarity"""
        matches = []
        
        if not amazon_product.name:
            return matches
        
        # Extract key terms from Amazon product name
        amazon_terms = self._extract_key_terms(amazon_product.name)
        
        if len(amazon_terms) < 2:
            return matches
        
        # Build query for products with similar terms
        query = Q()
        for term in amazon_terms:
            if len(term) >= 3:  # Only meaningful terms
                query |= Q(name__icontains=term)
        
        similar_products = Product.objects.filter(query).exclude(source='amazon')[:100]
        
        for product in similar_products:
            db_terms = self._extract_key_terms(product.name)
            
            # Calculate term overlap
            if amazon_terms and db_terms:
                overlap = len(amazon_terms.intersection(db_terms))
                total_terms = len(amazon_terms.union(db_terms))
                confidence = overlap / total_terms if total_terms > 0 else 0
                
                # Also consider manufacturer match
                if (amazon_product.manufacturer and product.manufacturer and 
                    amazon_product.manufacturer.name.upper() == product.manufacturer.name.upper()):
                    confidence *= 1.2  # Boost confidence for same manufacturer
                
                if confidence > 0.3:  # Minimum threshold for name matches
                    matches.append(('name', min(confidence, 0.8), product))  # Cap at 0.8
                    if self.debug:
                        print(f"🔸 NAME MATCH ({confidence:.2f}): {product.name[:40]}...")
        
        return matches
    
    def _extract_technical_specs(self, description):
        """Extract technical specifications from description"""
        if not description:
            return set()
        
        desc_upper = description.upper()
        specs = set()
        
        # Memory specifications
        memory_specs = re.findall(r'\b(DDR[45](?:-\d+)?|[0-9]+GB|[0-9]+TB)\b', desc_upper)
        specs.update(memory_specs)
        
        # Connectivity
        connectivity_specs = re.findall(r'\b(USB\s*[0-9\.]+|Wi-?Fi\s*[0-9A-Z]*|Bluetooth\s*[0-9\.]*|HDMI|DisplayPort|PCIe?\s*[0-9\.]*)\b', desc_upper)
        specs.update([spec.replace(' ', '') for spec in connectivity_specs])
        
        # Performance specs
        performance_specs = re.findall(r'\b([0-9]+\s*GHZ|[0-9]+\s*MHZ|[0-9]+\s*RPM)\b', desc_upper)
        specs.update([spec.replace(' ', '') for spec in performance_specs])
        
        # Dimensions and power
        physical_specs = re.findall(r'\b([0-9]+\"\s*|[0-9]+W\s*|[0-9]+V\s*)\b', desc_upper)
        specs.update([spec.replace(' ', '') for spec in physical_specs])
        
        # Model numbers and part identifiers
        model_specs = re.findall(r'\b([A-Z]{2,4}\d{2,}[A-Z0-9]*)\b', desc_upper)
        specs.update(model_specs)
        
        return specs
    
    def _extract_key_terms(self, name):
        """Extract meaningful terms from product name"""
        if not name:
            return set()
        
        # Remove common stop words and clean
        stop_words = {'THE', 'AND', 'OR', 'WITH', 'FOR', 'IN', 'ON', 'AT', 'TO', 'A', 'AN'}
        
        # Split and clean terms
        terms = re.findall(r'\b[A-Z0-9]{3,}\b', name.upper())
        
        # Filter out stop words and very common terms
        meaningful_terms = set()
        for term in terms:
            if (term not in stop_words and 
                len(term) >= 3 and 
                not re.match(r'^\d+$', term)):  # Not just numbers
                meaningful_terms.add(term)
        
        return meaningful_terms
    
    def _calculate_spec_similarity(self, specs1, specs2):
        """Calculate similarity between two sets of specifications"""
        if not specs1 or not specs2:
            return 0.0
        
        # Direct overlap
        overlap = len(specs1.intersection(specs2))
        total_specs = len(specs1.union(specs2))
        
        if total_specs == 0:
            return 0.0
        
        base_similarity = overlap / total_specs
        
        # Bonus for having many matching specs
        if overlap >= 3:
            base_similarity *= 1.2
        
        return min(base_similarity, 1.0)
    
    def _deduplicate_matches(self, matches):
        """Remove duplicate products from matches, keeping highest confidence"""
        seen_products = {}
        
        for match_type, confidence, product in matches:
            product_id = product.id
            
            if product_id not in seen_products or confidence > seen_products[product_id][1]:
                seen_products[product_id] = (match_type, confidence, product)
        
        return list(seen_products.values())

# Convenience function for easy use
def find_product_matches(amazon_product, limit=10):
    """
    Find potential matches for an Amazon product
    
    Args:
        amazon_product: Product instance (Amazon source)
        limit: Maximum number of matches to return
    
    Returns:
        List of (match_type, confidence, database_product) tuples
    """
    matcher = ProductMatcher()
    return matcher.find_matches(amazon_product, limit) 