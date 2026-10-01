"""Reproduce the WhatsApp-STOP duplicate suppression insert (NEW-01).

Verification artifact only. Lives outside tests/ and is never added to the
offline suite. Shows that revoke_opt_in writes the phone suppression twice in
one transaction (whatsapp_optin.py:207 and consent.suppress_everywhere ->
consent.py:254), and that the failure only appears when the lead has BOTH an
email and a phone -- which is why the 45 green STOP/consent tests miss it.
"""
import os, uuid
os.environ["DATABASE_URL"] = "sqlite://"
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db.models import (Base, User, Product, Strategy, Lead, LeadStatus,
                           StrategyStatus, OptInSource, SuppressionEntry)
from app.services import whatsapp_optin

e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                  poolclass=StaticPool)
Base.metadata.create_all(e)
s = sessionmaker(bind=e)()

u = User(id=uuid.uuid4(), email="t@example.com", password_hash="x")
s.add(u); s.flush()
p = Product(id=uuid.uuid4(), user_id=u.id, name="P", description="d", type="skill")
s.add(p); s.flush()
st = Strategy(id=uuid.uuid4(), product_id=p.id, flow_type="with_clients",
              status=StrategyStatus.EXECUTING, verified_passes_json={},
              campaign_state="active")
s.add(st); s.flush(); s.commit()

def run(label, email, phone):
    l = Lead(id=uuid.uuid4(), strategy_id=st.id, source="manual",
             status=LeadStatus.CONTACTED, full_name="L", email=email, phone=phone)
    s.add(l); s.commit()
    whatsapp_optin.record_opt_in(s, l, source=OptInSource.MANUAL_IMPORT,
                                 evidence="verification evidence")
    s.commit()
    try:
        whatsapp_optin.revoke_opt_in(s, l, source=OptInSource.INBOUND_MESSAGE,
                                     evidence="STOP")
        n = s.query(SuppressionEntry).count()
        print(f"  [{label}] revoke OK      email={email!r} phone={phone!r} "
              f"suppression_rows={n}")
    except Exception as ex:
        s.rollback()
        print(f"  [{label}] revoke FAILED  email={email!r} phone={phone!r}")
        print(f"            {type(ex).__name__}: {str(ex).splitlines()[0][:120]}")

print("CASE 1 - lead has phone only (the shape the green tests use):")
run("phone-only", None, "+15550001111")
print("CASE 2 - lead has BOTH email and phone (the real-world shape):")
run("email+phone", "both@example.com", "+15550002222")
