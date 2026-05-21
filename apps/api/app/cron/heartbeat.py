import sys
import os
import ulid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select

# Add parent directory to sys.path to allow absolute imports in Lambda if needed
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")))

from apps.api.app.core.database import SessionLocal
from apps.api.app.models.user import TechProfile, AvailabilityStatusLog

def handler(event, context):
    """
    Cron job triggered every 5 minutes by AWS EventBridge.
    Sets technicians to 'offline' if they haven't sent a heartbeat for 10+ minutes.
    """
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        timeout_threshold = now - timedelta(minutes=10)

        # Select tech profiles that are NOT offline and whose last heartbeat is too old
        stale_techs = db.scalars(
            select(TechProfile)
            .where(TechProfile.availability_status != "offline")
            .where(
                (TechProfile.last_heartbeat_at < timeout_threshold) |
                (TechProfile.last_heartbeat_at.is_(None))
            )
        ).all()

        updated_count = 0
        for tech in stale_techs:
            tech.availability_status = "offline"
            tech.status_changed_at = now

            # Close existing active log
            active_log = db.scalar(
                select(AvailabilityStatusLog)
                .where(AvailabilityStatusLog.user_id == tech.user_id)
                .where(AvailabilityStatusLog.ended_at.is_(None))
            )
            if active_log:
                active_log.ended_at = now

            # Create new offline log
            offline_log = AvailabilityStatusLog(
                id=f"asl_{ulid.new()}",
                user_id=tech.user_id,
                company_id=tech.company_id,
                status="offline",
                started_at=now
            )
            db.add(offline_log)
            updated_count += 1

        if updated_count > 0:
            db.commit()
            print(f"Cron heartbeat worker marked {updated_count} tech(s) as offline.")
        else:
            print("Cron heartbeat worker: No stale technicians found.")

        return {
            "status": "success",
            "marked_offline_count": updated_count
        }

    except Exception as e:
        db.rollback()
        print(f"Error in heartbeat cron handler: {e}")
        raise e
    finally:
        db.close()
