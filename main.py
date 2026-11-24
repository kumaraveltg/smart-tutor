from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles 
from pathlib import Path 
from app import image_service as imgs
from app.routers import (
    auth, chapter, user_roles, users, lov, questions, answers,
    subchapter, glossary, translate, question_images,student,practice 
)  
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app_errors.log", encoding="utf-8", delay=True),
    ],
)

app = FastAPI(title="SmartTutor API")


from fastapi.staticfiles import StaticFiles
from app.image_service import IMAGE_BASE_PATH

IMAGE_BASE_PATH.mkdir(parents=True, exist_ok=True)
app.mount("/images", StaticFiles(directory=str(IMAGE_BASE_PATH)), name="images")

app.add_middleware(
    CORSMiddleware,
   allow_origins=["http://localhost:5173","http://127.0.0.1:5173","https://smartaistudio.in",],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(user_roles.router)
app.include_router(users.router)
app.include_router(lov.router)
app.include_router(chapter.router)
app.include_router(subchapter.router)
app.include_router(questions.router)
app.include_router(answers.router)
app.include_router(glossary.router)
app.include_router(translate.router)
app.include_router(question_images.router)
app.include_router(student.router)
app.include_router(practice.router)
app.include_router(student.admin_router)

@app.get("/")
def root():
    return {"status": "ok"}