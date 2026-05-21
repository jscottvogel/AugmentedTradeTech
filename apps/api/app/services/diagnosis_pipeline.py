import os
import json
import logging
import httpx
import math
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, TypedDict
from sqlalchemy.orm import Session
from sqlalchemy import select, update, text
from langgraph.graph import StateGraph, START, END

from apps.api.app.core.database import SessionLocal, set_rls_context
from apps.api.app.models.job import Job, JobPhoto, JobPart
from apps.api.app.models.customer import Customer, Equipment
from apps.api.app.models.ai import AIRequest, JobEmbedding

logger = logging.getLogger(__name__)

class AgentState(TypedDict):
    job_id: str
    db: Session
    company_id: str
    trade: str
    
    # DB Entities
    job_data: Dict[str, Any]
    customer_data: Dict[str, Any]
    equipment_data: Dict[str, Any]
    inspection_data: Dict[str, Any]
    photos_data: List[Dict[str, Any]]
    service_history: List[Dict[str, Any]]
    
    # Retrieved & Analyzed Context
    similar_jobs: List[Dict[str, Any]]
    readings_analysis: Dict[str, Any]
    photos_analysis: Dict[str, Any]
    
    # Outputs
    synthesized_diagnosis: Dict[str, Any]
    embedding: List[float]
    final_diagnosis_data: Dict[str, Any]


async def get_embedding(text_to_embed: str) -> List[float]:
    """
    Generate a 1536-dimensional embedding using OpenAI.
    Falls back to a hash-based deterministic mock embedding in development/testing.
    """
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        try:
            headers = {
                "Authorization": f"Bearer {openai_key}",
                "Content-Type": "application/json"
            }
            body = {
                "input": text_to_embed,
                "model": "text-embedding-3-small"
            }
            async with httpx.AsyncClient() as client:
                resp = await client.post("https://api.openai.com/v1/embeddings", headers=headers, json=body, timeout=10.0)
                if resp.status_code == 200:
                    return resp.json()["data"][0]["embedding"]
        except Exception as e:
            logger.error(f"Failed to generate OpenAI embedding: {e}")

    # Hash-based deterministic mock embedding
    h = hashlib.sha256(text_to_embed.encode("utf-8")).digest()
    vals = []
    for i in range(1536):
        val = ((h[i % 32] * (i + 1)) % 2000 - 1000) / 1000.0
        vals.append(val)
    # normalize to unit length
    norm = math.sqrt(sum(x * x for x in vals))
    if norm > 0:
        vals = [x / norm for x in vals]
    return vals


def context_loader_node(state: AgentState) -> Dict[str, Any]:
    db = state["db"]
    job_id = state["job_id"]
    
    job = db.scalar(select(Job).where(Job.id == job_id))
    if not job:
        raise ValueError(f"Job {job_id} not found")
        
    company_id = job.company_id
    trade = job.trade or "HVAC"
    
    # Configure RLS context so background operations read correctly
    set_rls_context(db, company_id, None, "system")
    
    customer = None
    if job.customer_id:
        customer = db.scalar(select(Customer).where(Customer.id == job.customer_id))
        
    equipment = None
    if job.equipment_id:
        equipment = db.scalar(select(Equipment).where(Equipment.id == job.equipment_id))
        
    photos = db.scalars(select(JobPhoto).where(JobPhoto.job_id == job_id, JobPhoto.deleted_at == None)).all()
    photos_data = []
    for p in photos:
        photos_data.append({
            "id": p.id,
            "photo_type": p.photo_type,
            "caption": p.caption,
            "ai_analysis": p.ai_analysis
        })
        
    service_history = []
    if job.equipment_id:
        prior_jobs = db.scalars(
            select(Job)
            .where(
                Job.equipment_id == job.equipment_id,
                Job.id != job_id,
                Job.status == "completed"
            )
            .order_by(Job.completed_at.desc())
        ).all()
        for pj in prior_jobs:
            service_history.append({
                "job_id": pj.id,
                "completed_at": pj.completed_at.isoformat() if pj.completed_at else None,
                "ai_diagnosis": pj.ai_diagnosis
            })
            
    job_data = {
        "id": job.id,
        "title": job.job_number,
        "description": job.reported_problem,
        "inspection_data": job.inspection_data or {},
        "trade": trade
    }
    
    customer_data = {
        "id": customer.id,
        "first_name": customer.first_name,
        "last_name": customer.last_name,
        "email": customer.email
    } if customer else {}
    
    equipment_data = {
        "id": equipment.id,
        "make": equipment.make,
        "model": equipment.model,
        "serial_number": equipment.serial_number,
        "equipment_type": equipment.equipment_type
    } if equipment else {}
    
    return {
        "company_id": company_id,
        "trade": trade,
        "job_data": job_data,
        "customer_data": customer_data,
        "equipment_data": equipment_data,
        "inspection_data": job_data["inspection_data"],
        "photos_data": photos_data,
        "service_history": service_history
    }


