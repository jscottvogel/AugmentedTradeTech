import os
import logging
import ulid
import boto3
import json
import copy
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select

from apps.api.app.core.database import get_db
from apps.api.app.models.job import Job, JobTechnician, JobPhoto, JobNote, JobStatusHistory, JobPart
from apps.api.app.models.customer import Customer, Equipment
from apps.api.app.models.company import Company
from apps.api.app.models.sync import SyncQueue
from apps.api.app.routers.jobs import serialize_job, VALID_TRANSITIONS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["sync"])

# --- Request Schemas ---

class SyncItem(BaseModel):
    idempotency_key: str
    entity_type: str  # job | note | part | tech
    entity_id: str
    operation: str  # status | create | delete | availability | workflow
    payload: Dict[str, Any]
    client_timestamp: int  # Milliseconds since epoch

class SyncFlushRequest(BaseModel):
    items: List[SyncItem]

class PhotoUploadItem(BaseModel):
    idempotency_key: str
    s3_key: str
    job_id: str
    step_key: Optional[str] = None
    photo_type: str  # nameplate | fault | before | after | general

class SyncPhotosConfirmRequest(BaseModel):
    photo_uploads: List[PhotoUploadItem]

# --- Helper function to apply a mutation ---

def apply_mutation(db: Session, item: SyncItem, user_id: str, company_id: str, role: str) -> Dict[str, Any]:
    if item.entity_type == "tech" and item.operation == "availability":
        from apps.api.app.routers.jobs import update_tech_availability
        from apps.api.app.models.user import User
        from apps.api.app.routers.me import serialize_me_user
        
        status_val = item.payload.get("status")
        valid_statuses = ["available", "on_job", "driving", "break", "off_duty", "offline"]
        if status_val not in valid_statuses:
            raise ValueError(f"Invalid availability status: {status_val}")
            
        update_tech_availability(db, company_id, user_id, status_val)
        
        user = db.scalar(select(User).where(User.id == user_id))
        if user:
            return serialize_me_user(user)
        return {"success": True}

    # Job-related mutations
    job = db.scalar(
        select(Job)
        .where(Job.id == item.entity_id)
        .where(Job.deleted_at.is_(None))
    )
    if not job:
        raise ValueError(f"Job {item.entity_id} not found")

    if role == "tech":
        is_assigned = db.scalar(
            select(JobTechnician)
            .where(JobTechnician.job_id == job.id)
            .where(JobTechnician.tech_id == user_id)
        )
        if not is_assigned:
            raise PermissionError("Access denied. You are not assigned to this job.")

    if item.entity_type == "job" and item.operation == "status":
        new_status = item.payload.get("status")
        note = item.payload.get("note")
        
        old_status = job.status
        if old_status != new_status:
            allowed = VALID_TRANSITIONS.get(old_status, [])
            if new_status not in allowed and new_status not in ["follow_up_required", "cancelled"]:
                raise ValueError(f"Invalid transition from '{old_status}' to '{new_status}'.")
            
            current_time = datetime.now(timezone.utc)
            job.status = new_status
            job.updated_at = current_time
            job.updated_by = user_id
            
            if new_status == "on_site" and not job.arrived_at:
                job.arrived_at = current_time
            elif new_status == "completed":
                if not job.completed_at:
                    job.completed_at = current_time
                try:
                    from apps.api.app.routers.invoices import create_draft_invoice_from_job
                    create_draft_invoice_from_job(db, job, user_id)
                except Exception as e:
                    logger.error(f"Error auto-drafting invoice for job {job.id}: {e}", exc_info=True)
            
            hist = JobStatusHistory(
                id=f"jsh_{ulid.new()}",
                company_id=company_id,
                job_id=job.id,
                from_status=old_status,
                to_status=new_status,
                changed_by=user_id,
                note=note
            )
            db.add(hist)
            
            # Update technician availability based on status change
            lead_tech = db.scalar(
                select(JobTechnician)
                .where(JobTechnician.job_id == job.id)
                .where(JobTechnician.is_lead == True)
            )
            if lead_tech:
                from apps.api.app.routers.jobs import update_tech_availability
                if new_status == "on_site":
                    update_tech_availability(db, company_id, lead_tech.tech_id, "on_job")
                elif new_status == "completed":
                    update_tech_availability(db, company_id, lead_tech.tech_id, "available")
            
            db.flush()
            
            # Send SNS notification to customer on key transitions
            from apps.api.app.routers.jobs import publish_sns_notification
            customer = db.scalar(select(Customer).where(Customer.id == job.customer_id))
            if customer:
                message = None
                if new_status == "en_route":
                    message = "Your tech is on the way"
                elif new_status == "on_site":
                    message = "Your tech has arrived"
                elif new_status == "completed":
                    message = "Job complete — invoice on its way"
                if message:
                    publish_sns_notification(customer.phone, message)

        return serialize_job(job)

    elif item.entity_type == "note" and item.operation == "create":
        note_id = f"jnt_{ulid.new()}"
        note = JobNote(
            id=note_id,
            company_id=company_id,
            job_id=job.id,
            author_id=user_id,
            note_type=item.payload.get("note_type") or "general",
            body=item.payload.get("body"),
            is_internal=item.payload.get("is_internal", True),
            created_by=user_id,
            updated_by=user_id
        )
        db.add(note)
        job.updated_at = datetime.now(timezone.utc)
        job.updated_by = user_id
        db.flush()
        return serialize_job(job)

    elif item.entity_type == "part" and item.operation == "create":
        part_id = f"jp_{ulid.new()}"
        part = JobPart(
            id=part_id,
            company_id=company_id,
            job_id=job.id,
            name=item.payload.get("name"),
            quantity=item.payload.get("quantity") or 1,
            price_cents=item.payload.get("price_cents") or 0,
            serial_number=item.payload.get("serial_number"),
            created_by=user_id,
            updated_by=user_id
        )
        db.add(part)
        job.updated_at = datetime.now(timezone.utc)
        job.updated_by = user_id
        db.flush()
        return serialize_job(job)

    elif item.entity_type == "part" and item.operation == "delete":
        part_id = item.payload.get("partId")
        part = db.scalar(
            select(JobPart)
            .where(JobPart.id == part_id)
            .where(JobPart.job_id == job.id)
        )
        if not part:
            raise ValueError(f"Part {part_id} not found")
        db.delete(part)
        job.updated_at = datetime.now(timezone.utc)
        job.updated_by = user_id
        db.flush()
        return serialize_job(job)

    elif item.entity_type == "job" and item.operation == "workflow":
        step = item.payload.get("step")
        inputs = item.payload.get("inputs")
        skipped = item.payload.get("skipped", False)
        idempotency_key = item.payload.get("idempotency_key")
        
        company = db.scalar(select(Company).where(Company.id == job.company_id))
        if not company:
            raise ValueError("Company not found")
            
        from apps.api.app.core.workflows import DEFAULT_WORKFLOW_CONFIG
        
        trade_config = None
        if company.workflow_config and job.trade in company.workflow_config:
            trade_config = company.workflow_config[job.trade]
        else:
            trade_config = DEFAULT_WORKFLOW_CONFIG.get(job.trade)
            
        if not trade_config:
            raise ValueError(f"No workflow config found for trade '{job.trade}'")
            
        steps_list = trade_config.get("steps", [])
        valid_step_keys = {s["key"] for s in steps_list}
        if step not in valid_step_keys:
            raise ValueError(f"Invalid step key '{step}' for trade '{job.trade}'")
            
        current_data = job.inspection_data or {}
        existing_step = current_data.get(step, {})
        if existing_step and existing_step.get("idempotency_key") == idempotency_key:
            return serialize_job(job)
            
        new_data = copy.deepcopy(current_data)
        existing_ai_result = existing_step.get("ai_result") if existing_step else None
        
        new_data[step] = {
            "inputs": inputs,
            "ai_result": existing_ai_result,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "skipped": skipped,
            "idempotency_key": idempotency_key
        }
        
        job.inspection_data = new_data
        job.updated_at = datetime.now(timezone.utc)
        job.updated_by = user_id
        db.add(job)
        db.flush()
        return serialize_job(job)

    else:
        raise ValueError(f"Unsupported mutation entity_type={item.entity_type}, operation={item.operation}")

