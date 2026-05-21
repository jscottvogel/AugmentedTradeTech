import sys
import os
import json
import logging
import traceback
from datetime import datetime, timezone
from sqlalchemy import select

# Add parent directory to sys.path to allow absolute imports in Lambda if needed
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")))

import boto3
from apps.api.app.core.database import SessionLocal, set_rls_context
from apps.api.app.models.sync import SyncQueue
from apps.api.app.models.user import User

logger = logging.getLogger("sync_queue_worker")

def send_admin_alert(company_id, sync_queue_id, error_msg, admin_emails):
    if os.getenv("STAGE", "dev") == "dev" and not os.getenv("AWS_ACCESS_KEY_ID"):
        print(f"\n[LOCAL DEV] Simulated Sync Worker Failure Email to {admin_emails} for sync queue ID {sync_queue_id}: {error_msg}\n")
        return
        
    try:
        ses = boto3.client("ses", region_name=os.getenv("AWS_REGION", "us-east-1"))
        sender = os.getenv("SES_SENDER_EMAIL", "noreply@augmentedtradetech.com")
        subject = f"[Sync Processing Failure] Queue Item {sync_queue_id}"
        body_text = f"Background processing failed for sync queue item {sync_queue_id}.\n\nError:\n{error_msg}\n\nThis item has been moved to the Dead Letter Queue (DLQ)."
        body_html = f"""<html>
        <body>
          <h2>Sync Processing Failure</h2>
          <p>Background processing failed for sync queue item <strong>{sync_queue_id}</strong>.</p>
          <p><strong>Error Details:</strong></p>
          <pre style="background-color: #f8f9fa; padding: 10px; border: 1px solid #dee2e6; border-radius: 4px;">{error_msg}</pre>
          <p>This item has been routed to the Dead Letter Queue (DLQ) after maximum retry attempts.</p>
        </body>
        </html>"""
        
        ses.send_email(
            Source=sender,
            Destination={"ToAddresses": admin_emails},
            Message={
                "Subject": {"Data": subject},
                "Body": {
                    "Text": {"Data": body_text},
                    "Html": {"Data": body_html}
                }
            }
        )
        logger.info(f"SES alert email sent to {admin_emails}")
    except Exception as e:
        logger.error(f"Failed to send alert email via SES: {e}")

def handler(event, context):
    logger.info(f"Received SQS event: {json.dumps(event)}")
    
    sqs = boto3.client("sqs", region_name=os.getenv("AWS_REGION", "us-east-1"))
    db = SessionLocal()
    
    batch_item_failures = []
    
    # Get Queue URLs from SST Resources
    queue_url = None
    dlq_url = None
    try:
        from sst import Resource
        if hasattr(Resource, "SyncQueue"):
            queue_url = Resource.SyncQueue.url
        if hasattr(Resource, "SyncQueueDLQ"):
            dlq_url = Resource.SyncQueueDLQ.url
    except Exception as sst_err:
        logger.warning(f"Could not load SST Resources: {sst_err}")

    # Fallback/mock urls for local dev if sst resources are not fully loaded
    if not queue_url:
        queue_url = os.getenv("SYNC_QUEUE_URL", "mock-sync-queue-url")
    if not dlq_url:
        dlq_url = os.getenv("SYNC_QUEUE_DLQ_URL", "mock-sync-queue-dlq-url")

    for record in event.get("Records", []):
        message_id = record.get("messageId")
        receipt_handle = record.get("receiptHandle")
        body_str = record.get("body", "{}")
        
        try:
            body = json.loads(body_str)
        except Exception as e:
            logger.error(f"Failed to parse record body: {e}")
            continue

        company_id = body.get("company_id")
        sync_queue_id = body.get("sync_queue_id")
        
        if not company_id:
            logger.error(f"Missing company_id in message body: {body}")
            continue

        try:
            # Set database RLS context
            set_rls_context(db, company_id, None, "system")
            
            # Retrieve DB entry
            sync_record = None
            if sync_queue_id:
                sync_record = db.scalar(
                    select(SyncQueue)
                    .where(SyncQueue.id == sync_queue_id)
                    .where(SyncQueue.company_id == company_id)
                )

            # Process the sync message
            # If payload has simulate_worker_error=True, trigger exception
            if body.get("payload", {}).get("simulate_worker_error") is True:
                raise RuntimeError("Simulated worker error for testing retry/DLQ flow")
                
            logger.info(f"Successfully processed sync queue item {sync_queue_id}")
            
            # If record is found, update its background worker state
            if sync_record and sync_record.status == "processing":
                sync_record.status = "applied"
                sync_record.applied_at = datetime.now(timezone.utc)
                db.add(sync_record)
                db.commit()

        except Exception as err:
            db.rollback()
            error_trace = traceback.format_exc()
            error_msg = f"Worker error: {str(err)}\n\nTraceback:\n{error_trace}"
            logger.error(f"Error processing record {message_id}: {error_msg}")
            
            # Read ApproximateReceiveCount from SQS attributes
            approx_receive_count = int(record.get("attributes", {}).get("ApproximateReceiveCount", 1))
            logger.info(f"Message receive count: {approx_receive_count}")
            
            is_local = os.getenv("STAGE", "dev") == "dev" and not os.getenv("AWS_ACCESS_KEY_ID")

            if approx_receive_count <= 3:
                # Calculate exponential backoff
                visibility_timeout = (2 ** approx_receive_count) * 5
                logger.info(f"Setting message visibility to {visibility_timeout} seconds (backoff)")
                
                if not is_local:
                    try:
                        sqs.change_message_visibility(
                            QueueUrl=queue_url,
                            ReceiptHandle=receipt_handle,
                            VisibilityTimeout=visibility_timeout
                        )
                    except Exception as sqs_err:
                        logger.error(f"Failed to change message visibility: {sqs_err}")
                
                batch_item_failures.append({"itemIdentifier": message_id})
            else:
                # Route to DLQ programmatically
                logger.warning(f"Exceeded 3 attempts for message {message_id}. Routing to DLQ.")
                
                if not is_local:
                    try:
                        sqs.send_message(
                            QueueUrl=dlq_url,
                            MessageBody=body_str
                        )
                        sqs.delete_message(
                            QueueUrl=queue_url,
                            ReceiptHandle=receipt_handle
                        )
                    except Exception as sqs_err:
                        logger.error(f"Failed to route message to DLQ: {sqs_err}")
                else:
                    print(f"\n[LOCAL DEV] Simulated Routing message to DLQ URL: {dlq_url}\n")
                
                try:
                    set_rls_context(db, company_id, None, "system")
                    admins = db.scalars(
                        select(User)
                        .where(User.company_id == company_id)
                        .where(User.role == "company_admin")
                        .where(User.is_active == True)
                    ).all()
                    admin_emails = [admin.email for admin in admins] if admins else ["admin@augmentedtradetech.com"]
                except Exception as db_err:
                    logger.error(f"Failed to fetch admin emails from DB: {db_err}")
                    admin_emails = ["admin@augmentedtradetech.com"]

                send_admin_alert(company_id, sync_queue_id or message_id, error_msg, admin_emails)

    db.close()
    return {"batchItemFailures": batch_item_failures}