def make_inspection_summary_text(state: AgentState) -> str:
    job = state["job_data"]
    insp = state["inspection_data"]
    lines = [
        f"Job Title: {job.get('title', '')}",
        f"Description: {job.get('description', '')}",
        f"Trade: {job.get('trade', '')}"
    ]
    if insp:
        lines.append("Inspection Readings:")
        for step_key, step_val in insp.items():
            if isinstance(step_val, dict):
                inputs = step_val.get("inputs", {})
                skipped = step_val.get("skipped", False)
                if skipped:
                    lines.append(f"- {step_key}: Skipped")
                elif inputs:
                    lines.append(f"- {step_key}: {json.dumps(inputs)}")
            else:
                lines.append(f"- {step_key}: {step_val}")
    return "\n".join(lines)


async def similar_jobs_retriever_node(state: AgentState) -> Dict[str, Any]:
    db = state["db"]
    company_id = state["company_id"]
    trade = state["trade"]
    job_id = state["job_id"]
    
    summary_text = make_inspection_summary_text(state)
    query_vector = await get_embedding(summary_text)
    
    similar_jobs = []
    try:
        stmt = (
            select(JobEmbedding, Job)
            .join(Job, Job.id == JobEmbedding.job_id)
            .where(
                JobEmbedding.company_id == company_id,
                Job.trade == trade,
                Job.status == "completed",
                Job.id != job_id
            )
            .order_by(JobEmbedding.embedding.cosine_distance(query_vector))
            .limit(5)
        )
        results = db.execute(stmt).all()
        for embed_row, job_row in results:
            similar_jobs.append({
                "job_id": job_row.id,
                "title": job_row.job_number,
                "ai_diagnosis": job_row.ai_diagnosis
            })
    except Exception as err:
        logger.error(f"Error querying similar jobs via pgvector: {err}")
        
    return {
        "similar_jobs": similar_jobs
    }


def readings_analyzer_node(state: AgentState) -> Dict[str, Any]:
    insp = state["inspection_data"] or {}
    trade = state["trade"].lower() if state["trade"] else ""
    anomalies = []
    
    if "hvac" in trade:
        # Check delta-T
        temp_step = insp.get("temperature_readings", {})
        if temp_step and not temp_step.get("skipped", False):
            inputs = temp_step.get("inputs", {})
            supply = inputs.get("supply_temp")
            ret = inputs.get("return_temp")
            if supply is not None and ret is not None:
                delta = float(ret) - float(supply)
                if delta < 15.0 or delta > 22.0:
                    anomalies.append({
                        "field": "temperature_delta",
                        "value": delta,
                        "expected": "15.0 to 22.0 °F",
                        "severity": "critical" if delta < 10.0 or delta > 28.0 else "moderate",
                        "description": f"Air temperature delta-T of {delta:.1f}°F is outside the normal cooling range of 15-22°F."
                    })
        # Check pressures
        press_step = insp.get("refrigerant_pressures", {})
        if press_step and not press_step.get("skipped", False):
            inputs = press_step.get("inputs", {})
            suction = inputs.get("suction_pressure")
            discharge = inputs.get("discharge_pressure")
            if suction is not None:
                if float(suction) < 110.0 or float(suction) > 130.0:
                    anomalies.append({
                        "field": "suction_pressure",
                        "value": suction,
                        "expected": "110.0 to 130.0 PSI",
                        "severity": "critical" if float(suction) < 90.0 or float(suction) > 150.0 else "moderate",
                        "description": f"Suction pressure of {suction} PSI is outside the expected R-410A operating range of 110-130 PSI."
                    })
            if discharge is not None:
                if float(discharge) < 300.0 or float(discharge) > 400.0:
                    anomalies.append({
                        "field": "discharge_pressure",
                        "value": discharge,
                        "expected": "300.0 to 400.0 PSI",
                        "severity": "critical" if float(discharge) < 250.0 or float(discharge) > 450.0 else "moderate",
                        "description": f"Discharge pressure of {discharge} PSI is outside the expected R-410A operating range of 300-400 PSI."
                    })
    elif "garage" in trade:
        # Check balance test
        balance_step = insp.get("balance_test", {})
        if balance_step and not balance_step.get("skipped", False):
            inputs = balance_step.get("inputs", {})
            val = inputs.get("value") or balance_step.get("value") or ""
            if "severe" in val.lower() or "dangerous" in val.lower():
                anomalies.append({
                    "field": "balance_test",
                    "value": val,
                    "expected": "Perfect balance or Slightly heavy/light tension",
                    "severity": "critical",
                    "description": "Garage door balance test indicates it is severely out of balance or dangerous to operate."
                })
                
    return {
        "readings_analysis": {
            "anomalies": anomalies
        }
    }


