# main.py

from datetime import datetime
import sys
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
from utils.scheduler import start_scheduler
from models.models import OrganizationLicense 
from connection.database import SessionLocal

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Standard logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
    """Optimized middleware logging"""
    import time
    start_time = time.time()
    
    response = await call_next(request)
    
    duration = (time.time() - start_time) * 1000
    
    # Only log essential info in one line to reduce I/O
    logger.info(f"{request.method} {request.url.path} - {response.status_code} - {duration:.2f}ms")
    
    return response

@app.middleware("http")
async def license_check_middleware(request: Request, call_next):
    exempt_paths = [
        "/auth/login",
        "/auth/logout", 
        "/docs",
        "/openapi.json",
        "/auth/me"  # ← Tambahin ini
    ]

    if request.url.path in exempt_paths:
        return await call_next(request)

    auth_header = request.headers.get("authorization", "")
    
    if not auth_header.startswith("Bearer "):
        return await call_next(request)
    
    token = auth_header.replace("Bearer ", "")
    
    from routers.auth import verify_token  
    from jose import JWTError
    
    try:
        payload = verify_token(token)
        user_id = payload.get("sub")
        
        if not user_id:
            return await call_next(request)
        
        # Get user dari database
        db = SessionLocal()
        try:
            from models.models import User
            user = db.query(User).filter(User.id == int(user_id)).first()
            
            if not user:
                return await call_next(request)
            
            # ✅ CHECK LICENSE DI SINI
            if user.role != "super_admin":
                license = db.query(OrganizationLicense).filter(
                    OrganizationLicense.organization_id == user.organization_id
                ).first()

                if not license or license.end_date < datetime.utcnow():
                    return JSONResponse(
                        status_code=403,
                        content={
                            "detail": "Your organization license has expired. Please contact administrator."
                        }
                    )
        finally:
            db.close()
            
    except JWTError:
        pass  
    except Exception as e:
        print(f"License check error: {str(e)}")
        pass

    return await call_next(request)

# Include routers
from routers import directories, documents, document_categories, metadata, auth, organizations, departments, activity, users, anayltics

app.include_router(auth.router)
app.include_router(directories.router)
app.include_router(documents.router)
app.include_router(metadata.router)
app.include_router(organizations.router)
app.include_router(departments.router)
app.include_router(activity.router)
app.include_router(users.router)
app.include_router(document_categories.router)
app.include_router(anayltics.router)

@app.get("/")
def root():
    return {"message": "FastAPI running"}


# Tambahkan setelah app initialization
@app.on_event("startup")
async def startup_event():
    # Start license checker
    start_scheduler()
    print("Application started with license monitoring")

@app.on_event("shutdown")
async def shutdown_event():
    print("Application shutting down")

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
    
