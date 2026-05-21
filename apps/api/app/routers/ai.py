import os
import base64
import json
import logging
import asyncio
import copy
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from pydantic import BaseModel, Field
import boto3
import httpx
import ulid

from apps.api.app.core.database import get_db, SessionLocal, set_rls_context, IS_TESTING
from apps.api.app.services.diagnosis_pipeline import run_diagnosis_pipeline
from apps.api.app.models.ai import AIRequest
from apps.api.app.models.job import Job, JobPhoto, JobTechnician
from apps.api.app.models.customer import Customer, Equipment, EquipmentCustomer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])
equipment_router = APIRouter(prefix="/equipment", tags=["equipment"])

# Global concurrency tracker
CONCURRENT_REQUESTS = 0
CONCURRENT_REQUESTS_LOCK = asyncio.Lock()

# Pydantic Schemas
class AnalyzePhotoRequest(BaseModel):
    photo_id: str
    analysis_type: str  # nameplate_scan | fault_analysis | wiring_analysis
    job_id: str

class AnalyzeNameplateRequest(BaseModel):
    photo_id: str
    job_id: str
    equipment_id: Optional[str] = None

class EquipmentPatchRequest(BaseModel):
    make: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    ai_extracted_data: Optional[Dict[str, Any]] = None

PROMPTS = {
    "nameplate_scan": {
        "system": (
            "You are an expert HVAC and garage door nameplate scanner. Analyze the provided image of an equipment nameplate.\n"
            "Extract the following fields from the image if visible. For each field, provide a 'value' and a 'confidence' score between 0.0 and 1.0. If a field cannot be read or is not present, set 'value' to null and 'confidence' to 0.0.\n"
            "Fields to extract:\n"
            "- make (string): Brand or manufacturer name (e.g. Carrier, Lennox)\n"
            "- model (string): Model number\n"
            "- serial_number (string): Serial number\n"
            "- manufacture_date (string or null): Date of manufacture (e.g. YYYY-MM or MM/YYYY)\n"
            "- tonnage (float or null): Equipment capacity in tons (often decoded from model number, e.g., 24 = 2.0 tons, 36 = 3.0 tons)\n"
            "- voltage (string or null): Voltage supply rating (e.g. 208-230V, 115V)\n"
            "- refrigerant_type (string or null): Type of refrigerant used (e.g. R-410A, R-22)\n"
            "- efficiency_rating (string or null): SEER/EER or efficiency rating if listed\n\n"
            "If you cannot read the nameplate clearly at all due to blurriness, obstruction, or low resolution, set 'prompt_retake' to true and explain why in a 'message' field. Otherwise, set 'prompt_retake' to false.\n\n"
            "Return the output ONLY as a flat JSON object with the keys: 'make', 'model', 'serial_number', 'manufacture_date', 'tonnage', 'voltage', 'refrigerant_type', 'efficiency_rating', 'prompt_retake', 'message'. Each of the extraction fields must be an object with 'value' and 'confidence'."
        )
    },
    "fault_analysis": {
        "system": (
            "You are an expert field service technician assistant. Analyze the provided image showing equipment damage, wear, or a fault.\n"
            "Identify:\n"
            "- component_type (string): The part or component shown (e.g. capacitor, contactor, spring, roller, compressor, coil)\n"
            "- visible_damage (string) or failure_mode (string): Describe what damage or failure is visible (e.g. bulged top, burnt terminal, rusted coils, broken spring coil)\n"
            "- severity (string): Choose from: 'critical' (immediate replacement needed, system inoperable), 'moderate' (functioning but failing/degraded), 'minor' (wear and tear, needs monitoring)\n"
            "- likely_cause (string): Most probable reason for this condition\n"
            "- recommended_action (string): Action required to fix or address the issue\n"
            "- safety_concerns (string): Any safety hazards related to this fault (e.g. electrical shock hazard, high pressure hazard, spring under tension hazard)\n\n"
            "Provide a confidence score between 0.0 and 1.0 for each identified field.\n"
            "Return the output ONLY as a valid JSON object containing these keys."
        )
    },
    "wiring_analysis": {
        "system": (
            "You are an expert electrical and field service inspector. Analyze the provided image focusing on electrical wiring, terminals, and connections.\n"
            "Identify:\n"
            "- wiring_issues (string): Describe any wiring anomalies (e.g. loose connections, exposed copper, corroded terminals, melted insulation, incorrect wire sizing)\n"
            "- component_condition (string): Describe the overall condition of the electrical components shown\n"
            "- voltage_hazards (string): Mention any specific voltage or safety hazards observed\n\n"
            "Provide a confidence score between 0.0 and 1.0 for each identified field.\n"
            "Return the output ONLY as a valid JSON object containing these keys."
        )
    }
}