# --- Endpoints ---

@router.post("/flush")
def flush_sync_queue(
    req: SyncFlushRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    user_id = getattr(request.state, "user_id", None)
    company_id = getattr(request.state, "company_id", None)
    role = getattr(request.state, "role", None)

    if not user_id or not company_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Sort items by (entity_id, client_timestamp)
    sorted_items = sorted(req.items, key=lambda x: (x.entity_id, x.client_timestamp))

    results = []

    for item in sorted_items:
        # 1. Check idempotency key
        existing_sq = db.scalar(
            select(SyncQueue)
            .where(SyncQueue.idempotency_key == item.idempotency_key)
            .where(SyncQueue.company_id == company_id)
        )
        if existing_sq:
            results.append({
                "idempotency_key": item.idempotency_key,
                "status": existing_sq.status,
                "server_response": existing_sq.server_response
            })
            continue

        # 2. Check conflicts if applicable
        # Compare server updated_at against client last_known_updated_at
        conflict_detected = False
        server_state = None
        last_known_str = item.payload.get("last_known_updated_at")

        # Load main Job to check updated_at
        job = None
        if item.entity_type in ["job", "note", "part"]:
            job = db.scalar(select(Job).where(Job.id == item.entity_id))

        if job and last_known_str:
            try:
                # Normalize Z suffix to +00:00 for python's fromisoformat
                client_time = datetime.fromisoformat(last_known_str.replace("Z", "+00:00"))
                if client_time.tzinfo is None:
                    client_time = client_time.replace(tzinfo=timezone.utc)
                
                # Check conflict
                if job.updated_at and job.updated_at > client_time:
                    conflict_detected = True
                    server_state = serialize_job(job)
            except Exception as parse_err:
                logger.warning(f"Failed to parse last_known_updated_at ISO string '{last_known_str}': {parse_err}")

        # Declare status and responses
        status_val = "pending"
        conflict_detail = None
        server_response = None

        if conflict_detected:
            status_val = "conflict"
            conflict_detail = {
                "server_state": server_state,
                "client_payload": item.payload
            }
            server_response = server_state
        else:
            try:
                # Apply mutation
                res_payload = apply_mutation(db, item, user_id, company_id, role)
                status_val = "applied"
                server_response = res_payload
            except Exception as e:
                db.rollback()
                logger.error(f"Error applying sync mutation: {e}", exc_info=True)
                status_val = "failed"
                server_response = {"error": str(e)}

        # Parse client timestamp
        try:
            client_ts_dt = datetime.fromtimestamp(item.client_timestamp / 1000.0, tz=timezone.utc)
        except Exception:
            client_ts_dt = datetime.now(timezone.utc)

        # 3. Create SyncQueue entry
        sq = SyncQueue(
            id=f"sq_{ulid.new()}",
            company_id=company_id,
            user_id=user_id,
            entity_type=item.entity_type,
            entity_id=item.entity_id,
            operation=item.operation,
            payload=item.payload,
            client_timestamp=client_ts_dt,
            idempotency_key=item.idempotency_key,
            status=status_val,
            conflict_detail=conflict_detail,
            server_response=server_response,
            attempts=1,
            last_attempted_at=datetime.now(timezone.utc),
            applied_at=datetime.now(timezone.utc) if status_val == "applied" else None
        )
        db.add(sq)
        db.flush()

        results.append({
            "idempotency_key": item.idempotency_key,
            "status": status_val,
            "server_response": server_response
        })

        # 4. SQS Publish
        queue_url = None
        try:
            from sst import Resource
            if hasattr(Resource, "SyncQueue"):
                queue_url = Resource.SyncQueue.url
            elif hasattr(Resource, "sync-queue"):
                queue_url = Resource["sync-queue"].url
            elif "SyncQueue" in Resource:
                queue_url = Resource["SyncQueue"].url
        except Exception:
            pass

        if queue_url:
            try:
                sqs = boto3.client("sqs")
                sqs.send_message(
                    QueueUrl=queue_url,
                    MessageBody=json.dumps({
                        "sync_queue_id": sq.id,
                        "idempotency_key": sq.idempotency_key,
                        "entity_type": sq.entity_type,
                        "entity_id": sq.entity_id,
                        "operation": sq.operation,
                        "payload": sq.payload,
                        "company_id": sq.company_id,
                        "user_id": sq.user_id,
                        "status": sq.status
                    })
                )
            except Exception as sqs_err:
                logger.error(f"Failed to queue sync event via SQS: {sqs_err}")
        else:
            logger.info(f"[LOCAL] Simulated SQS SyncQueue message: {item.idempotency_key}")

    # Commit transactions
    db.commit()

    return {"results": results}


@router.post("/photos/confirm")
async def confirm_photo_sync(
    req: SyncPhotosConfirmRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    user_id = getattr(request.state, "user_id", None)
    company_id = getattr(request.state, "company_id", None)

    if not user_id or not company_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    results = []

    for item in req.photo_uploads:
        # Check if already registered (by s3_key)
        existing = db.scalar(
            select(JobPhoto)
            .where(JobPhoto.s3_key == item.s3_key)
        )
        if existing:
            results.append({
                "idempotency_key": item.idempotency_key,
                "photo_id": existing.id,
                "status": "already_registered"
            })
            continue

        # Load job
        job = db.scalar(select(Job).where(Job.id == item.job_id))
        if not job:
            results.append({
                "idempotency_key": item.idempotency_key,
                "status": "error",
                "message": f"Job {item.job_id} not found"
            })
            continue

        # Construct CDN URL
        cdn_domain = os.getenv("CDN_DOMAIN")
        if not cdn_domain:
            try:
                from sst import Resource
                if hasattr(Resource, "MediaBucket"):
                    cdn_domain = getattr(Resource.MediaBucket, "domain", None)
            except Exception:
                pass
        if not cdn_domain:
            cdn_domain = "media.augmentedtradetech.com"

        db_cdn_url = f"https://{cdn_domain}/{item.s3_key}"
        photo_id = f"jph_{ulid.new()}"

        new_photo = JobPhoto(
            id=photo_id,
            company_id=company_id,
            job_id=item.job_id,
            tech_id=user_id,
            step_key=item.step_key,
            photo_type=item.photo_type,
            s3_key=item.s3_key,
            cdn_url=db_cdn_url,
            caption=f"Sync photo for step: {item.step_key or 'general'}",
            mime_type="image/jpeg",
            created_by=user_id
        )
        db.add(new_photo)
        db.flush()

        # Trigger AI Analysis if nameplate or fault
        analysis_type = None
        if item.photo_type == "nameplate":
            analysis_type = "nameplate_scan"
        elif item.photo_type == "fault":
            analysis_type = "fault_analysis"

        if analysis_type:
            try:
                from apps.api.app.routers.ai import analyze_photo_internal
                ai_result = await analyze_photo_internal(
                    photo_id=photo_id,
                    analysis_type=analysis_type,
                    job_id=item.job_id,
                    request=request,
                    db=db
                )
                # Auto-populate equipment fields for nameplate scan if successful
                if analysis_type == "nameplate_scan" and ai_result and not isinstance(ai_result, JSONResponse):
                    if not ai_result.get("prompt_retake", False):
                        if job.equipment_id:
                            equipment = db.scalar(select(Equipment).where(Equipment.id == job.equipment_id))
                            if equipment:
                                if "make" in ai_result and ai_result["make"].get("value"):
                                    equipment.make = ai_result["make"]["value"]
                                if "model" in ai_result and ai_result["model"].get("value"):
                                    equipment.model = ai_result["model"]["value"]
                                if "serial_number" in ai_result and ai_result["serial_number"].get("value"):
                                    equipment.serial_number = ai_result["serial_number"]["value"]
                                equipment.ai_extracted_data = ai_result
                                db.add(equipment)
                                db.flush()
            except Exception as ai_err:
                logger.error(f"AI analysis trigger failed for photo {photo_id}: {ai_err}")

        results.append({
            "idempotency_key": item.idempotency_key,
            "photo_id": photo_id,
            "status": "registered"
        })

    db.commit()

    return {"results": results}
