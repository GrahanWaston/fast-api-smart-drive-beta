# main.py

import sys
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Setup logging dengan force flush
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Force flush after every print
def print_flush(*args, **kwargs):
    print(*args, **kwargs)
    sys.stdout.flush()

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Middleware dengan forced logging"""
    import time
    
    start_time = time.time()
    
    # Log dengan flush
    print_flush(f"\n{'='*60}")
    print_flush(f"📥 {request.method} {request.url.path}")
    print_flush(f"📥 Query: {dict(request.query_params)}")
    
    auth = request.headers.get("authorization", "None")
    if auth != "None":
        print_flush(f"📥 Auth: {auth[:40]}...")
    else:
        print_flush(f"📥 Auth: MISSING")
    
    try:
        response = await call_next(request)
        duration = (time.time() - start_time) * 1000
        
        print_flush(f"📤 Status: {response.status_code}")
        print_flush(f"📤 Duration: {duration:.2f}ms")
        print_flush(f"{'='*60}\n")
        
        return response
        
    except Exception as e:
        duration = (time.time() - start_time) * 1000
        print_flush(f"❌ ERROR: {type(e).__name__}")
        print_flush(f"❌ Message: {str(e)}")
        print_flush(f"❌ Duration: {duration:.2f}ms")
        print_flush(f"{'='*60}\n")
        raise

# Include routers
from routers import directories, documents, metadata, auth, organizations, departments, activity, users

app.include_router(auth.router)
app.include_router(directories.router)
app.include_router(documents.router)
app.include_router(metadata.router)
app.include_router(organizations.router)
app.include_router(departments.router)
app.include_router(activity.router)
app.include_router(users.router)

@app.get("/")
def root():
    return {"message": "FastAPI running"}

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8000))
    # PENTING: disable access log buffering
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=port,
        log_level="debug",
        access_log=True
    )