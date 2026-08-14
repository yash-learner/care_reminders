from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet


class BaseViewSet(GenericViewSet):
    """Cookiecutter demo viewset kept so existing health probes still import."""

    @action(detail=False, methods=["get"])
    def hello(self, request, *args, **kwargs):
        return Response({"message": "Hello from care_reminders plugin!"})
