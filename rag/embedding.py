import os
import json
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),  # Use the standard OpenAI API key env variable
    base_url=os.getenv("OPENAI_BASE_URL")  # Read base_url from environment variable
)

completion = client.embeddings.create(
    model="text-embedding-ada-002",
    input='This is a sample text for embedding generation to test the functionality.',
    encoding_format="float"
)

response_json = completion.model_dump_json()
embedding_data = json.loads(response_json)
embedding_array = embedding_data['data'][0]['embedding']
print(len(embedding_array))
print(type(embedding_array))
print("Extracted embedding array:", embedding_array)