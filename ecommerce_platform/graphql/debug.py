# Create this file for debugging
import json
from .schema_future import schema

def print_schema():
    """Print the full GraphQL schema to help debug missing fields"""
    schema_dict = schema.introspect()
    with open('schema_debug.json', 'w') as f:
        json.dump(schema_dict, f, indent=2)
    
    print("Schema written to schema_debug.json")

if __name__ == "__main__":
    print_schema() 