"""M4 tests — the adapter's hard compliance guard (Chunk 4, spec item 2).

Every rule is re-checked on the send path itself, and there is no
parameter combination that bypasses any of them — asserted structurally
(signature inspection) and behaviorally (hostile metadata still blocks).
"""

import inspect
from datetime import timedelta

import pytest

from app.db import models as m
from app.integrations.whatsapp import ComplianceError, WhatsAppChannel
from app.services import whatsapp_optin as optin_svc
from tests.conftest import NOW, wa_outbound


class TestGuardBlocks:
    def test_freeform_with_closed_window_raises(self, db_session, wa_lead,
                                                 wa_channel, fake_graph_http):
        assert wa_lead.whatsapp_last_inbound_at is None  # window never open
        with pytest.raises(ComplianceError, match="24-hour"):
            wa_channel.send(wa_outbound(wa_lead, kind="text"))
        assert fake_graph_http.requests == []  # blocked BEFORE any API call

    def test_freeform_inside_open_window_allowed(self, db_session, wa_lead,
                                                 wa_channel):
        # the adapter checks the window against the WALL CLOCK (send() has
        # no `now` — production behavior), so the inbound must be recent
        # relative to real time here.
        from datetime import datetime, timezone
        wa_lead.whatsapp_last_inbound_at = (
            datetime.now(timezone.utc) - timedelta(hours=1))
        db_session.commit()
        # Guard passes; the fake Graph API returns success.
        assert wa_channel.send(wa_outbound(wa_lead, kind="text")).ok

    def test_unapproved_template_raises(self, db_session, wa_lead, wa_channel,
                                        fake_graph_http):
        # 'never_submitted' does not exist in the registry at all
        with pytest.raises(ComplianceError, match="not\\s+APPROVED"):
            wa_channel.send(wa_outbound(wa_lead, template="never_submitted"))
        assert fake_graph_http.requests == []

    def test_draft_template_raises_even_if_named_manually(
            self, db_session, wa_lead, wa_channel):
        from app.services import whatsapp_templates as tmpl_svc
        tmpl_svc.create_draft(
            db_session, name="still_draft", language="en_US",
            category=m.WhatsAppTemplateCategory.MARKETING,
            body="Hi {{1}}. Reply STOP to opt out.",
            variable_descriptions={"1": "first name"},
        )
        with pytest.raises(ComplianceError):
            wa_channel.send(wa_outbound(wa_lead, template="still_draft"))

    def test_suppressed_recipient_blocked_at_send_time(
            self, db_session, wa_lead, approved_template, wa_channel,
            fake_graph_http):
        """Scheduled earlier, suppressed since — the send-time re-check wins."""
        outbound = wa_outbound(wa_lead)  # "scheduled" before suppression
        db_session.add(m.SuppressionEntry(phone=wa_lead.phone, reason="test"))
        db_session.commit()
        with pytest.raises(ComplianceError, match="suppression"):
            wa_channel.send(outbound)
        assert fake_graph_http.requests == []

    def test_no_optin_cold_template_raises(self, db_session, wa_lead_no_optin,
                                           approved_template, wa_channel,
                                           fake_graph_http):
        with pytest.raises(ComplianceError, match="opt-in"):
            wa_channel.send(wa_outbound(wa_lead_no_optin))
        assert fake_graph_http.requests == []

    def test_cache_flag_without_audit_row_still_blocked(
            self, db_session, wa_lead_no_optin, approved_template, wa_channel):
        """A manually flipped Lead.whatsapp_opted_in with no audit row is
        NOT consent — the guard requires the append-only trail to agree."""
        wa_lead_no_optin.whatsapp_opted_in = True
        db_session.commit()
        with pytest.raises(ComplianceError, match="opt-in"):
            wa_channel.send(wa_outbound(wa_lead_no_optin))

    def test_optout_after_optin_blocks(self, db_session, wa_lead,
                                       approved_template, wa_channel):
        optin_svc.revoke_opt_in(db_session, wa_lead)
        with pytest.raises(ComplianceError):
            wa_channel.send(wa_outbound(wa_lead))