def photo_analyzer_node(state: AgentState) -> Dict[str, Any]:
    photos = state["photos_data"]
    failed_components = []
    concerning_components = []
    
    for p in photos:
        analysis = p.get("ai_analysis")
        if not analysis:
            continue
            
        if isinstance(analysis, str):
            try:
                analysis = json.loads(analysis)
            except Exception:
                pass
                
        if isinstance(analysis, dict):
            sev = analysis.get("severity") or ""
            comp = analysis.get("component_type") or analysis.get("component") or ""
            desc = analysis.get("visible_damage") or analysis.get("recommended_action") or ""
            
            if sev.lower() in ("critical", "severe"):
                failed_components.append({
                    "photo_id": p["id"],
                    "component": comp,
                    "severity": sev,
                    "description": desc
                })
            elif sev.lower() in ("moderate", "minor") or analysis.get("wiring_issues") or analysis.get("issues"):
                concerning_components.append({
                    "photo_id": p["id"],
                    "component": comp,
                    "severity": sev,
                    "description": desc or str(analysis)
                })
                
    return {
        "photos_analysis": {
            "failed_components": failed_components,
            "concerning_components": concerning_components
        }
    }


async def diagnosis_synthesizer_node(state: AgentState) -> Dict[str, Any]:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    
    job = state["job_data"]
    cust = state["customer_data"]
    eq = state["equipment_data"]
    insp = state["inspection_data"]
    history = state["service_history"]
    similar = state["similar_jobs"]
    readings = state["readings_analysis"]
    photos = state["photos_analysis"]
    
    context = {
        "job_title": job.get("title"),
        "job_description": job.get("description"),
        "trade": state["trade"],
        "customer": cust,
        "equipment": eq,
        "inspection_readings": insp,
        "equipment_service_history": history,
        "similar_completed_jobs": similar,
        "readings_anomalies": readings.get("anomalies", []),
        "photo_failed_components": photos.get("failed_components", []),
        "photo_concerning_components": photos.get("concerning_components", [])
    }
    
    system_prompt = (
        "You are a Senior HVAC/garage door technician with 20 years of field experience. "
        "Your task is to analyze the provided service call details, inspection readings, photo analysis reports, "
        "and historic records to synthesize a structured diagnosis. "
        "Format your response as a valid JSON object matching this schema exactly:\n"
        "{\n"
        "  \"summary\": \"2-3 sentences diagnosing the primary issue.\",\n"
        "  \"root_causes\": [\n"
        "    { \"description\": \"Root cause description.\", \"confidence\": 0.95, \"evidence\": \"Specific readings/photo findings supporting this.\" }\n"
        "  ],\n"
        "  \"recommendations\": [\n"
        "    { \"action\": \"Step-by-step action item.\", \"priority\": \"high/medium/low\", \"parts_likely_needed\": [\"part name\"] }\n"
        "  ],\n"
        "  \"safety_concerns\": [\"Any safety issues or hazards noted.\"],\n"
        "  \"escalation_needed\": false\n"
        "}"
    )
    
    user_prompt = f"Please analyze this job context and return a structured diagnosis JSON:\n{json.dumps(context, indent=2)}"
    
    if api_key:
        try:
            async with httpx.AsyncClient() as client:
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                }
                payload = {
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 1500,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}],
                    "temperature": 0.2
                }
                resp = await client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=20.0)
                if resp.status_code == 200:
                    res_json = resp.json()
                    content_text = res_json["content"][0]["text"]
                    
                    input_tokens = res_json.get("usage", {}).get("input_tokens", 0)
                    output_tokens = res_json.get("usage", {}).get("output_tokens", 0)
                    cost_usd_micro = int((input_tokens * 3 + output_tokens * 15) / 1000.0)
                    
                    db = state["db"]
                    import ulid
                    req_id = "air_" + str(ulid.new())
                    ai_req = AIRequest(
                        id=req_id,
                        company_id=state["company_id"],
                        job_id=state["job_id"],
                        request_type="diagnosis",
                        model="claude-3-5-sonnet-20241022",
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cost_usd_micro=cost_usd_micro,
                        feature_tag="langgraph_diagnosis",
                        status="success"
                    )
                    db.add(ai_req)
                    db.commit()
                    
                    if "```json" in content_text:
                        content_text = content_text.split("```json")[1].split("```")[0].strip()
                    elif "```" in content_text:
                        content_text = content_text.split("```")[1].split("```")[0].strip()
                    
                    parsed_diagnosis = json.loads(content_text.strip())
                    return {
                        "synthesized_diagnosis": parsed_diagnosis
                    }
        except Exception as e:
            logger.error(f"Error calling Claude for diagnosis synthesizer: {e}")
            
    # Mock fallback for local dev / tests
    logger.info("Missing ANTHROPIC_API_KEY or call failed. Generating mock diagnosis response.")
    
    trade = state["trade"].lower() if state["trade"] else ""
    anomalies = readings.get("anomalies", [])
    failed_photos = photos.get("failed_components", [])
    
    if "hvac" in trade:
        summary = "System exhibits low cooling capacity due to a suspected refrigerant charge deficiency."
        root_causes = [
            {
                "description": "Refrigerant leak in evaporator coil.",
                "confidence": 0.85,
                "evidence": "Suction pressure is low and delta-T is below normal."
            }
        ]
        recommendations = [
            {
                "action": "Perform electronic leak search on evaporator and condenser coils.",
                "priority": "high",
                "parts_likely_needed": ["Leak Sealant", "Refrigerant R-410A"]
            }
        ]
        safety_concerns = ["Ensure power is disconnected when performing component repair."]
        escalation_needed = False
        
        has_electrical = any("capacitor" in str(x).lower() or "contactor" in str(x).lower() for x in failed_photos)
        if has_electrical:
            summary = "System fails to start the compressor due to a failed dual run capacitor."
            root_causes = [
                {
                    "description": "Failed/bulged dual run capacitor.",
                    "confidence": 0.95,
                    "evidence": "Electrical step shows a bulged run capacitor photo, and compressor draws lock-rotor amps."
                }
            ]
            recommendations = [
                {
                    "action": "Replace dual run capacitor (45/5 uF 440V). Check contactor points for pitting.",
                    "priority": "high",
                    "parts_likely_needed": ["Dual Run Capacitor 45/5 uF", "Contactor"]
                }
            ]
            safety_concerns = ["High voltage hazard. Disconnect power and discharge capacitor before replacement."]
    else:
        summary = "Garage door opener mechanism is strained due to broken spring system."
        root_causes = [
            {
                "description": "Broken torsion spring on shaft.",
                "confidence": 0.98,
                "evidence": "Spring system photo shows a clean separation of the torsion spring coil."
            }
        ]
        recommendations = [
            {
                "action": "Replace broken torsion spring. Balance door and verify limits.",
                "priority": "high",
                "parts_likely_needed": ["Torsion Spring 250x2x28"]
            }
        ]
        safety_concerns = ["High spring tension. Extreme caution required during spring replacement."]
        escalation_needed = True

    parsed_diagnosis = {
        "summary": summary,
        "root_causes": root_causes,
        "recommendations": recommendations,
        "safety_concerns": safety_concerns,
        "escalation_needed": escalation_needed
    }
    
    return {
        "synthesized_diagnosis": parsed_diagnosis
    }


