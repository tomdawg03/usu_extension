from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from openai import OpenAI
import time
import os
from dotenv import load_dotenv
from functools import lru_cache

# Load environment variables
load_dotenv()

app = FastAPI(title="AG Extension Q&A API")

ASSISTANT_ID = os.getenv("ASSISTANT_ID", "asst_IlflAyLDYVWCfSSJpMZ7ZgEO")

@lru_cache(maxsize=1)
def get_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return OpenAI(api_key=api_key)

class Question(BaseModel):
    message: str

@app.get("/")
def root():
    return {
        "message": "AG Extension Q&A API is running",
        "endpoints": {
            "/ask": "POST - Ask a question to the assistant",
            "/health": "GET - Health check"
        }
    }

@app.get("/health")
def health_check():
    configured = bool(os.getenv("OPENAI_API_KEY"))
    return {"status": "healthy", "assistant_id": ASSISTANT_ID, "openai_configured": configured}

@app.post("/ask")
def ask_question(question: Question):
    """
    Ask a question to the AG Extension assistant.
    Only returns answers from the fact sheets database.
    """
    try:
        client = get_openai_client()
        
        # Create thread
        thread = client.beta.threads.create()

        # Add user message
        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=question.message
        )

        # Run assistant
        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=ASSISTANT_ID
        )

        # Wait for completion (with timeout)
        max_wait = 60  # 60 seconds timeout
        elapsed = 0
        while run.status != "completed":
            if elapsed >= max_wait:
                raise HTTPException(status_code=408, detail="Request timeout")
            
            time.sleep(1)
            elapsed += 1
            run = client.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id
            )
            
            # Check for failed status
            if run.status == "failed":
                raise HTTPException(status_code=500, detail="Assistant run failed")

        # Get the response
        messages = client.beta.threads.messages.list(thread_id=thread.id)

        for message in messages.data:
            if message.role == "assistant":
                return {
                    "response": message.content[0].text.value,
                    "thread_id": thread.id
                }
        
        raise HTTPException(status_code=500, detail="No response from assistant")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
