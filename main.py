from fastapi import FastAPI
from app.routers import auth, chapter, user_roles, users, lov, questions, answers,subchapter
from fastapi.middleware.cors import CORSMiddleware
from app.routers.chapter import router as chapter_router


app = FastAPI(title="SmartTutor API")
app.include_router(user_roles.router)
app.include_router(users.router)
app.include_router(lov.router)
app.include_router(questions.router)
app.include_router(answers.router)
app.include_router(chapter.router)
app.include_router(auth.router)
app.include_router(chapter_router)
app.include_router(subchapter.router)

@app.get("/")
def root():
    return {"status": "ok"}
 


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)