#FASTAPI

pip install -r requirements.txt

python -m uvicorn main:app --reload


#FLASK

pip install -r requirements.txt

py app.py


postgresql://postgres:MHWdrHhWHMDOVaCqZJjoLBxeHMgQRIZW@postgres.railway.internal:5432/railway
postgresql://postgres:MHWdrHhWHMDOVaCqZJjoLBxeHMgQRIZW@crossover.proxy.rlwy.net:36511/railway

#STRUKTUR 

    FASTAPI/
    ├─ app
    │   ├─ main.py
    │   ├─ connection
    │       ├─ database.py
    │       ├─ schemas.py
    │       └─ base.py
    │   ├─ models 
    |       ├─ models.py
    │   └─ routers
    │       ├─ directories.py
    │       ├─ documents.py
    │       └─ metadata.py
    └─ requirements.txt

    FLASKAPP/
    ├─ app.py
    ├─ requirements.txt
    ├─ templates
    │   └─ backend
    |       └─ components
    |           └─ all the components here
    |       └─ pages
    |           └─ dashboard.html
    |           └─ organization.html
    |           └─ department.html 
    |       └─ base.html
    └─ static
        └─ js
            └─ index.js

            