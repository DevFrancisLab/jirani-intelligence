"""JSON API for the React frontend. Credentials stay server-side."""

from __future__ import annotations

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.investigations import services


class HealthView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        return Response({"status": "ok", "service": "jirani-intelligence"})


class StatusView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        return Response(services.public_status())


class ConnectionsView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request: Request) -> Response:
        return Response(services.check_connections())


class ZetarisProbeView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request: Request) -> Response:
        payload = services.zetaris_select_1()
        code = status.HTTP_200_OK if payload["ok"] else status.HTTP_502_BAD_GATEWAY
        if payload["status"] == "not_configured":
            code = status.HTTP_503_SERVICE_UNAVAILABLE
        return Response(payload, status=code)


class ZetarisTaxiSampleView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request: Request) -> Response:
        payload = services.zetaris_taxi_sample()
        code = status.HTTP_200_OK if payload["ok"] else status.HTTP_502_BAD_GATEWAY
        if payload["status"] == "not_configured":
            code = status.HTTP_503_SERVICE_UNAVAILABLE
        return Response(payload, status=code)


class InvestigationView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request: Request) -> Response:
        question = (request.data.get("question") or "").strip()
        if not question:
            return Response(
                {"error": "question is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(question) > 4000:
            return Response(
                {"error": "question is too long"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(services.run_investigation(question))


class MemoryView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        try:
            limit = int(request.query_params.get("limit", "8"))
        except ValueError:
            limit = 8
        limit = max(1, min(limit, 50))
        return Response(services.memory_recent(limit))


class CockpitAnswerView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request: Request) -> Response:
        question = (request.data.get("question") or "").strip()
        answer = (request.data.get("answer") or "").strip()
        record_ids = request.data.get("record_ids") or []
        if not isinstance(record_ids, list):
            return Response(
                {"error": "record_ids must be a list"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not answer:
            return Response(
                {"error": "Paste the Nightshift Morning answer before recording it."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            payload = services.save_cockpit_answer(
                question,
                answer,
                [str(item) for item in record_ids if isinstance(item, str)],
            )
        except ValueError as error:
            return Response({"error": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload, status=status.HTTP_201_CREATED)
