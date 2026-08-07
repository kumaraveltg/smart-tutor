from fastapi import FastAPI
from app.routers import user_roles, users, lov, questions, answers

app = FastAPI(title="SmartTutor API")
app.include_router(user_roles.router)
app.include_router(users.router)
app.include_router(lov.router)
app.include_router(questions.router)
app.include_router(answers.router)

@app.get("/")
def root():
    return {"status": "ok"}