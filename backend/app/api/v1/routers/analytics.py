"""教学分析"""
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models import User, Experiment, ExperimentProgress, OperationRecord

router = APIRouter()


@router.get("/overview", dependencies=[Depends(require_roles("teacher"))])
def overview(db: Session = Depends(get_db)):
    total_students = db.query(func.count(User.id)).filter(User.role == "student").scalar() or 0
    total_experiments = db.query(func.count(Experiment.id)).scalar() or 0
    completed = db.query(func.count(ExperimentProgress.id)).filter(
        ExperimentProgress.status == "completed"
    ).scalar() or 0
    in_progress = db.query(func.count(ExperimentProgress.id)).filter(
        ExperimentProgress.status == "in_progress"
    ).scalar() or 0

    return {
        "total_students": total_students,
        "total_experiments": total_experiments,
        "completed_count": completed,
        "in_progress_count": in_progress,
        "completion_rate": round(completed / max(completed + in_progress, 1) * 100, 1),
    }


@router.get("/students", dependencies=[Depends(require_roles("teacher"))])
def student_list(db: Session = Depends(get_db)):
    students = db.query(User).filter(User.role == "student").all()
    result = []
    for s in students:
        progresses = db.query(ExperimentProgress).filter(ExperimentProgress.user_id == s.id).all()
        result.append({
            "id": s.id,
            "name": s.real_name or s.username,
            "class_name": s.class_name,
            "total_progresses": len(progresses),
            "completed_count": sum(1 for p in progresses if p.status == "completed"),
            "in_progress_count": sum(1 for p in progresses if p.status == "in_progress"),
        })
    return result


@router.get("/experiments/{exp_id}", dependencies=[Depends(require_roles("teacher"))])
def experiment_stats(exp_id: int, db: Session = Depends(get_db)):
    exp = db.query(Experiment).filter(Experiment.id == exp_id).first()
    if not exp:
        return {"error": "not found"}
    progresses = db.query(ExperimentProgress).filter(ExperimentProgress.experiment_id == exp_id).all()
    if not progresses:
        return {"experiment_id": exp_id, "stats": "no participants"}
    completion_rate = sum(1 for p in progresses if p.status == "completed") / len(progresses) * 100
    return {
        "experiment_id": exp_id,
        "title": exp.title,
        "participants": len(progresses),
        "completion_rate": round(completion_rate, 1),
        "avg_completed_steps": round(
            sum(p.completed_steps for p in progresses) / len(progresses), 1
        ),
    }
