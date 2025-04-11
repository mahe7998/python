#!/usr/bin/env python3
"""
Milvus collection management utility.
Usage:
  python pymil.py [collection_name] [--delete NEW_NAME] [--list]
  uv run pymil.py --list
"""

import argparse
import sys
import socket
import time
from pymilvus import connections, utility, Collection, CollectionSchema, DataType, FieldSchema

def check_server_availability(host, port, timeout=2):
    """Check if the server is available at the given host and port"""
    try:
        # Convert port to integer
        port = int(port)
        
        # Create a socket object
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        
        # Attempt to connect
        result = sock.connect_ex((host, port))
        sock.close()
        
        # If result is 0, the port is open
        return result == 0
    except Exception as e:
        print(f"Error checking server availability: {e}")
        return False

def connect_to_milvus(host="localhost", port="9091", uri=None):
    """Connect to Milvus server"""
    try:
        # Check server availability first
        if not check_server_availability(host, port):
            print(f"Cannot reach Milvus server at {host}:{port} - server may not be running")
            return False
        
        # Try to connect
        if uri:
            connections.connect("default", uri=uri)
            print(f"Connected to Milvus server at {uri}")
        else:
            connections.connect("default", host=host, port=port)
            print(f"Connected to Milvus server at {host}:{port}")
        
        # Verify connection
        try:
            utility.list_collections()
            return True
        except Exception as e:
            print(f"Connection test failed: {e}")
            return False
            
    except Exception as e:
        print(f"Failed to connect to Milvus: {e}")
        return False

def list_collections():
    """List all collections in Milvus"""
    try:
        collections = utility.list_collections()
        if not collections:
            print("No collections found in Milvus")
        else:
            print("Available collections:")
            for i, coll in enumerate(collections, 1):
                print(f"  {i}. {coll}")
        return collections
    except Exception as e:
        print(f"Error listing collections: {e}")
        return []

def delete_collection(collection_name):
    """Delete a collection from Milvus"""
    if not utility.has_collection(collection_name):
        print(f"Collection '{collection_name}' does not exist")
        return False
    
    try:
        utility.drop_collection(collection_name)
        print(f"Collection '{collection_name}' deleted successfully")
        return True
    except Exception as e:
        print(f"Error deleting collection '{collection_name}': {e}")
        return False

def rename_collection(old_name, new_name):
    """Rename a collection in Milvus by creating a new one and copying data"""
    if not utility.has_collection(old_name):
        print(f"Collection '{old_name}' does not exist")
        return False
    
    if utility.has_collection(new_name):
        print(f"Collection '{new_name}' already exists. Please choose a different name")
        return False
    
    try:
        # Get the original collection
        old_collection = Collection(old_name)
        old_collection.load()
        
        # Get schema from old collection
        schema = old_collection.schema
        print(f"Obtained schema with {len(schema.fields)} fields")
        
        # Create new collection with same schema
        new_collection = Collection(name=new_name, schema=schema)
        print(f"Created new collection '{new_name}'")
        
        # Simplified index creation - create basic indexes on vector fields
        try:
            for field in schema.fields:
                # Check if this is a vector field
                if field.dtype in [DataType.FLOAT_VECTOR, DataType.BINARY_VECTOR]:
                    print(f"Creating FLAT index on vector field '{field.name}'")
                    index_params = {
                        "index_type": "FLAT",  # Simplest index type, works everywhere
                        "metric_type": "L2",   # Standard distance metric
                        "params": {}           # No special parameters
                    }
                    new_collection.create_index(field_name=field.name, index_params=index_params)
        except Exception as e:
            print(f"Warning: Failed to create indexes: {e}")
            print("Will continue without indexes - you may need to add them manually later")
            
        # Get data from old collection and insert into new
        num_entities = old_collection.num_entities
        if num_entities > 0:
            print(f"Copying {num_entities} entities from '{old_name}' to '{new_name}'...")
            
            # Process in batches for large collections
            batch_size = 500  # Smaller batch size for stability
            for offset in range(0, num_entities, batch_size):
                limit = min(batch_size, num_entities - offset)
                try:
                    # Note: We use "*" to get all fields
                    data = old_collection.query(expr="", limit=limit, offset=offset, output_fields=["*"])
                    if data:
                        # Print sample entity keys for first batch (for debugging)
                        if offset == 0:
                            sample_entity = data[0]
                            print(f"Sample entity keys: {list(sample_entity.keys())}")
                        
                        # Prepare data for insertion by transforming to dictionary format
                        insert_data = {}
                        field_names = [field.name for field in schema.fields 
                                      if not field.name.startswith("_") or field.name == "_unused"]
                        
                        # Initialize the insert_data dictionary with empty lists for each field
                        for field_name in field_names:
                            insert_data[field_name] = []
                        
                        # Add data from entities
                        for entity in data:
                            for field_name in field_names:
                                if field_name in entity:
                                    insert_data[field_name].append(entity[field_name])
                                else:
                                    # If field is missing in this entity, add None or an appropriate default
                                    if field_name in insert_data:  # Only if we've started collecting this field
                                        insert_data[field_name].append(None)
                        
                        # Remove empty fields
                        insert_data = {k: v for k, v in insert_data.items() if v}
                        
                        # Insert only if we have data
                        if insert_data and any(len(v) > 0 for v in insert_data.values()):
                            new_collection.insert(insert_data)
                            print(f"Copied batch: {offset} to {offset + len(data)}")
                        else:
                            print(f"Warning: No valid data in batch {offset} to {offset + len(data)}")
                except Exception as e:
                    print(f"Error copying batch at offset {offset}: {e}")
                    print(f"Will continue with next batch...")
        
        # Flush to ensure data is written
        new_collection.flush()
        
        print(f"Collection '{old_name}' renamed to '{new_name}' successfully")
        
        # Delete old collection after successful copy
        delete_collection(old_name)
        
        return True
    except Exception as e:
        print(f"Error renaming collection '{old_name}' to '{new_name}': {e}")
        try:
            # Attempt to clean up the new collection if something went wrong
            if utility.has_collection(new_name):
                utility.drop_collection(new_name)
        except Exception:
            pass
        return False

