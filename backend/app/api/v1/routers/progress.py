"""实验进度"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User, ExperimentProgress
from app.schemas import ProgressOut

router = APIRouter()


@router.get("/{exp_id}", response_model=ProgressOut)
def get_progress(
    exp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    progress = db.query(ExperimentProgress).filter(
        ExperimentProgress.user_id == current_user.id,
        ExperimentProgress.experiment_id == exp_id,
    ).first()
    if not progress:
        raise HTTPException(404, "进度不存在")
    return ProgressOut.model_validate(progress)