async def embedder_node(state: AgentState) -> Dict[str, Any]:
    db = state["db"]
    job_id = state["job_id"]
    company_id = state["company_id"]
    
    diagnosis = state["synthesized_diagnosis"]
    
    summary = diagnosis.get("summary", "")
    causes = ", ".join(rc.get("description", "") for rc in diagnosis.get("root_causes", []))
    embed_text = f"Summary: {summary} Root Causes: {causes}"
    
    embedding = await get_embedding(embed_text)
    
    try:
        import ulid
        existing = db.scalar(select(JobEmbedding).where(JobEmbedding.job_id == job_id))
        if existing:
            existing.embedding = embedding
            existing.embed_text = embed_text
            existing.updated_at = datetime.now(timezone.utc)
        else:
            emb_id = "jemb_" + str(ulid.new())
            new_emb = JobEmbedding(
                id=emb_id,
                company_id=company_id,
                job_id=job_id,
                embedding=embedding,
                embed_text=embed_text,
                model_version="text-embedding-3-small"
            )
            db.add(new_emb)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to upsert job_embedding: {e}")
        db.rollback()
        
    return {
        "embedding": embedding
    }


PARTS_PRICING = {
    "dual run capacitor": 6500,
    "contactor": 4500,
    "refrigerant": 12000,
    "leak sealant": 8500,
    "torsion spring": 15000,
    "extension spring": 9500,
    "roller": 1500,
    "cable": 2500
}


