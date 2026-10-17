
# def query():
#     query = input("What do u want to ask about?\n")
#     related_chunks = retriever.query(question=query, top_k=20)

#     reranked_results: list[tuple[dict, float]] = reranker.rerank(
#         query=query, docs=related_chunks, top_k=5
#     )
#     for chunk, score in reranked_results:
#         print(chunk["content"][:50])
#         print(score)