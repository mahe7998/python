import ollama

response = ollama.chat(model='dolphin-llama3:latest', messages=[
 {
 'role': 'user',
 'content': 'What is the Retrieval-Augmented Generation? Answer with 1 sentence',
 },
])

print(response['message']['content'])
