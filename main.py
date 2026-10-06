from fastapi import FastAPI
from app.routers import auth, chapter, user_roles, users, lov, questions, answers,subchapter,glossary,translate  
from fastapi.middleware.cors import CORSMiddleware  


app = FastAPI(title="SmartTutor API")
app.include_router(user_roles.router)
app.include_router(users.router)
app.include_router(lov.router)
app.include_router(questions.router)
app.include_router(answers.router)
app.include_router(chapter.router)
app.include_router(auth.router)
app.include_router(chapter.router)
app.include_router(subchapter.router) 
app.include_router(glossary.router)
app.include_router(translate.router)  

@app.get("/")
def root():
    return {"status": "ok"}
 


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)