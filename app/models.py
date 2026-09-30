from typing import Optional
from sqlalchemy import Column, DateTime, Float, Integer, String, Text, Boolean, ForeignKey  
from sqlalchemy.orm import Mapped, mapped_column, relationship 
from app.database import Base
from datetime import datetime, timezone 

class UserRole(Base):
    __tablename__ = "st_userroles"
    __table_args__ = {"schema": "smarttutor"}
    role_id = Column(Integer, primary_key=True)
    role_name = Column(String(100), unique=True, nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    created_on: Mapped[datetime] = mapped_column( DateTime(timezone=True),default=lambda: datetime.now(timezone.utc))
    modified_by: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    modified_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    

class User(Base):
    __tablename__ = "st_users"
    __table_args__ = {"schema": "smarttutor"}
    user_id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    email_id = Column(String(255), unique=True, nullable=False)
    mobile = Column(String(20))
    device_id = Column(String(255))
    user_device = Column(String(100))
    password_hash = Column(String(255), nullable=False)
    role_id = Column(Integer, ForeignKey("smarttutor.st_userroles.role_id"), nullable=False)
    is_active = Column(Boolean, default=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    created_on: Mapped[datetime] = mapped_column( DateTime(timezone=True),default=lambda: datetime.now(timezone.utc))
    modified_by: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    modified_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    full_name = Column(String(150)) 
    role = relationship("UserRole") 
    
class Question(Base):
    __tablename__ = "st_questions"
    __table_args__ = {"schema": "smarttutor"}
    question_id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, ForeignKey("smarttutor.st_questions.question_id"), nullable=True)
    level_no = Column(Integer, nullable=True)
    class_id = Column(Integer, ForeignKey("smarttutor.st_lov.lov_id"), nullable=True)
    subject_id = Column(Integer, ForeignKey("smarttutor.st_lov.lov_id"), nullable=True)
    medium_id = Column(Integer, ForeignKey("smarttutor.st_lov.lov_id"), nullable=True)
    chapter_id = Column(Integer, ForeignKey("smarttutor.st_chapter.chapter_id"), nullable=True)
    subchapter_id = Column(Integer, ForeignKey("smarttutor.st_chapter.chapter_id"), nullable=True)
    question_text = Column(Text, nullable=False)
    language_translation = Column(String(255), nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    created_on: Mapped[datetime] = mapped_column( DateTime(timezone=True),default=lambda: datetime.now(timezone.utc))
    modified_by: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    modified_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    

class LOV(Base):
    __tablename__ = "st_lov"
    __table_args__ = {"schema": "smarttutor"}
    lov_id = Column(Integer, primary_key=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    created_on: Mapped[datetime] = mapped_column( DateTime(timezone=True),default=lambda: datetime.now(timezone.utc))
    modified_by: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    modified_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Answer(Base):
    __tablename__ = "st_answers"
    __table_args__ = {"schema": "smarttutor"}
    answer_id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey("smarttutor.st_questions.question_id"), nullable=False)
    answer_text = Column(Text, nullable=False)
    is_correct = Column(Boolean)
    created_by: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    created_on: Mapped[datetime] = mapped_column( DateTime(timezone=True),default=lambda: datetime.now(timezone.utc))
    modified_by: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    modified_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class Chapter(Base):
    __tablename__ = "st_chapter"
    __table_args__ = {"schema": "smarttutor", "extend_existing": True}
    chapter_id = Column(Integer, primary_key=True, autoincrement=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    created_on: Mapped[datetime] = mapped_column( DateTime(timezone=True),default=lambda: datetime.now(timezone.utc))
    modified_by: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    modified_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    board_lov_id = Column(Integer, ForeignKey("smarttutor.st_lov.lov_id"), nullable=False)
    medium_lov_id = Column(Integer, ForeignKey("smarttutor.st_lov.lov_id"), nullable=False)
    class_lov_id = Column(Integer, ForeignKey("smarttutor.st_lov.lov_id"), nullable=False)
    subject_lov_id = Column(Integer, ForeignKey("smarttutor.st_lov.lov_id"), nullable=False)
    chapter_no = Column(String(10), nullable=False)     # '1', '2' ...
    title_en = Column(String(255), nullable=False)      # canonical text; other languages via st_translation
    level_no = Column(Integer, nullable=False, default=1)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    title_ta = Column(String(255), nullable=True)
    translations = relationship("ChapterTranslation", cascade="all, delete-orphan")

    subchapters = relationship(
        "Subchapter", back_populates="chapter", cascade="all, delete-orphan"
    )


class Subchapter(Base):
    __tablename__ = "st_subchapter"
    __table_args__ = {"schema": "smarttutor", "extend_existing": True}

    subchapter_id = Column(Integer, primary_key=True, autoincrement=True)
    chapter_id = Column(
        Integer, ForeignKey("smarttutor.st_chapter.chapter_id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    created_on: Mapped[datetime] = mapped_column( DateTime(timezone=True),default=lambda: datetime.now(timezone.utc))
    modified_by: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    modified_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    subchapter_no = Column(String(10), nullable=False)  # '1.1', '1.2' ...
    title_en = Column(String(255), nullable=False)
    level_no = Column(Integer, nullable=False, default=2)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    title_ta = Column(String(255), nullable=True)

    chapter = relationship("Chapter", back_populates="subchapters")   
    translations = relationship("SubchapterTranslation", back_populates="subchapter", cascade="all, delete-orphan", passive_deletes=True)

class ChapterTranslation(Base):
    __tablename__ = "chapter_translations"
    __table_args__ = {"schema": "smarttutor", "extend_existing": True}

    chapter_id = Column(Integer, ForeignKey("smarttutor.st_chapter.chapter_id", ondelete="CASCADE"), primary_key=True)
    lang_code = Column(String(10), primary_key=True)
    title = Column(String(255), nullable=False)
    created_by = Column(String(100), nullable=True)
    created_on = Column(DateTime, nullable=True)
    modified_by = Column(String(100), nullable=True)
    modified_on = Column(DateTime, nullable=True)

    chapter = relationship("Chapter", back_populates="translations")


class SubchapterTranslation(Base):
    __tablename__ = "subchapter_translations"
    __table_args__ = {"schema": "smarttutor", "extend_existing": True}    

   
    subchapter_id = Column(
        Integer,
        ForeignKey("smarttutor.st_subchapter.subchapter_id", ondelete="CASCADE"),
        primary_key=True,
    )
    lang_code = Column(String(10), primary_key=True)
    title = Column(String(255), nullable=False)
    created_by = Column(String(100), nullable=True)
    created_on = Column(DateTime(timezone=True), nullable=True)
    modified_by = Column(String(100), nullable=True)
    modified_on = Column(DateTime(timezone=True), nullable=True)

    subchapter = relationship("Subchapter", back_populates="translations")
 
 
