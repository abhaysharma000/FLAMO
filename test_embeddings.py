
from langchain_google_genai import GoogleGenerativeAIEmbeddings

def main():
    embeddings = GoogleGenerativeAIEmbeddings(
        model="gemini-embedding-001"
    )

    text = "Flamo is an autonomous AI agent with persistent memory."
    vector = embeddings.embed_query(text)

    print("Embedding test successful!")
    print("Vector dimensions:", len(vector))
    print("First 5 values:", vector[:5])

if __name__ == "__main__":
    main()
