from typing import List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import Float


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
    full_name: str | None = None

class UserUpdate(BaseModel):
    username: str | None = None
    email_id: EmailStr | None = None
    mobile: str | None = None
    device_id: str | None = None
    user_device: str | None = None
    role_id: int | None = None
    is_active: bool | None = None
    password: str | None = None
    full_name: str | None = None

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
    full_name: str | None = None


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
    value: str
    active: bool | None = True 

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



# ---------- Chapter ----------

class ChapterBase(BaseModel):
    board_lov_id: int
    class_lov_id: int
    medium_lov_id: int
    subject_lov_id: int
    chapter_no: str = Field(..., max_length=10)
    title_en: str = Field(..., max_length=255)
    sort_order: Optional[int] = 0
    is_active: bool = True
    created_by: Optional[str] = None
    modified_by: Optional[str] = None


class ChapterCreate(ChapterBase):
    pass


class ChapterUpdate(BaseModel):
    chapter_no: Optional[str] = None
    title_en: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None
    modified_by: Optional[str] = None


class ChapterOut(ChapterBase):
    chapter_id: int
    level_no: int

    class Config:
        from_attributes = True


# ---------- Subchapter ----------

class SubchapterBase(BaseModel):
    chapter_id: int
    subchapter_no: str = Field(..., max_length=10)
    title_en: str = Field(..., max_length=255)
    sort_order: Optional[int] = 0
    is_active: bool = True
    created_by: Optional[str] = None
    modified_by: Optional[str] = None


class SubchapterCreate(SubchapterBase):
    pass


class SubchapterUpdate(BaseModel):
    subchapter_no: Optional[str] = None
    title_en: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None
    modified_by: Optional[str] = None


class SubchapterOut(SubchapterBase):
    subchapter_id: int
    level_no: int

    class Config:
        from_attributes = True


# ---------- Combined (chapter + its subchapters, for the left-menu tree) ----------

class ChapterWithSubchapters(ChapterOut):
    subchapters: List[SubchapterOut] = []
