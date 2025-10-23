import os
import uuid
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import fitz  # PyMuPDF
from pinecone import Pinecone, ServerlessSpec
import google.generativeai as genai
from typing import List
from contextlib import asynccontextmanager
import uvicorn

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("--- Server Starting Up ---")
    
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise RuntimeError("API_KEY not found in environment variables.")
    genai.configure(api_key=api_key)
    print("Gemini Initialized.")

    pinecone_api_key = os.getenv("PINECONE_API_KEY")
    if not pinecone_api_key:
        raise RuntimeError("PINECONE_API_KEY not found in environment variables.")
    pc = Pinecone(api_key=pinecone_api_key)

    index_name = "chat-with-pdf"
    if index_name not in pc.list_indexes().names():
        print(f"Creating new Pinecone index: {index_name}")
        pc.create_index(
            name=index_name,
            dimension=768,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1")
        )
    app.state.pinecone_index = pc.Index(index_name)
    print("Pinecone Initialized.")
    
    yield
    
    print("--- Server Shutting Down ---")
    
app = FastAPI(lifespan=lifespan)

cors_origins = os.getenv("CORS_ORIGINS", "https://aman-pdf.netlify.app,http://localhost:3000,http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class UploadResponse(BaseModel):
    doc_id: str
    message: str
    num_chunks: int

class QueryRequest(BaseModel):
    doc_id: str
    query: str

class QueryResponse(BaseModel):
    answer: str
    source_chunks: List[str]

def extract_text_from_pdf(content: bytes) -> str:
    text = ""
    with fitz.open(stream=content, filetype="pdf") as doc:
        for page in doc:
            text += page.get_text() + "\n"
    return text

def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 100) -> List[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += (chunk_size - overlap)
    return [chunk for chunk in chunks if chunk.strip()]

def create_embeddings(chunks: List[str]) -> List[List[float]]:
    try:
        response = genai.embed_content(
            model="models/text-embedding-004",
            content=chunks,
            task_type="RETRIEVAL_DOCUMENT"
        )
        return response['embedding']
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating embeddings: {e}")

@app.post("/upload", response_model=UploadResponse)
async def upload_pdf(request: Request, file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")
        
    try:
        content = await file.read()
        text = extract_text_from_pdf(content)
        if not text.strip():
            raise HTTPException(status_code=400, detail="Could not extract text from PDF.")
        
        chunks = chunk_text(text)
        embeddings = create_embeddings(chunks)
        doc_id = str(uuid.uuid4())

        vectors = []
        for i, (embedding, chunk) in enumerate(zip(embeddings, chunks)):
            vectors.append({
                "id": f"{doc_id}_{i}",
                "values": embedding,
                "metadata": {
                    "text_chunk": chunk
                }
            })
        
        pinecone_index = request.app.state.pinecone_index
        batch_size = 100
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i:i + batch_size]
            pinecone_index.upsert(vectors=batch, namespace=doc_id)
        
        print(f"PDF processed and stored in Pinecone with namespace: {doc_id}")

        return UploadResponse(
            doc_id=doc_id,
            message="PDF processed and stored successfully",
            num_chunks=len(chunks)
        )
    except Exception as e:
        print(f"Error during upload: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")

@app.post("/query", response_model=QueryResponse)
async def query_pdf(request: Request, query_request: QueryRequest):
    pinecone_index = request.app.state.pinecone_index

    try:
        query_embedding_response = genai.embed_content(
            model="models/text-embedding-004",
            content=query_request.query,
            task_type="RETRIEVAL_QUERY"
        )
        query_embedding = query_embedding_response['embedding']

        results = pinecone_index.query(
            vector=query_embedding,
            top_k=5,
            namespace=query_request.doc_id,
            include_metadata=True
        )

        relevant_chunks = [match.metadata['text_chunk'] for match in results.matches]
        
        if not relevant_chunks:
            raise HTTPException(status_code=404, detail="No relevant context found for your query in this document.")

        context = "\n\n---\n\n".join(relevant_chunks)

        model = genai.GenerativeModel("gemini-1.5-pro") 
        prompt = (
            f"You are a helpful assistant. Answer the following question based ONLY on the context provided below.\n"
            f"If the answer is not in the context, state that you cannot find the answer in the document.\n\n"
            f"CONTEXT:\n{context}\n\n"
            f"QUESTION:\n{query_request.query}\n\n"
            f"ANSWER:"
        )
        
        response = model.generate_content(prompt)

        return QueryResponse(
            answer=response.text,
            source_chunks=relevant_chunks
        )
    except Exception as e:
        if "namespace" in str(e):
             raise HTTPException(status_code=404, detail="Document ID not found. The session may have expired.")
        print(f"Error during query: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing query: {str(e)}")

@app.get("/")
async def read_root():
    return {"message": "Welcome to the Chat with PDF API! Server is running."}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)