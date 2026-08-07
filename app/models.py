from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey
from app.database import Base

class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = {"schema": "smarttutor"}
    role_id = Column(Integer, primary_key=True)
    role_name = Column(String(100), unique=True, nullable=False)


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "smarttutor"}
    user_id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    email_id = Column(String(255), unique=True, nullable=False)
    mobile = Column(String(20))
    device_id = Column(String(255))
    user_device = Column(String(100))
    password_hash = Column(String(255), nullable=False)
    role_id = Column(Integer, ForeignKey("smarttutor.user_roles.role_id"), nullable=False)
    is_active = Column(Boolean, default=True)


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = {"schema": "smarttutor"}
    question_id = Column(Integer, primary_key=True)
    subject = Column(String(100))
    question_text = Column(Text, nullable=False)


class LOV(Base):
    __tablename__ = "lov"
    __table_args__ = {"schema": "smarttutor"}
    lov_id = Column(Integer, primary_key=True)
    type = Column(String(100), nullable=False)
    is_hardcoded = Column(Boolean, default=False)
    value = Column(String(255), nullable=False)
    group_id = Column(String(100))
    question_id = Column(Integer, ForeignKey("smarttutor.questions.question_id"), nullable=True)


class Answer(Base):
    __tablename__ = "answers"
    __table_args__ = {"schema": "smarttutor"}
    answer_id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey("smarttutor.questions.question_id"), nullable=False)
    answer_text = Column(Text, nullable=False)
    is_correct = Column(Boolean)