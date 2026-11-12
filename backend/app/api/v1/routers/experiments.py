"""实验任务 CRUD"""
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models import User, Experiment, ExperimentStep, ExperimentProgress, ExperimentReport
from app.schemas import (
    ExperimentCreate, ExperimentUpdate, ExperimentOut, ExperimentListOut, ExperimentStepOut,
    ExperimentReportIn, ExperimentReportOut, ExperimentImportIn, StepProgressIn,
)

router = APIRouter()


def _to_list_out(exp: Experiment, progress: ExperimentProgress | None = None) -> ExperimentListOut:
    total = len(exp.steps)
    done = progress.completed_steps if progress else 0
    progress_pct = round(done / total * 100, 1) if total else 0
    # 没有进度记录 → 学生视角就是「未开始」，不能把 published/draft 直接暴露给学生
    student_status = progress.status if progress else "not_started"
    return ExperimentListOut(
        id=exp.id, title=exp.title, description=exp.description,
        type=exp.type, software=exp.software, status=student_status,
        deadline=exp.deadline, created_at=exp.created_at,
        total_steps=total, completed_steps=done, progress=progress_pct,
    )


@router.get("", response_model=List[ExperimentListOut])
def list_experiments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出实验（附带当前用户进度）"""
    experiments = db.query(Experiment).options(joinedload(Experiment.steps)).all()
    progresses = {
        p.experiment_id: p
        for p in db.query(ExperimentProgress).filter(ExperimentProgress.user_id == current_user.id).all()
    }
    return [_to_list_out(e, progresses.get(e.id)) for e in experiments]


@router.post("/import", response_model=ExperimentOut, dependencies=[Depends(require_roles("teacher"))])
def import_experiment(data: ExperimentImportIn, db: Session = Depends(get_db)):
    """导入实验（JSON：实验信息 + 步骤 + 桌面助手定位提示）

    steps[].adapter 可以带 target_app / window_title / keywords / type_hint，
    桌面助手据此自动聚焦对应窗口并标注控件。
    """
    if data.overwrite:
        old = db.query(Experiment).filter(Experiment.title == data.experiment.title).first()
        if old:
            # 级联删除会自动清理 steps / progresses / reports / operation_records
            db.delete(old)
            db.flush()  # 不 commit，与下面的创建合并到同一事务

    exp = Experiment(**data.experiment.model_dump())
    db.add(exp)
    db.flush()

    for i, step in enumerate(data.steps):
        db.add(ExperimentStep(
            experiment_id=exp.id,
            order_index=i,
            title=step.title,
            instruction=step.instruction,
            expected_result=step.expected_result,
            common_errors=step.common_errors,
            adapter_hint=step.adapter,
        ))
    db.commit()
    db.refresh(exp)
    return ExperimentOut.model_validate(exp)


def _require_experiment(db: Session, exp_id: int) -> Experiment:
    """取实验，不存在直接 404（避免为不存在的实验写入进度/报告）"""
    exp = db.query(Experiment).options(joinedload(Experiment.steps)).filter(
        Experiment.id == exp_id
    ).first()
    if not exp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "实验不存在")
    return exp


@router.post("/{exp_id}/step")
def update_step_progress(
    exp_id: int,
    data: StepProgressIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """桌面助手回报当前步骤进度"""
    exp = _require_experiment(db, exp_id)
    if data.step_index < 0 or data.step_index >= len(exp.steps):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "步骤序号超出范围")
    progress = _get_or_create_progress(db, current_user.id, exp_id)
    progress.current_step = data.step_index
    if data.completed:
        progress.completed_steps = max(progress.completed_steps or 0, data.step_index + 1)
    progress.last_active_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "current_step": progress.current_step,
            "completed_steps": progress.completed_steps}


@router.get("/{exp_id}", response_model=ExperimentOut)
def get_experiment(exp_id: int, db: Session = Depends(get_db)):
    exp = db.query(Experiment).options(joinedload(Experiment.steps)).filter(Experiment.id == exp_id).first()
    if not exp:
        raise HTTPException(404, "实验不存在")
    return ExperimentOut.model_validate(exp)


@router.post("", response_model=ExperimentOut, dependencies=[Depends(require_roles("teacher"))])
def create_experiment(data: ExperimentCreate, db: Session = Depends(get_db)):
    exp = Experiment(**data.model_dump())
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return ExperimentOut.model_validate(exp)


@router.put("/{exp_id}", response_model=ExperimentOut, dependencies=[Depends(require_roles("teacher"))])
def update_experiment(exp_id: int, data: ExperimentUpdate, db: Session = Depends(get_db)):
    exp = db.query(Experiment).filter(Experiment.id == exp_id).first()
    if not exp:
        raise HTTPException(404, "实验不存在")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(exp, field, value)
    db.commit()
    db.refresh(exp)
    return ExperimentOut.model_validate(exp)


@router.delete("/{exp_id}", dependencies=[Depends(require_roles("teacher"))])
def delete_experiment(exp_id: int, db: Session = Depends(get_db)):
    exp = db.query(Experiment).filter(Experiment.id == exp_id).first()
    if not exp:
        raise HTTPException(404, "实验不存在")
    db.delete(exp)
    db.commit()
    return {"ok": True}


@router.get("/{exp_id}/steps", response_model=List[ExperimentStepOut])
def list_steps(exp_id: int, db: Session = Depends(get_db)):
    exp = db.query(Experiment).filter(Experiment.id == exp_id).first()
    if not exp:
        raise HTTPException(404, "实验不存在")
    steps = db.query(ExperimentStep).filter(
        ExperimentStep.experiment_id == exp_id
    ).order_by(ExperimentStep.order_index).all()
    return [ExperimentStepOut.model_validate(s) for s in steps]


@router.post("/{exp_id}/start")
def start_experiment(
    exp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """开始/继续实验，初始化进度"""
    exp = db.query(Experiment).filter(Experiment.id == exp_id).first()
    if not exp:
        raise HTTPException(404, "实验不存在")
    from datetime import datetime
    progress = db.query(ExperimentProgress).filter(
        ExperimentProgress.user_id == current_user.id,
        ExperimentProgress.experiment_id == exp_id,
    ).first()
    if not progress:
        progress = ExperimentProgress(
            user_id=current_user.id,
            experiment_id=exp_id,
            status="in_progress",
            started_at=datetime.utcnow(),
        )
        db.add(progress)
    elif progress.status != "completed":
        progress.status = "in_progress"
    progress.last_active_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "progress_id": progress.id, "status": progress.status}


@router.post("/{exp_id}/submit")
def submit_experiment(
    exp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    progress = db.query(ExperimentProgress).filter(
        ExperimentProgress.user_id == current_user.id,
        ExperimentProgress.experiment_id == exp_id,
    ).first()
    if not progress:
        raise HTTPException(400, "请先开始实验")
    exp = db.query(Experiment).options(joinedload(Experiment.steps)).filter(
        Experiment.id == exp_id
    ).first()
    progress.status = "completed"
    progress.completed_at = datetime.utcnow()
    progress.completed_steps = len(exp.steps) if exp else 0
    db.commit()
    return {"ok": True}


# ==================== 实验报告 ====================

def _get_or_create_progress(db: Session, user_id: int, exp_id: int) -> ExperimentProgress:
    progress = db.query(ExperimentProgress).filter(
        ExperimentProgress.user_id == user_id,
        ExperimentProgress.experiment_id == exp_id,
    ).first()
    if not progress:
        progress = ExperimentProgress(
            user_id=user_id, experiment_id=exp_id,
            status="in_progress", started_at=datetime.utcnow(),
        )
        db.add(progress)
        db.commit()
        db.refresh(progress)
    return progress


@router.get("/{exp_id}/report", response_model=ExperimentReportOut)
def get_report(
    exp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    progress = db.query(ExperimentProgress).filter(
        ExperimentProgress.user_id == current_user.id,
        ExperimentProgress.experiment_id == exp_id,
    ).first()
    if not progress:
        raise HTTPException(404, "还没有报告")
    report = db.query(ExperimentReport).filter(
        ExperimentReport.progress_id == progress.id
    ).first()
    if not report:
        raise HTTPException(404, "还没有报告")
    return ExperimentReportOut.model_validate(report)


@router.put("/{exp_id}/report", response_model=ExperimentReportOut)
def save_report(
    exp_id: int,
    data: ExperimentReportIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """保存报告草稿（自动创建/更新当前用户的报告）"""
    _require_experiment(db, exp_id)
    progress = _get_or_create_progress(db, current_user.id, exp_id)
    report = db.query(ExperimentReport).filter(
        ExperimentReport.progress_id == progress.id
    ).first()
    if not report:
        report = ExperimentReport(progress_id=progress.id)
        db.add(report)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(report, field, value)
    db.commit()
    db.refresh(report)
    return ExperimentReportOut.model_validate(report)


@router.post("/{exp_id}/report/submit")
def submit_report(
    exp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_experiment(db, exp_id)
    progress = _get_or_create_progress(db, current_user.id, exp_id)
    report = db.query(ExperimentReport).filter(
        ExperimentReport.progress_id == progress.id
    ).first()
    if not report:
        raise HTTPException(400, "请先填写报告内容")
    report.submitted = True
    db.commit()
    return {"ok": True, "submitted": True}
