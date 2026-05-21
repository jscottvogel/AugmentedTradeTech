import sys
import os
import ulid
import logging
from datetime import datetime, timezone
from sqlalchemy import select, func

# Add parent directory to sys.path to allow absolute imports in Lambda
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")))

from apps.api.app.core.database import SessionLocal
from apps.api.app.models.loyalty import LoyaltyAccount, LoyaltyLedger

logger = logging.getLogger("loyalty_expiry")
logger.setLevel(logging.INFO)

def handler(event, context):
    """
    Daily cron job running at 2am to expire loyalty points.
    Determines unused points per expired earn entry using a FIFO approach,
    and inserts an 'expire' entry to the ledger.
    """
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        expired_count = 0
        expired_points_total = 0

        # Retrieve all active loyalty accounts
        accounts = db.scalars(
            select(LoyaltyAccount).where(LoyaltyAccount.is_active == True)
        ).all()

        for account in accounts:
            # Get all non-voided ledger entries for this account
            entries = db.scalars(
                select(LoyaltyLedger)
                .where(LoyaltyLedger.account_id == account.id)
                .where(LoyaltyLedger.voided_at.is_(None))
                .order_by(LoyaltyLedger.created_at.asc(), LoyaltyLedger.id.asc())
            ).all()

            # Calculate total deductions (redeem, expire, adjustment_debit)
            total_deductions = sum(
                e.points for e in entries 
                if e.entry_type in ("redeem", "expire", "adjustment_debit")
            )

            # Process earn/adjustment_credit entries in FIFO order
            for entry in entries:
                if entry.entry_type not in ("earn", "adjustment_credit"):
                    continue

                if total_deductions >= entry.points:
                    # This entry's points were fully consumed by later redeems/debits
                    total_deductions -= entry.points
                else:
                    # This entry's points were partially consumed or completely unconsumed
                    unused_points = entry.points - total_deductions
                    total_deductions = 0

                    # Check if this entry has expired
                    if entry.entry_type == "earn" and entry.expires_at is not None and entry.expires_at < now:
                        # Check idempotency: make sure we haven't already expired this earn entry
                        idempotency_key = f"expire-{entry.id}"
                        existing_expiry = db.scalar(
                            select(LoyaltyLedger)
                            .where(LoyaltyLedger.idempotency_key == idempotency_key)
                        )
                        if not existing_expiry and unused_points > 0:
                            # Create an expire ledger entry
                            expire_entry = LoyaltyLedger(
                                id=f"tx_{ulid.new()}",
                                company_id=account.company_id,
                                account_id=account.id,
                                entry_type="expire",
                                points=unused_points,
                                description=f"Points expired from earn entry {entry.id}",
                                idempotency_key=idempotency_key,
                                created_by=None  # System process
                            )
                            db.add(expire_entry)
                            expired_count += 1
                            expired_points_total += unused_points

        if expired_count > 0:
            db.commit()
            logger.info(f"Loyalty Expiry Cron: Expired {expired_points_total} points across {expired_count} entries.")
        else:
            logger.info("Loyalty Expiry Cron: No expired points found.")

        return {
            "status": "success",
            "expired_entries_count": expired_count,
            "expired_points_total": expired_points_total
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error in loyalty points expiry cron: {e}")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    # Setup simple console logging when run directly
    logging.basicConfig(level=logging.INFO)
    handler(None, None)
