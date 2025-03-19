import sys

# Maximum number od images of results to return
def check_dependencies():
    missing_deps = []
    try:
        from colpali_class import ColpaliLocaRag
    except ImportError:
        missing_deps.append("colpali_class")

    try:
        import argparse
    except ImportError:
        missing_deps.append("argparse")
    
    try:
        import byaldi
    except ImportError:
        missing_deps.append("byaldi")
    
    try:
        import torch
    except ImportError:
        missing_deps.append("torch")
    
    try:
        import transformers
    except ImportError:
        missing_deps.append("transformers")
    
    if missing_deps:
        print(f"Error: Missing dependencies: {', '.join(missing_deps)}")
        print("Please install them using: pip install -r requirements.txt")
        sys.exit(1)

# Check dependencies before proceeding
check_dependencies()

from colpali_class import ColpaliLocaRag
import argparse

def main():
    """
    Example usage of the ColpaliLocaRag class.
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='ColPali - PDF RAG with multimodal capabilities')
    parser.add_argument('project_name', type=str, help='Name of the project (required)')
    parser.add_argument('--pdf', type=str, help='Path to PDF file to index (optional)')
    parser.add_argument('--query', type=str, default="What is the document about?",
                        help='Query to search in the PDF')
    parser.add_argument('--model', type=str, default="Qwen/Qwen2-VL-2B-Instruct", 
                      help='Model to use for analysis (default: Qwen/Qwen2-VL-2B-Instruct)')
    parser.add_argument('--max_pages', type=int, default=3,
                      help='Maximum number of pages to return in search results (default: 3)')
    args = parser.parse_args()
    
    # Create ColpaliLocaRag instance
    rag = ColpaliLocaRag(args.project_name, model=args.model, max_k=args.max_pages)
    
    # If PDF file is provided, add it to the index
    if args.pdf:
        success = rag.add_pdf(args.pdf)
        if not success:
            sys.exit(1)
    
    response = rag.query(args.query)
    print(f"{args.query}\nAI model response:")
    print(response)

if __name__ == "__main__":
    main()
