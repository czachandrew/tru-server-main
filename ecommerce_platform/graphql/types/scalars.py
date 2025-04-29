import graphene
from graphene.types.scalars import Scalar
import json

class JSONScalar(Scalar):
    """JSON Scalar Type"""
    @staticmethod
    def serialize(value):
        return value
    
    @staticmethod
    def parse_literal(node):
        return node.value
    
    @staticmethod
    def parse_value(value):
        return json.loads(value) 