async def analyze_photo_internal(
    photo_id: str,
    analysis_type: str,
    job_id: str,
    request: Request,
    db: Session
) -> Any:
    """Internal helper carrying out the rate limits, concurrency check, S3 fetch, and Claude API invocation"""
    global CONCURRENT_REQUESTS

    role = request.state.role
    user_id = request.state.user_id
    company_id = request.state.company_id

    # 1. Validate analysis type
    if analysis_type not in ["nameplate_scan", "fault_analysis", "wiring_analysis"]:
        raise HTTPException(status_code=400, detail="Invalid analysis type")

    # 2. Check existence of Job and Photo under RLS context
    job = db.scalar(
        select(Job)
        .where(Job.id == job_id)
        .where(Job.company_id == company_id)
        .where(Job.deleted_at.is_(None))
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or access denied")

    # If technician, verify assigned to the job
    if role == "tech":
        is_assigned = db.scalar(
            select(JobTechnician)
            .where(JobTechnician.job_id == job_id)
            .where(JobTechnician.tech_id == user_id)
        )
        if not is_assigned:
            raise HTTPException(status_code=403, detail="Not authorized to access this job's photos")

    photo = db.scalar(
        select(JobPhoto)
        .where(JobPhoto.id == photo_id)
        .where(JobPhoto.job_id == job_id)
        .where(JobPhoto.company_id == company_id)
        .where(JobPhoto.deleted_at.is_(None))
    )
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found or access denied")

    # 3. Rate Limit check: max 10 AI photo analyses per job
    analysis_count = db.scalar(
        select(func.count(AIRequest.id))
        .where(AIRequest.job_id == job_id)
        .where(AIRequest.request_type.in_(["nameplate_scan", "fault_analysis", "wiring_analysis"]))
    )
    if analysis_count >= 10:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded: Maximum of 10 AI photo analyses permitted per job"
        )

    # 4. Check Concurrency Limit: queue if concurrent active requests exceed 5
    is_queued = False
    async with CONCURRENT_REQUESTS_LOCK:
        if CONCURRENT_REQUESTS >= 5:
            is_queued = True

    if is_queued:
        # Enqueue request to SQS
        queue_url = None
        try:
            from sst import Resource
            if hasattr(Resource, "ai-queue"):
                queue_url = Resource["ai-queue"].url
        except Exception:
            pass

        if queue_url:
            try:
                sqs = boto3.client("sqs")
                sqs.send_message(
                    QueueUrl=queue_url,
                    MessageBody=json.dumps({
                        "photo_id": photo_id,
                        "analysis_type": analysis_type,
                        "job_id": job_id,
                        "user_id": user_id,
                        "company_id": company_id
                    })
                )
                logger.info(f"AI photo analysis request {photo_id} enqueued to SQS successfully.")
            except Exception as sqs_err:
                logger.error(f"Failed to queue request via SQS: {sqs_err}")
        else:
            logger.info("SQS queue not available locally, simulating SQS enqueue successfully.")

        # Log pending/queued AIRequest entry to database
        ai_req = AIRequest(
            id=f"ai_{ulid.new()}",
            company_id=company_id,
            user_id=user_id,
            job_id=job_id,
            request_type=analysis_type,
            model="claude-3-5-sonnet",
            input_tokens=0,
            output_tokens=0,
            cost_usd_micro=0,
            feature_tag="photo_analysis",
            cache_hit=False,
            latency_ms=0,
            status="queued"
        )
        db.add(ai_req)
        db.commit()

        return JSONResponse(
            status_code=202,
            content={
                "status": "queued",
                "message": "Concurrent AI request threshold exceeded. Request enqueued to SQS ai-queue.",
                "photo_id": photo_id
            }
        )

    # 5. Execute AI photo analysis synchronously (Increment concurrent counter)
    async with CONCURRENT_REQUESTS_LOCK:
        CONCURRENT_REQUESTS += 1

    try:
        api_key = os.getenv("ANTHROPIC_API_KEY")

        if api_key:
            # A. Fetch image from S3 and convert to Base64
            bucket_name = None
            try:
                from sst import Resource
                if hasattr(Resource, "MediaBucket"):
                    bucket_name = Resource.MediaBucket.name
            except Exception:
                pass

            base64_image = None
            if bucket_name:
                try:
                    s3_client = boto3.client("s3")
                    s3_obj = s3_client.get_object(Bucket=bucket_name, Key=photo.s3_key)
                    base64_image = base64.b64encode(s3_obj["Body"].read()).decode("utf-8")
                except Exception as e:
                    logger.warning(f"Failed to fetch image from S3 bucket: {e}")

            if not base64_image:
                # Fallback to empty transparent pixel for debugging/testing
                base64_image = "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA="

            # B. Prepare Claude Vision payload
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
            body = {
                "model": "claude-3-5-sonnet-20241022",
                "max_tokens": 4096,
                "system": PROMPTS[analysis_type]["system"],
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": photo.mime_type or "image/jpeg",
                                    "data": base64_image
                                }
                            },
                            {
                                "type": "text",
                                "text": "Analyze this photo based on the system instructions. Return ONLY a valid JSON object matching the requested schema. Do not wrap in markdown blocks."
                            }
                        ]
                    }
                ]
            }

            start_time = datetime.now()
            async with httpx.AsyncClient() as http_client:
                response = await http_client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json=body,
                    timeout=60.0
                )
            latency = int((datetime.now() - start_time).total_seconds() * 1000)

            if response.status_code != 200:
                logger.error(f"Claude API failed: {response.text}")
                raise HTTPException(status_code=502, detail="Anthropic Claude API returned an error response")

            res_json = response.json()
            input_tokens = res_json["usage"]["input_tokens"]
            output_tokens = res_json["usage"]["output_tokens"]
            cost_usd_micro = int((input_tokens * 3.0) + (output_tokens * 15.0))

            content_text = res_json["content"][0]["text"].strip()
            # Clean JSON format block if Claude wraps it in markdown code fences
            if content_text.startswith("```"):
                lines = content_text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                content_text = "\n".join(lines).strip()

            analysis_result = json.loads(content_text)

        else:
            # C. Mock AI Analysis in local dev environment
            logger.info("Local environment missing ANTHROPIC_API_KEY. Simulating Claude API vision response.")
            input_tokens = 450
            output_tokens = 220
            cost_usd_micro = int((input_tokens * 3.0) + (output_tokens * 15.0))
            latency = 180

            is_blurry = (
                photo.id == "jph_blurry" or
                (photo.caption and "blurry" in photo.caption.lower())
            )

            if is_blurry and analysis_type == "nameplate_scan":
                analysis_result = {
                    "make": {"value": None, "confidence": 0.0},
                    "model": {"value": None, "confidence": 0.0},
                    "serial_number": {"value": None, "confidence": 0.0},
                    "manufacture_date": {"value": None, "confidence": 0.0},
                    "tonnage": {"value": None, "confidence": 0.0},
                    "voltage": {"value": None, "confidence": 0.0},
                    "refrigerant_type": {"value": None, "confidence": 0.0},
                    "efficiency_rating": {"value": None, "confidence": 0.0},
                    "prompt_retake": True,
                    "message": "Image is blurry and cannot be read. Please retake the photo."
                }
            elif analysis_type == "nameplate_scan":
                analysis_result = {
                    "make": {"value": "Carrier", "confidence": 0.95},
                    "model": {"value": "58SB0A045E14--12", "confidence": 0.90},
                    "serial_number": {"value": "1218A12345", "confidence": 0.99},
                    "manufacture_date": {"value": "2018-03", "confidence": 0.85},
                    "tonnage": {"value": 2.0, "confidence": 0.90},
                    "voltage": {"value": "115V", "confidence": 0.95},
                    "refrigerant_type": {"value": "R-410A", "confidence": 0.90},
                    "efficiency_rating": {"value": "14 SEER", "confidence": 0.80},
                    "prompt_retake": False,
                    "message": "Nameplate read successfully"
                }
            elif analysis_type == "fault_analysis":
                analysis_result = {
                    "component_type": "capacitor",
                    "visible_damage": "bulged top and leaking dielectric fluid",
                    "severity": "critical",
                    "likely_cause": "electrical surge or end of operating life",
                    "recommended_action": "Replace capacitor with matching 45uF dual-run capacitor",
                    "safety_concerns": "high voltage shock hazard from residual charge"
                }
            else:  # wiring_analysis
                analysis_result = {
                    "wiring_issues": "corroded terminals and loose ground connection",
                    "component_condition": "fair but showing significant oxidation on high-voltage lead connections",
                    "voltage_hazards": "arc flash hazard due to loose connection near contactor terminal block"
                }

        # D. Store AI analysis results in JobPhoto
        photo.ai_analysis = analysis_result
        db.commit()

        # E. Log entry in ai_requests
        ai_req = AIRequest(
            id=f"ai_{ulid.new()}",
            company_id=company_id,
            user_id=user_id,
            job_id=job_id,
            request_type=analysis_type,
            model="claude-3-5-sonnet-20241022" if api_key else "claude-3-5-sonnet",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd_micro=cost_usd_micro,
            feature_tag="photo_analysis",
            cache_hit=False,
            latency_ms=latency,
            status="success"
        )
        db.add(ai_req)
        db.commit()

        return analysis_result

    except Exception as run_err:
        logger.error(f"Error executing AI photo analysis: {run_err}")
        # Log failed AIRequest
        try:
            ai_req_fail = AIRequest(
                id=f"ai_{ulid.new()}",
                company_id=company_id,
                user_id=user_id,
                job_id=job_id,
                request_type=analysis_type,
                model="claude-3-5-sonnet",
                input_tokens=0,
                output_tokens=0,
                cost_usd_micro=0,
                feature_tag="photo_analysis",
                cache_hit=False,
                latency_ms=0,
                status="error",
                error_detail=str(run_err)
            )
            db.add(ai_req_fail)
            db.commit()
        except Exception as log_err:
            logger.error(f"Failed to log failed AIRequest to DB: {log_err}")
        raise run_err

    finally:
        async with CONCURRENT_REQUESTS_LOCK:
            CONCURRENT_REQUESTS -= 1