class TestNoEscapeHatch:
    """The guard has no bypass — asserted on the send path itself."""

    def test_send_signature_has_no_bypass_parameter(self):
        params = set(inspect.signature(WhatsAppChannel.send).parameters)
        assert params == {"self", "message"}  # nothing else, ever

    def test_guard_signature_has_no_bypass_parameter(self):
        params = set(inspect.signature(
            WhatsAppChannel._compliance_guard).parameters)
        assert params == {"self", "message", "kind", "lead"}

    def test_hostile_metadata_flags_do_not_bypass(self, db_session,
                                                  wa_lead_no_optin,
                                                  approved_template,
                                                  wa_channel, fake_graph_http):
        """Every flag-shaped key an attacker might try is inert."""
        outbound = wa_outbound(wa_lead_no_optin)
        outbound.metadata.update(
            bypass=True, skip_checks=True, force=True, compliance=False,
            admin=True, override="yes", window_open=True, opted_in=True,
        )
        with pytest.raises(ComplianceError):
            wa_channel.send(outbound)
        assert fake_graph_http.requests == []

    def test_unknown_kind_is_refused_not_defaulted(self, db_session, wa_lead,
                                                   approved_template,
                                                   wa_channel):
        outbound = wa_outbound(wa_lead)
        outbound.metadata["kind"] = "raw"
        with pytest.raises(ComplianceError, match="unsupported"):
            wa_channel.send(outbound)

    def test_missing_lead_is_refused(self, db_session, approved_template,
                                     wa_channel):
        from app.integrations.outreach_base import OutboundMessage
        with pytest.raises(ComplianceError, match="lead"):
            wa_channel.send(OutboundMessage(
                message_id="x", lead_id=None, to_address="+15550001111",
                body="hi", metadata={"kind": "template",
                                     "template_name": "intro_v1",
                                     "language": "en_US"}))


class TestComplianceErrorIsCanonical:
    """whatsapp.py used to declare its OWN `class ComplianceError(Exception)`.

    app/main.py registers the global handler against
    app.core.exceptions.ComplianceError by CONCRETE TYPE, so the adapter's
    look-alike was never matched: a WhatsApp compliance block fell through to
    the bare Exception handler and surfaced as a 500 instead of the documented
    422. The debug router papered over it by catching the adapter class and
    re-raising the canonical one, which meant the 422 was an artefact of the
    debug router and the same block through any other caller was a 500.
    """

    def test_adapter_exports_the_canonical_class(self):
        from app.core.exceptions import ComplianceError as Canonical
        from app.integrations import whatsapp

        assert whatsapp.ComplianceError is Canonical, (
            "whatsapp.py must not declare its own ComplianceError"
        )

    def test_only_one_compliance_error_class_in_the_app(self):
        """Tripwire: this project has re-grown duplicate classes ten times."""
        import pathlib
        import re

        root = pathlib.Path(__file__).resolve().parents[1] / "app"
        declarations = [
            path.relative_to(root).as_posix()
            for path in root.rglob("*.py")
            if re.search(r"^class ComplianceError\b", path.read_text(encoding="utf-8"),
                         re.M)
        ]
        assert declarations == ["core/exceptions.py"], declarations

    def test_guard_raises_carry_a_machine_readable_code(self, db_session, wa_lead,
                                                        wa_channel, fake_graph_http):
        """The code now comes from the raise site, not from prose-matching in
        the debug router (that mapping has been deleted)."""
        from app.core.exceptions import ComplianceError as Canonical

        with pytest.raises(Canonical) as exc_info:
            wa_channel.send(wa_outbound(wa_lead, kind="text"))
        assert exc_info.value.compliance_code == "WHATSAPP_WINDOW_CLOSED"
        assert exc_info.value.rule == "whatsapp_window_closed"

    def test_global_handler_maps_the_adapter_error_to_422(self, db_session, wa_lead,
                                                          wa_channel,
                                                          fake_graph_http):
        """The real wiring: the exception the ADAPTER raises, handed to the
        app's registered handler, must produce a 422 carrying the code.

        NOTE ON SCOPE: no non-debug HTTP endpoint reaches the send guard —
        production WhatsApp sends run in the Celery task below, not in a
        request. So this asserts the handler contract directly rather than
        inventing an endpoint that does not exist.
        """
        import asyncio
        import json

        from starlette.requests import Request

        from app.core.errors import global_exception_handler

        with pytest.raises(Exception) as exc_info:
            wa_channel.send(wa_outbound(wa_lead, kind="text"))

        # the handler reads request.headers, so hand it a real Request
        request = Request({
            "type": "http", "method": "POST", "path": "/whatsapp/send",
            "headers": [], "query_string": b"",
        })
        response = asyncio.run(global_exception_handler(request, exc_info.value))
        assert response.status_code == 422
        assert json.loads(response.body)["compliance_code"] == "WHATSAPP_WINDOW_CLOSED"

    def test_send_path_marks_a_compliance_block_by_channel(self):
        """send_message_impl must classify a compliance block, never retry it -
        and the status it writes depends on the channel.

        NEEDS_TEMPLATE is a WhatsApp state. That branch used to catch the
        adapter's own exception class, so it could only ever fire for WhatsApp;
        now that there is one canonical class it would also catch a block
        raised on the email render path, where NEEDS_TEMPLATE would be
        meaningless. This pins the mapping.
        """
        import inspect

        from app.workers import outreach_tasks

        src = inspect.getsource(outreach_tasks.send_message_impl)
        # imported from the canonical module, not from the adapter
        assert "from app.core.exceptions import ComplianceError" in src
        assert "from app.integrations.whatsapp import ComplianceError" not in src
        # and the recorded status is channel-aware
        assert "MessageStatus.NEEDS_TEMPLATE if is_whatsapp" in src
        assert "blocked_compliance" in src
