#!/bin/bash
# Simple shell script to translate markdown files using Ollama

# Default values
DEFAULT_LANGUAGE="French"
DEFAULT_MODEL="granite3.2:8b"

# Display usage information
function show_usage {
    echo "Usage: $0 [options] <markdown_file>"
    echo ""
    echo "Options:"
    echo "  -l, --language LANGUAGE   Target language for translation (default: $DEFAULT_LANGUAGE)"
    echo "  -m, --model MODEL         Ollama model to use (default: $DEFAULT_MODEL)"
    echo "  -h, --help                Show this help message"
    echo ""
    echo "Example:"
    echo "  $0 output/Lucas\ TB\ report-with-text_imagerefs.md"
    echo "  $0 --language Spanish output/Lucas\ TB\ report-with-text_imagerefs.md"
    echo ""
}

# Parse command line arguments
LANGUAGE=$DEFAULT_LANGUAGE
MODEL=$DEFAULT_MODEL
FILE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -l|--language)
            LANGUAGE="$2"
            shift 2
            ;;
        -m|--model)
            MODEL="$2"
            shift 2
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            if [[ -z "$FILE" ]]; then
                FILE="$1"
            else
                echo "Error: Unexpected argument: $1"
                show_usage
                exit 1
            fi
            shift
            ;;
    esac
done

# Check if a file was provided
if [[ -z "$FILE" ]]; then
    echo "Error: No markdown file specified."
    show_usage
    exit 1
fi

# Check if the file exists
if [[ ! -f "$FILE" ]]; then
    echo "Error: File '$FILE' does not exist."
    exit 1
fi

# Run the translation
echo "Translating '$FILE' to $LANGUAGE using model $MODEL..."
python translate_markdown.py --file "$FILE" --language "$LANGUAGE" --model "$MODEL"

# Check if the translation was successful
if [[ $? -eq 0 ]]; then
    # Get the base filename without extension
    BASENAME=$(basename "$FILE" .md)
    DIR=$(dirname "$FILE")
    TRANSLATED_FILE="$DIR/$BASENAME-${LANGUAGE,,}.md"
    
    if [[ -f "$TRANSLATED_FILE" ]]; then
        echo "Translation completed successfully!"
        echo "Translated file: $TRANSLATED_FILE"
    else
        echo "Translation completed, but the output file was not found at the expected location."
    fi
else
    echo "Translation failed. See error messages above."
fi
