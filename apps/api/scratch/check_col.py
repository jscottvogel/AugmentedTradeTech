from apps.api.app.core.database import SessionLocal
from apps.api.app.models.company import Company
from apps.api.app.models.customer import Customer
from apps.api.app.models.user import User
from apps.api.app.models.job import Job, JobStatusHistory
import ulid

db = SessionLocal()
try:
    hist = JobStatusHistory(
        id=f"jsh_{ulid.new()}",
        company_id="comp_test",
        job_id="job_test_flow",
        from_status="completed",
        to_status="paid",
        changed_by=None,
        note="Test null"
    )
    db.add(hist)
    db.commit()
    print("SUCCESS INSERT NULL")
except Exception as e:
    print("FAILED:", e)
finally:
    db.close()
