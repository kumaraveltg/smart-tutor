from typing import List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import Float
from datetime import datetime


# ---------- UserRole ----------
class UserRoleCreate(BaseModel):
    role_name: str
    created_by: Optional[str] = None
    modified_by: Optional[str] = None

class UserRoleOut(UserRoleCreate):
    model_config = ConfigDict(from_attributes=True)
    role_id: int
    role_name: str
    created_on: Optional[datetime] = None
    modified_on: Optional[datetime] = None
    created_by: Optional[str] = None
    modified_by: Optional[str] = None


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
    modified_by: str | None = None
    created_by: str | None = None

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
    modified_by: str | None = None

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
    created_on: Optional[datetime] = None
    modified_on: Optional[datetime] = None  

# ---------- Question ----------
class QuestionCreate(BaseModel):
    parent_id: int | None = None
    level_no: int | None = None  # worked out by the API when left empty
    class_id: int | None = None
    subject_id: int | None = None
    medium_id: int | None = None
    chapter_id: int | None = None
    subchapter_id: int | None = None
    question_text: str
    language_translation: str | None = None
    created_by: str | None = None  # adminApi.create sends this
    modified_by: str | None = None  # adminApi.update sends this


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    question_id: int
    parent_id: int | None = None
    level_no: int | None = None
    class_id: int | None = None
    subject_id: int | None = None
    medium_id: int | None = None
    chapter_id: int | None = None
    subchapter_id: int | None = None
    question_text: str
    language_translation: str | None = None
    created_by: str | None = None
    created_on: datetime | None = None
    modified_by: str | None = None
    modified_on: datetime | None = None


class QuestionImportRow(BaseModel):
    row: int | None = None  # Excel row number, used in error messages
    question_text: str | None = None
    language_translation: str | None = None


class QuestionImportRequest(BaseModel):
    chapter_id: int
    subchapter_id: int
    class_id: int | None = None
    subject_id: int | None = None
    medium_id: int | None = None
    items: list[QuestionImportRow]
    created_by: str | None = None  # adminApi.create sends this
    modified_by: str | None = None


class QuestionImportError(BaseModel):
    row: int
    reason: str


class QuestionImportResult(BaseModel):
    created: int
    errors: list[QuestionImportError] = []

class QuestionListOut(QuestionOut):
    display_text: str | None = None      # translated text if it exists, else English
    has_translation: bool = False

# ---------- LOV ----------
class LOVCreate(BaseModel):
    type: str 
    value: str
    active: bool | None = True 
    created_by: str | None = None
    modified_by: str | None = None

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
    title_ta: Optional[str] = None
    


class ChapterCreate(ChapterBase):
    pass


class ChapterUpdate(BaseModel):
    chapter_no: Optional[str] = None
    title_en: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None
    modified_by: Optional[str] = None
    title_ta: Optional[str] = None


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
    title_ta: Optional[str] = None


class SubchapterCreate(SubchapterBase):
    pass


class SubchapterUpdate(BaseModel):
    subchapter_no: Optional[str] = None
    title_en: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None
    modified_by: Optional[str] = None
    title_ta: Optional[str] = None


class SubchapterOut(SubchapterBase):
    subchapter_id: int
    level_no: int
    created_by: str | None = None
    created_on: datetime | None = None
    modified_by: str | None = None
    modified_on: datetime | None = None

    class Config:
        from_attributes = True


# ---------- Combined (chapter + its subchapters, for the left-menu tree) ----------

class ChapterWithSubchapters(ChapterOut):
    subchapters: List[SubchapterOut] = []

class ChapterTranslationIn(BaseModel):
    title: str
    modified_by: Optional[str] = None

class ChapterTranslationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    chapter_id: int
    lang_code: str
    title: str
    modified_by: Optional[str] = None
    modified_on: Optional[datetime] = None


class SubchapterTranslationIn(BaseModel):
    title: str
    modified_by: Optional[str] = None
 
 
class SubchapterTranslationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    subchapter_id: int
    lang_code: str
    title: str
    modified_by: Optional[str] = None
    modified_on: Optional[datetime] = None
     

class QuestionTranslationIn(BaseModel):
    question_text: str
    modified_by: str | None = None

class QuestionTranslationOut(BaseModel):
    question_id: int
    lang_code: str
    question_text: str
    created_by: str | None = None
    created_on: datetime | None = None
    modified_by: str | None = None
    modified_on: datetime | None = None
    model_config = ConfigDict(from_attributes=True)    



class TermOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    word: str


class TermCreate(BaseModel):
    english_word: str = Field(..., min_length=1, max_length=100)
    category: Optional[str] = None
    translations: Dict[str, str] = {}  # {"ta": "முக்கோணம்"}