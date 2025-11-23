# test_config.py - Demonstrate configuration usage
from config import DEFAULT_LLM, TOOL_INSTRUCTIONS, MAX_TOOL_ROUNDS

def main():
    print("=== Configuration Test ===")
    print(f"Current LLM: {DEFAULT_LLM}")
    print(f"Max Tool Rounds: {MAX_TOOL_ROUNDS}")
    print(f"Tool Instructions: {TOOL_INSTRUCTIONS['general']}")
    
    print("\n=== Available LLM Options ===")
    print("To change the LLM, edit config.py and uncomment one of these:")
    print("- llama3.2:3b (smaller, faster)")
    print("- llama3.1:8b (medium size)")
    print("- qwen2.5:7b (alternative model)")
    print("- openai/gpt-4o (requires OpenAI API key)")
    print("- anthropic/claude-3-5-sonnet-20241022 (requires Anthropic API key)")
    
    print("\n=== How to Change LLM ===")
    print("1. Edit config.py")
    print("2. Comment out current DEFAULT_LLM line")
    print("3. Uncomment your preferred model")
    print("4. Run your script - it will automatically use the new model!")

if __name__ == "__main__":
    main()