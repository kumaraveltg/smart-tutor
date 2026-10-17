"""Index every existing answer into Chroma.

Run from the project folder (E:\\smart-tutor) with the venv active and Ollama running:
    python rebuild_answer_index.py            # add / refresh all answers
    python rebuild_answer_index.py --reset    # empty the index first, then rebuild

Safe to run again at any time. Run it after adding a new language to TARGET_LANGUAGES too.
"""
import sys

from sqlalchemy.orm import selectinload

from app import ai_index
from app.database import SessionLocal  # <-- adjust if your session factory has another name
from app.models import Answer, AnswerStep


def main() -> None:
    if "--reset" in sys.argv:
        ai_index.reset_collection()
        print("Index emptied.")

    db = SessionLocal()
    try:
        answers = (
            db.query(Answer)
            .options(selectinload(Answer.steps).selectinload(AnswerStep.translations))
            .order_by(Answer.answer_id)
            .all()
        )
        print(f"{len(answers)} answers to index...")
        entries = 0
        for n, ans in enumerate(answers, start=1):
            docs = ai_index.answer_to_docs(ans)
            ai_index.index_answer_docs(ans.answer_id, docs)
            entries += len(docs)
            if n % 20 == 0 or n == len(answers):
                print(f"  {n}/{len(answers)} answers, {entries} entries")
        print("Done.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
