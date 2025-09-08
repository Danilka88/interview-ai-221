"""
Модуль, описывающий структуру таблиц в базе данных с использованием SQLAlchemy.
"""

import datetime

from sqlalchemy import (Column, Integer, String, Text, Float, DateTime, 
                        ForeignKey, JSON)
from sqlalchemy.orm import relationship

from core.database import Base

class Vacancy(Base):
    __tablename__ = "vacancies"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    text = Column(Text)
    generated_questions = Column(Text, nullable=True) # Сгенерированные вопросы для интервью
    weights_json = Column(JSON, nullable=True) # Веса критериев оценки в формате JSON
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Связь с кандидатами: одна вакансия может иметь много кандидатов
    candidates = relationship("Candidate", back_populates="vacancy")

class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    resume_text = Column(Text)
    initial_score = Column(Float)
    # Статус для воронки найма
    status = Column(String, default="new", index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    vacancy_id = Column(Integer, ForeignKey("vacancies.id"))
    
    # Связи
    vacancy = relationship("Vacancy", back_populates="candidates")
    interviews = relationship("Interview", back_populates="candidate")

class Interview(Base):
    __tablename__ = "interviews"

    id = Column(Integer, primary_key=True, index=True)
    interview_type = Column(String) # Например, 'voice' или 'simulation'
    final_score = Column(Float)
    full_report_json = Column(JSON)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    candidate_id = Column(Integer, ForeignKey("candidates.id"))

    # Связь
    candidate = relationship("Candidate", back_populates="interviews")
