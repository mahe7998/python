# web-search-gpt-oss.py
# Run with: uv run main.py [optional query]

# Recommended models:
#
# These models have great tool-use capabilities and are able to have multi-turn interactions with the user and tools to get to a final result.
#  qwen3
#  gpt-oss

# /// script
# requires-python = ">=3.11",
# requires-gpt-oss>=0.0.8",
# requires-ollama>=0.6.0",
# requires-python-dotenv>=1.1.1",
# dependencies = [
#     "ollama",
#     "gpt-oss",
#     "python-dotenv",
# ]
# ///
import sys
from typing import Any, Dict, List
from dotenv import load_dotenv
from web_search_gpt_oss_helper import Browser

from ollama import Client

# Load environment variables from .env file
load_dotenv()


def main() -> None:
  # Check command line arguments first
  if len(sys.argv) == 2:
    # Use query from command line argument
    query = sys.argv[1]
  elif len(sys.argv) > 2:
    # Too many arguments - show usage and prompt for input
    print("Too many arguments provided. Please enter your request interactively:")
    query = input("Please enter request: ").strip()
  else:
    # No arguments - prompt for input
    query = input("Please enter request: ").strip()
  
  if not query:
    print("No query provided. Exiting.")
    sys.exit(1)
  
  client = Client()
  browser = Browser(initial_state=None, client=client)

  def browser_search(query: str, topn: int = 10) -> str:
    return browser.search(query=query, topn=topn)['pageText']

  def browser_open(id: int | str | None = None, cursor: int = -1, loc: int = -1, num_lines: int = -1) -> str:
    return browser.open(id=id, cursor=cursor, loc=loc, num_lines=num_lines)['pageText']

  def browser_find(pattern: str, cursor: int = -1, **_: Any) -> str:
    return browser.find(pattern=pattern, cursor=cursor)['pageText']

  browser_search_schema = {
    'type': 'function',
    'function': {
      'name': 'browser.search',
    },
  }

  browser_open_schema = {
    'type': 'function',
    'function': {
      'name': 'browser.open',
    },
  }

  browser_find_schema = {
    'type': 'function',
    'function': {
      'name': 'browser.find',
    },
  }

  available_tools = {
    'browser.search': browser_search,
    'browser.open': browser_open,
    'browser.find': browser_find,
  }

  print('Prompt:', query, '\n')

  messages: List[Dict[str, Any]] = [{'role': 'user', 'content': query}]

  while True:
    resp = client.chat(
      # model='gpt-oss:120b-cloud',
      # changed with the local dowloaded gpt-oss
      model='gpt-oss:120b',
      messages=messages,
      tools=[browser_search_schema, browser_open_schema, browser_find_schema],
      #####
      think=True,
      #####

    )

    if resp.message.thinking:
      print('Thinking:\n========\n')
      print(resp.message.thinking + '\n')

    if resp.message.content:
      print('Response:\n========\n')
      print(resp.message.content + '\n')

    messages.append(resp.message)

    if not resp.message.tool_calls:
      break

    for tc in resp.message.tool_calls:
      tool_name = tc.function.name
      args = tc.function.arguments or {}
      print(f'Tool name: {tool_name}, args: {args}')
      fn = available_tools.get(tool_name)
      if not fn:
        messages.append({'role': 'tool', 'content': f'Tool {tool_name} not found', 'tool_name': tool_name})
        continue

      try:
        result_text = fn(**args)
        print('Result: ', result_text[:200] + '...')
      except Exception as e:
        result_text = f'Error from {tool_name}: {e}'

      messages.append({'role': 'tool', 'content': result_text, 'tool_name': tool_name})


if __name__ == '__main__':
  main()
  