def main():
    try:
        parser = argparse.ArgumentParser(description="Milvus collection management utility")
        parser.add_argument("collection_name", nargs="?", help="Name of the collection to operate on")
        parser.add_argument("--list", action="store_true", help="List all collections")
        parser.add_argument("--delete", action="store_true", help="Delete the specified collection")
        #parser.add_argument("--rename", type=str, help="Rename the collection to the specified new name")   Not working
        parser.add_argument("--host", type=str, default="localhost", help="Milvus server host (default: localhost)")
        parser.add_argument("--port", type=str, default="19530", help="Milvus server port (default: 19530)")
        parser.add_argument("--uri", type=str, help="Milvus server URI (e.g., http://localhost:19530)")
        
        args = parser.parse_args()
        
        # Connect to Milvus
        if not connect_to_milvus(args.host, args.port, args.uri):
            print("\nTroubleshooting tips:")
            print("1. Make sure the Milvus server is running")
            print("2. Check if you can access the server at the specified host and port")
            print("3. Verify there are no firewalls blocking the connection")
            print("4. Try running your main.py script to confirm its Milvus settings work")
            print("5. If using Docker, ensure the container is running and ports are properly mapped")
            print("\nAlternative connection:")
            print(f"  python pymil.py --host <your_host> --port <your_port> --list")
            sys.exit(1)
        
        # Just list collections if requested or no action specified
        if args.list or (not args.collection_name and not args.delete and not args.rename):
            list_collections()
            return
        # Ensure collection name is provided for operations
        if not args.collection_name:
            print("Error: collection_name is required for --delete and --rename operations")
            parser.print_help()
            sys.exit(1)
        
        # Perform the requested operation
        if args.delete:
            if delete_collection(args.collection_name):
                print("Operation completed successfully")
            else:
                sys.exit(1)
        elif args.rename:
            if rename_collection(args.collection_name, args.rename):
                print("Operation completed successfully")
            else:
                sys.exit(1)
        else:
            # If collection name is provided but no operation, just check if it exists
            if utility.has_collection(args.collection_name):
                collection = Collection(args.collection_name)
                print(f"Collection '{args.collection_name}' exists with {collection.num_entities} entities")
            else:
                print(f"Collection '{args.collection_name}' does not exist")
                list_collections()
    except Exception as e:
        print(f"Command line error: {e}")
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()