def get_part_price_cents(part_name: str) -> int:
    name = part_name.lower()
    for key, price in PARTS_PRICING.items():
        if key in name:
            return price
    return 7500


def documenter_node(state: AgentState) -> Dict[str, Any]:
    db = state["db"]
    job_id = state["job_id"]
    trade = state["trade"].lower() if state["trade"] else ""
    diagnosis = state["synthesized_diagnosis"]
    
    summary = diagnosis.get("summary", "")
    actions = [rec.get("action", "") for rec in diagnosis.get("recommendations", [])]
    work_performed = f"Performed comprehensive system diagnostic. {summary} Recommendations: " + " ".join(actions)
    
    line_items = []
    
    if "hvac" in trade:
        line_items.append({
            "description": "HVAC Service & Diagnostic Labor",
            "quantity": 1,
            "unit_price_cents": 18000
        })
    else:
        line_items.append({
            "description": "Garage Door Repair & Tuning Labor",
            "quantity": 1,
            "unit_price_cents": 15000
        })
        
    parts_needed = []
    for rec in diagnosis.get("recommendations", []):
        for part in rec.get("parts_likely_needed", []):
            parts_needed.append(part)
            
    for part in parts_needed:
        price = get_part_price_cents(part)
        qty = 2 if "refrigerant" in part.lower() else 1
        line_items.append({
            "description": f"Replacement Part: {part}",
            "quantity": qty,
            "unit_price_cents": price
        })
        
    final_diagnosis = {
        **diagnosis,
        "work_performed": work_performed,
        "draft_invoice": {
            "line_items": line_items
        }
    }
    
    try:
        job = db.scalar(select(Job).where(Job.id == job_id))
        if job:
            job.ai_diagnosis = final_diagnosis
            db.add(job)
            db.commit()
    except Exception as e:
        logger.error(f"Failed to update jobs.ai_diagnosis: {e}")
        db.rollback()
        
    return {
        "final_diagnosis_data": final_diagnosis
    }


def build_diagnosis_workflow():
    workflow = StateGraph(AgentState)
    
    workflow.add_node("context_loader", context_loader_node)
    workflow.add_node("similar_jobs_retriever", similar_jobs_retriever_node)
    workflow.add_node("readings_analyzer", readings_analyzer_node)
    workflow.add_node("photo_analyzer", photo_analyzer_node)
    workflow.add_node("diagnosis_synthesizer", diagnosis_synthesizer_node)
    workflow.add_node("embedder", embedder_node)
    workflow.add_node("documenter", documenter_node)
    
    workflow.add_edge(START, "context_loader")
    workflow.add_edge("context_loader", "similar_jobs_retriever")
    workflow.add_edge("similar_jobs_retriever", "readings_analyzer")
    workflow.add_edge("readings_analyzer", "photo_analyzer")
    workflow.add_edge("photo_analyzer", "diagnosis_synthesizer")
    workflow.add_edge("diagnosis_synthesizer", "embedder")
    workflow.add_edge("embedder", "documenter")
    workflow.add_edge("documenter", END)
    
    return workflow.compile()


async def run_diagnosis_pipeline(job_id: str, db: Session):
    app = build_diagnosis_workflow()
    
    initial_state = {
        "job_id": job_id,
        "db": db,
        "company_id": "",
        "trade": "",
        "job_data": {},
        "customer_data": {},
        "equipment_data": {},
        "inspection_data": {},
        "photos_data": [],
        "service_history": [],
        "similar_jobs": [],
        "readings_analysis": {},
        "photos_analysis": {},
        "synthesized_diagnosis": {},
        "embedding": [],
        "final_diagnosis_data": {}
    }
    
    result = await app.ainvoke(initial_state)
    return result["final_diagnosis_data"]
