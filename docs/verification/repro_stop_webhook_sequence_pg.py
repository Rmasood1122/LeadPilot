"""NEW-01: reproduce the webhook STOP failure exactly as the HTTP path does it.

The webhook (app/api/webhooks_whatsapp.py:368-374) calls BOTH
  optin_svc.revoke_opt_in(...)      # post-Feature-9: suppresses phone AND email
  engine.unsubscribe_lead(...)      # legacy: suppresses email AND phone again
Feature 9 (commit 4612e30) made revoke_opt_in call consent.suppress_everywhere,
which already covers the email side, so the two calls now overlap and the
flush emits a duplicate phone -> UniqueViolation on ix_suppression_list_phone.

Verification artifact only; outside tests/, never added to the suite.
"""
import os, uuid, sys
os.environ["DATABASE_URL"]="postgresql+psycopg2://lpaudit:lpauditpw@127.0.0.1:5432/lprepro2"
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.models import (Base, User, Product, Strategy, Lead, LeadStatus,
                           StrategyStatus, OptInSource, SuppressionEntry)
from app.services import whatsapp_optin as optin_svc
from app.services import sequence_engine as engine

e=create_engine(os.environ["DATABASE_URL"]); Base.metadata.create_all(e)
s=sessionmaker(bind=e)()
u=User(id=uuid.uuid4(), email="t@example.com", password_hash="x"); s.add(u); s.flush()
p=Product(id=uuid.uuid4(), user_id=u.id, name="P", description="d", type="skill"); s.add(p); s.flush()
st=Strategy(id=uuid.uuid4(), product_id=p.id, flow_type="with_clients",
            status=StrategyStatus.EXECUTING, verified_passes_json={}, campaign_state="active")
s.add(st); s.commit()
l=Lead(id=uuid.uuid4(), strategy_id=st.id, source="manual", status=LeadStatus.CONTACTED,
       full_name="L", email="lead@example.com", phone="+15550009999")
s.add(l); s.commit()
optin_svc.record_opt_in(s,l,source=OptInSource.MANUAL_IMPORT,evidence="verification"); s.commit()

print("Replaying the webhook's exact two-call STOP sequence:")
try:
    optin_svc.revoke_opt_in(s,l,source=OptInSource.INBOUND_MESSAGE,evidence="inbound STOP")
    print("  1) revoke_opt_in      OK   suppression_rows=", s.query(SuppressionEntry).count())
    engine.unsubscribe_lead(s,l,source="whatsapp_stop",channel="whatsapp")
    print("  2) unsubscribe_lead   OK   suppression_rows=", s.query(SuppressionEntry).count())
    print("RESULT: no error -> NEW-01 would NOT reproduce this way")
except Exception as ex:
    s.rollback()
    print(f"  FAILED at step 2: {type(ex).__name__}")
    print("  ", str(ex).splitlines()[0][:160])
    print("RESULT: NEW-01 REPRODUCED -- STOP cannot complete; opt-out is lost")
    print("  suppression_rows after rollback =", s.query(SuppressionEntry).count())
