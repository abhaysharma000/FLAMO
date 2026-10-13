
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings

def main():
    embeddings = GoogleGenerativeAIEmbeddings(
        model="gemini-embedding-001"
    )

    db = Chroma(
        collection_name="flamo_memory_test",
        embedding_function=embeddings,
        persist_directory="./workspace/chroma_memory"
    )

    documents = [
        "Flamo is an autonomous AI agent.",
        "Flamo uses persistent state to resume interrupted tasks.",
        "Python is a programming language.",
    ]

    db.add_texts(
        texts=documents,
        ids=["memory_1", "memory_2", "memory_3"]
    )

    results = db.similarity_search(
        "How does Flamo recover interrupted tasks?",
        k=2
    )

    print("\nSemantic search results:")
    for doc in results:
        print("-", doc.page_content)

if __name__ == "__main__":
    main()
