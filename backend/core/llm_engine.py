from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

# Featherless is OpenAI-compatible, just swap the base URL
client = OpenAI(
    api_key=os.getenv("FEATHERLESS_API_KEY"),
    base_url="https://api.featherless.ai/v1"
)

MODEL = "Qwen/Qwen2.5-72B-Instruct"


def ask_llm(system_prompt, user_message, temperature=0.0):
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        temperature=temperature,
        max_tokens=1024
    )
    return response.choices[0].message.content.strip()


# quick test
if __name__ == "__main__":
    result = ask_llm(
        system_prompt="You are a SQL expert. Return only valid SQLite SQL.",
        user_message="Count all rows in a table called customers."
    )
    print(result)
