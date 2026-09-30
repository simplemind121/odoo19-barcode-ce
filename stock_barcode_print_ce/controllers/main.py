import json

from odoo import fields, http
from odoo.http import request


class LabelAgentController(http.Controller):
    """Endpoints used by tools/label_print_agent.py. Authenticated by the agent token."""

    def _agent(self):
        try:
            payload = json.loads(request.httprequest.get_data() or b"{}")
        except ValueError:
            payload = {}
        agent = request.env["barcode.label.agent"]._by_token(payload.get("token"))
        return agent, payload

    @http.route("/barcode_label/agent/poll", type="http", auth="none", methods=["POST"], csrf=False, readonly=False, save_session=False)
    def poll(self, **kw):
        agent, payload = self._agent()
        if not agent:
            return request.make_json_response({"error": "invalid token"}, status=403)
        env = request.env(user=agent.create_uid.id or 1, su=True)
        agent = agent.with_env(env)
        agent.last_seen = fields.Datetime.now()
        jobs = env["barcode.label.job"].search(
            [("agent_id", "=", agent.id), ("state", "=", "queued")], order="id", limit=int(payload.get("limit") or 10))
        result = []
        for job in jobs:
            result.append({"id": job.id, "target": job.printer_id.target, "data": job.data.decode()
                           if isinstance(job.data, bytes) else job.data, "name": job.name})
        jobs.write({"state": "sent", "sent_date": fields.Datetime.now()})
        return request.make_json_response({"jobs": result})

    @http.route("/barcode_label/agent/ack", type="http", auth="none", methods=["POST"], csrf=False, readonly=False, save_session=False)
    def ack(self, **kw):
        agent, payload = self._agent()
        if not agent:
            return request.make_json_response({"error": "invalid token"}, status=403)
        env = request.env(user=agent.create_uid.id or 1, su=True)
        job = env["barcode.label.job"].browse(int(payload.get("id") or 0)).exists()
        if not job or job.agent_id.id != agent.id:
            return request.make_json_response({"error": "unknown job"}, status=404)
        if payload.get("ok"):
            job.write({"state": "done", "done_date": fields.Datetime.now(), "error": False})
        else:
            job.write({"state": "error", "error": (payload.get("error") or "")[:250]})
        return request.make_json_response({"ok": True})