@router.post("/analyze-photo")
async def analyze_photo(
    payload: AnalyzePhotoRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Analyze photo endpoint verifying limits and executing Claude/Mock Vision scan"""
    result = await analyze_photo_internal(
        photo_id=payload.photo_id,
        analysis_type=payload.analysis_type,
        job_id=payload.job_id,
        request=request,
        db=db
    )

    # If nameplate scan succeeded and the job has an equipment record, auto-populate it
    if payload.analysis_type == "nameplate_scan" and not isinstance(result, JSONResponse):
        # Check if the result has successfully read fields and is not prompting retake
        if not result.get("prompt_retake", False):
            job = db.scalar(select(Job).where(Job.id == payload.job_id))
            if job and job.equipment_id:
                equipment = db.scalar(select(Equipment).where(Equipment.id == job.equipment_id))
                if equipment:
                    if "make" in result and result["make"].get("value"):
                        equipment.make = result["make"]["value"]
                    if "model" in result and result["model"].get("value"):
                        equipment.model = result["model"]["value"]
                    if "serial_number" in result and result["serial_number"].get("value"):
                        equipment.serial_number = result["serial_number"]["value"]
                    equipment.ai_extracted_data = result
                    db.commit()

    return result


@router.post("/analyze-nameplate")
async def analyze_nameplate(
    payload: AnalyzeNameplateRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Convenience endpoint calling analyze-photo with nameplate scan, then patching equipment fields"""
    result = await analyze_photo_internal(
        photo_id=payload.photo_id,
        analysis_type="nameplate_scan",
        job_id=payload.job_id,
        request=request,
        db=db
    )

    if isinstance(result, JSONResponse) and result.status_code == 202:
        return result

    # Verify if scan succeeded and prompt_retake is false
    if not result.get("prompt_retake", False):
        # Resolve target equipment ID
        equipment_id = payload.equipment_id
        if not equipment_id:
            job = db.scalar(select(Job).where(Job.id == payload.job_id))
            if job:
                equipment_id = job.equipment_id

        if equipment_id:
            company_id = request.state.company_id
            equipment = db.scalar(
                select(Equipment)
                .where(Equipment.id == equipment_id)
                .where(Equipment.company_id == company_id)
            )
            if equipment:
                if "make" in result and result["make"].get("value"):
                    equipment.make = result["make"]["value"]
                if "model" in result and result["model"].get("value"):
                    equipment.model = result["model"]["value"]
                if "serial_number" in result and result["serial_number"].get("value"):
                    equipment.serial_number = result["serial_number"]["value"]
                
                # Merge or set AI extracted data
                equipment.ai_extracted_data = result
                db.commit()

    return result


@equipment_router.patch("/{id}")
def patch_equipment(
    id: str,
    payload: EquipmentPatchRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """PATCH endpoint to update equipment record details"""
    company_id = request.state.company_id
    equipment = db.scalar(
        select(Equipment)
        .where(Equipment.id == id)
        .where(Equipment.company_id == company_id)
    )
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")

    if payload.make is not None:
        equipment.make = payload.make
    if payload.model is not None:
        equipment.model = payload.model
    if payload.serial_number is not None:
        equipment.serial_number = payload.serial_number
    if payload.ai_extracted_data is not None:
        # Shallow merge existing and new ai_extracted_data if both exist
        existing = equipment.ai_extracted_data or {}
        merged = {**existing, **payload.ai_extracted_data}
        equipment.ai_extracted_data = merged

    db.commit()
    db.refresh(equipment)

    return {
        "id": equipment.id,
        "trade": equipment.trade,
        "equipment_type": equipment.equipment_type,
        "make": equipment.make,
        "model": equipment.model,
        "serial_number": equipment.serial_number,
        "ai_extracted_data": equipment.ai_extracted_data
    }


@router.post("/diagnose/{job_id}")
async def diagnose_job(
    job_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Triggers the LangGraph AI diagnosis pipeline for the specified job.
    Enqueues to SQS ai-queue, falling back to an async task in local/development.
    """
    company_id = request.state.company_id
    
    # 1. Verify Job exists and belongs to the company
    job = db.scalar(select(Job).where(Job.id == job_id, Job.company_id == company_id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    # 2. Check if SQS queue is available (SST linked resource)
    queue_url = None
    try:
        from sst import Resource
        if hasattr(Resource, "ai-queue"):
            queue_url = Resource["ai-queue"].url
    except Exception:
        pass
        
    if queue_url:
        try:
            sqs = boto3.client("sqs")
            sqs.send_message(
                QueueUrl=queue_url,
                MessageBody=json.dumps({
                    "action": "diagnose",
                    "job_id": job_id,
                    "company_id": company_id
                })
            )
            logger.info(f"AI diagnosis request for job {job_id} enqueued to SQS successfully.")
        except Exception as sqs_err:
            logger.error(f"Failed to queue AI diagnosis via SQS: {sqs_err}")
            queue_url = None
            
    if not queue_url:
        logger.info("SQS queue not available. Running AI diagnosis pipeline in background.")
        
        if not IS_TESTING:
            async def run_in_background(j_id: str, comp_id: str):
                bg_db = SessionLocal()
                try:
                    set_rls_context(bg_db, comp_id, None, "system")
                    await run_diagnosis_pipeline(j_id, bg_db)
                except Exception as e:
                    logger.error(f"Error executing background AI diagnosis pipeline: {e}")
                finally:
                    bg_db.close()
                    
            asyncio.create_task(run_in_background(job_id, company_id))
        else:
            logger.info("Skipping background task creation because IS_TESTING is True.")
        
    return {
        "job_id": job_id,
        "status": "queued"
    }


# --- 'Senior Tech' AI Chat Endpoint ---

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    job_id: str
    messages: List[ChatMessage]

@router.post("/chat")
async def ai_chat_stream(
    req: ChatRequest,
    request: Request
):
    """
    Streams a response from the 'Senior Tech' AI chat via SSE (Server-Sent Events).
    Logs the token counts, cost, and latency in the ai_requests table.
    """
    role = request.state.role
    user_id = request.state.user_id
    company_id = request.state.company_id

    # 1. Synchronously verify authorization before returning the stream
    auth_db = SessionLocal()
    try:
        set_rls_context(auth_db, company_id, user_id, role)
        job = auth_db.scalar(select(Job).where(Job.id == req.job_id, Job.company_id == company_id))
        if not job:
            logger.warning(f"Job {req.job_id} not found under company {company_id} for user {user_id}")
            raise HTTPException(status_code=404, detail="Job not found")
        if role == "tech":
            is_assigned = auth_db.scalar(
                select(JobTechnician)
                .where(JobTechnician.job_id == req.job_id)
                .where(JobTechnician.tech_id == user_id)
            )
            if not is_assigned:
                logger.warning(f"Technician {user_id} is not assigned to job {req.job_id}")
                raise HTTPException(status_code=403, detail="Not authorized to access this job's chat")
    finally:
        auth_db.close()

    async def event_generator():
        db = SessionLocal()
        try:
            set_rls_context(db, company_id, user_id, role)
            
            # Load context details (similar to context_loader_node)
            job = db.scalar(select(Job).where(Job.id == req.job_id))
            if not job:
                yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
                return

            customer = None
            if job.customer_id:
                customer = db.scalar(select(Customer).where(Customer.id == job.customer_id))

            equipment = None
            if job.equipment_id:
                equipment = db.scalar(select(Equipment).where(Equipment.id == job.equipment_id))

            # Fetch service history (prior completed jobs on same equipment)
            service_history = []
            if job.equipment_id:
                prior_jobs = db.scalars(
                    select(Job)
                    .where(
                        Job.equipment_id == job.equipment_id,
                        Job.id != req.job_id,
                        Job.status == "completed"
                    )
                    .order_by(Job.completed_at.desc())
                ).all()
                for pj in prior_jobs:
                    service_history.append({
                        "job_number": pj.job_number,
                        "completed_at": pj.completed_at.isoformat() if pj.completed_at else None,
                        "ai_diagnosis": pj.ai_diagnosis
                    })

            # Fetch job photos
            photos = db.scalars(
                select(JobPhoto)
                .where(JobPhoto.job_id == req.job_id, JobPhoto.deleted_at.is_(None))
            ).all()
            photos_data = []
            for p in photos:
                photos_data.append({
                    "photo_type": p.photo_type,
                    "caption": p.caption,
                    "ai_analysis": p.ai_analysis
                })

            trade = job.trade or "hvac"
            trade_name = "HVAC" if trade.lower() == "hvac" else "Garage Door"

            customer_str = "Unknown"
            if customer:
                customer_str = f"{customer.first_name} {customer.last_name}"

            equipment_str = "None"
            if equipment:
                equipment_age = "Unknown"
                if equipment.install_date:
                    from datetime import date
                    equipment_age = f"{date.today().year - equipment.install_date.year} years"
                
                equipment_str = (
                    f"Type: {equipment.equipment_type}\n"
                    f"Make: {equipment.make or 'Unknown'}\n"
                    f"Model: {equipment.model or 'Unknown'}\n"
                    f"Serial Number: {equipment.serial_number or 'Unknown'}\n"
                    f"Age: {equipment_age} (Installed: {equipment.install_date or 'Unknown'})"
                )

            # Format inspection readings
            readings_list = []
            if job.inspection_data:
                for step_key, step_val in job.inspection_data.items():
                    if isinstance(step_val, dict):
                        inputs = step_val.get("inputs", {})
                        skipped = step_val.get("skipped", False)
                        if skipped:
                            readings_list.append(f"- {step_key}: Skipped")
                        elif inputs:
                            inputs_str = ", ".join(f"{k}: {v}" for k, v in inputs.items())
                            readings_list.append(f"- {step_key}: {inputs_str}")
            readings_str = "\n".join(readings_list) if readings_list else "No readings logged yet."

            # Format current diagnosis
            diag_str = "No diagnosis generated yet."
            if job.ai_diagnosis:
                diag_summary = job.ai_diagnosis.get("summary", "")
                diag_causes = ", ".join(rc.get("cause", "") for rc in job.ai_diagnosis.get("root_causes", []))
                diag_recs = ", ".join(job.ai_diagnosis.get("recommendations", []))
                diag_str = (
                    f"Summary: {diag_summary}\n"
                    f"Likely Causes: {diag_causes}\n"
                    f"Recommendations: {diag_recs}"
                )

            # Format prior service history
            history_list = []
            for h in service_history:
                diag = h.get("ai_diagnosis") or {}
                summary = diag.get("summary", "No diagnosis details")
                history_list.append(f"- Job {h['job_number']} completed at {h['completed_at']}: {summary}")
            history_str = "\n".join(history_list) if history_list else "No prior service history."

            # Format photo analysis
            photos_list = []
            for p in photos_data:
                analysis = p.get("ai_analysis") or {}
                comp = analysis.get("component_type", "unknown")
                sev = analysis.get("severity", "unknown")
                dmg = analysis.get("visible_damage") or analysis.get("failure_mode") or "None"
                photos_list.append(f"- {p['photo_type']} photo: Component: {comp}, Severity: {sev}, Damage: {dmg}")
            photos_str = "\n".join(photos_list) if photos_list else "No photo analyses logged."

            # Compile system prompt
            system_prompt = (
                f"You are a Senior {trade_name} technician with over 20 years of field experience. "
                "You are acting as a mentor, guiding a junior technician on-site. "
                "Provide trade-specific, technical, concise, and highly practical answers. "
                "Use your knowledge of standard operating procedures, safety guidelines, and troubleshooting techniques. "
                "Always maintain your professional persona as a supportive, seasoned senior tech.\n\n"
                "Here is the context of the current job:\n"
                f"- Job Number: {job.job_number}\n"
                f"- Trade: {trade_name}\n"
                f"- Reported Problem: {job.reported_problem or 'No problem reported'}\n"
                f"- Dispatcher Notes: {job.dispatcher_notes or 'None'}\n"
                f"- Customer: {customer_str}\n\n"
                "Equipment:\n"
                f"{equipment_str}\n\n"
                "Collected Inspection Readings:\n"
                f"{readings_str}\n\n"
                "Job Photos & Vision Analyses:\n"
                f"{photos_str}\n\n"
                "Current AI Diagnosis:\n"
                f"{diag_str}\n\n"
                "Prior Service History on this Equipment:\n"
                f"{history_str}\n\n"
                "Answer the technician's messages directly, keeping your explanations direct, helpful, and safety-focused."
            )

            api_key = os.getenv("ANTHROPIC_API_KEY")
            if api_key:
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                }
                body = {
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 1024,
                    "system": system_prompt,
                    "messages": [{"role": m.role, "content": m.content} for m in req.messages],
                    "stream": True
                }
                
                start_time = datetime.now()
                output_text = ""
                input_tokens = 0
                output_tokens = 0
                
                async with httpx.AsyncClient() as http_client:
                    async with http_client.stream(
                        "POST",
                        "https://api.anthropic.com/v1/messages",
                        headers=headers,
                        json=body,
                        timeout=60.0
                    ) as response:
                        if response.status_code != 200:
                            err_body = await response.aread()
                            logger.error(f"Claude streaming failed with status {response.status_code}: {err_body.decode()}")
                            yield f"data: {json.dumps({'error': 'Claude API returned error status'})}\n\n"
                            return

                        async for line in response.aiter_lines():
                            if not line.strip():
                                continue
                            if line.startswith("data:"):
                                data_str = line[5:].strip()
                                try:
                                    data_json = json.loads(data_str)
                                    event_type = data_json.get("type")
                                    
                                    if event_type == "content_block_delta":
                                        text_delta = data_json["delta"]["text"]
                                        output_text += text_delta
                                        yield f"data: {json.dumps({'text': text_delta})}\n\n"
                                    elif event_type == "message_start":
                                        input_tokens = data_json["message"]["usage"]["input_tokens"]
                                    elif event_type == "message_delta":
                                        output_tokens = data_json["usage"]["output_tokens"]
                                except Exception as parse_err:
                                    logger.warning(f"Error parsing Claude stream line: {parse_err}")
                
                # Stream finished successfully, log to ai_requests
                latency = int((datetime.now() - start_time).total_seconds() * 1000)
                cost_usd_micro = int((input_tokens * 3.0) + (output_tokens * 15.0))
                
                ai_req = AIRequest(
                    id=f"ai_{ulid.new()}",
                    company_id=company_id,
                    user_id=user_id,
                    job_id=req.job_id,
                    request_type="senior_tech_chat",
                    model="claude-3-5-sonnet-20241022",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd_micro=cost_usd_micro,
                    feature_tag="senior_tech_chat",
                    cache_hit=False,
                    latency_ms=latency,
                    status="success"
                )
                db.add(ai_req)
                db.commit()

            else:
                # Mock Streaming Response for local dev
                logger.info("Local environment missing ANTHROPIC_API_KEY. Simulating mock chat streaming.")
                start_time = datetime.now()
                
                equipment_desc = f"{equipment.make} {equipment.model}" if equipment else "unknown equipment"
                mock_text = (
                    f"Hey there, senior tech here! I see you're working on that {equipment_desc} with trade {trade_name}. "
                    f"Looking at your readings, we have: {readings_str}. "
                    "Typically, if you see low suction pressure, check for a restricted filter, dirty evaporator coil, or a low charge. "
                    "Make sure your line voltage is stable and check the dual run capacitor for bulging. "
                    "What specific issues are you running into right now?"
                )
                
                # Yield word by word
                for word in mock_text.split(" "):
                    yield f"data: {json.dumps({'text': word + ' '})}\n\n"
                    await asyncio.sleep(0.04)
                    
                # Log success to db
                latency = int((datetime.now() - start_time).total_seconds() * 1000)
                input_tokens = 500
                output_tokens = len(mock_text) // 4
                cost_usd_micro = int((input_tokens * 3.0) + (output_tokens * 15.0))
                
                ai_req = AIRequest(
                    id=f"ai_{ulid.new()}",
                    company_id=company_id,
                    user_id=user_id,
                    job_id=req.job_id,
                    request_type="senior_tech_chat",
                    model="claude-3-5-sonnet",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd_micro=cost_usd_micro,
                    feature_tag="senior_tech_chat",
                    cache_hit=False,
                    latency_ms=latency,
                    status="success"
                )
                db.add(ai_req)
                db.commit()

        except Exception as run_err:
            logger.error(f"Error executing AI chat streaming: {run_err}")
            yield f"data: {json.dumps({'error': str(run_err)})}\n\n"
            
            # Log failed AIRequest
            try:
                ai_req_fail = AIRequest(
                    id=f"ai_{ulid.new()}",
                    company_id=company_id,
                    user_id=user_id,
                    job_id=req.job_id,
                    request_type="senior_tech_chat",
                    model="claude-3-5-sonnet",
                    input_tokens=0,
                    output_tokens=0,
                    cost_usd_micro=0,
                    feature_tag="senior_tech_chat",
                    cache_hit=False,
                    latency_ms=0,
                    status="error",
                    error_detail=str(run_err)
                )
                db.add(ai_req_fail)
                db.commit()
            except Exception as db_err:
                logger.error(f"Failed to log failed AIRequest: {db_err}")
        finally:
            db.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

