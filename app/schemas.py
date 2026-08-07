from pydantic import BaseModel, ConfigDict, EmailStr


# ---------- UserRole ----------
class UserRoleCreate(BaseModel):
    role_name: str

class UserRoleOut(UserRoleCreate):
    model_config = ConfigDict(from_attributes=True)
    role_id: int


# ---------- User ----------
class UserCreate(BaseModel):
    username: str
    email_id: EmailStr
    mobile: str | None = None
    device_id: str | None = None
    user_device: str | None = None
    role_id: int
    password: str  # plain text in, hashed before saving

class UserUpdate(BaseModel):
    username: str | None = None
    email_id: EmailStr | None = None
    mobile: str | None = None
    device_id: str | None = None
    user_device: str | None = None
    role_id: int | None = None
    is_active: bool | None = None

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: int
    username: str
    email_id: EmailStr
    mobile: str | None = None
    device_id: str | None = None
    user_device: str | None = None
    role_id: int
    is_active: bool


# ---------- Question ----------
class QuestionCreate(BaseModel):
    subject: str | None = None
    question_text: str

class QuestionOut(QuestionCreate):
    model_config = ConfigDict(from_attributes=True)
    question_id: int


# ---------- LOV ----------
class LOVCreate(BaseModel):
    type: str
    is_hardcoded: bool = False
    value: str
    group_id: str | None = None
    question_id: int | None = None

class LOVOut(LOVCreate):
    model_config = ConfigDict(from_attributes=True)
    lov_id: int


# ---------- Answer ----------
class AnswerCreate(BaseModel):
    question_id: int
    answer_text: str
    is_correct: bool | None = None

class AnswerOut(AnswerCreate):
    model_config = ConfigDict(from_attributes=True)
    answer_id: int