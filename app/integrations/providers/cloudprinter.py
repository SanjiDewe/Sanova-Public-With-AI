from app.config import assert_sandbox_url, provider_config
from app.integrations.providers.base import PhysicalProvider, ProviderResult, ProviderStatus, ProviderError
from app.integrations.providers.http import SandboxHttpClient, SandboxHttpRequest
from app.integrations.providers.mock import MockProvider
from app.integrations.providers.normalization import normalize_error, normalize_status
from app.core.models.task import PhysicalTask, TaskState


class CloudprinterSandboxAdapter(PhysicalProvider):
    name = "cloudprinter-sandbox"
    order_path = "/cloudcore/1.0/orders/add"

    def __init__(self, client=None, simulation: bool = True):
        self._client = client
        self.simulation = simulation

    def build_order_request(self, task: PhysicalTask) -> SandboxHttpRequest:
        cfg = provider_config("cloudprinter")
        if not cfg.base_url:
            raise RuntimeError("SANOVA_CLOUDPRINTER_SANDBOX_BASE_URL is not configured.")
        body = {"reference": task.id, "metadata": {"sanovaTaskId": task.id}}
        url = f"{cfg.base_url.rstrip('/')}{self.order_path}"
        assert_sandbox_url(url, "cloudprinter")
        return SandboxHttpRequest("POST", url, {"Content-Type": "application/json"}, body)

    def normalize_status(self, raw_status: str) -> ProviderStatus:
        return normalize_status(raw_status)

    def normalize_error(self, error: Exception | str) -> ProviderError:
        return normalize_error(error)

    def submit_sandbox(self, task: PhysicalTask) -> ProviderResult:
        if self.simulation:
            result = MockProvider().submit_sandbox(task)
            return ProviderResult(
                result.accepted, ProviderStatus.SUBMITTED if result.accepted else ProviderStatus.FAILED,
                result.external_id, result.message, result.error,
            )
        cfg = provider_config("cloudprinter")
        if not cfg.http_enabled:
            raise RuntimeError("Sandbox HTTP is disabled. Set SANOVA_SANDBOX_HTTP_ENABLED=true explicitly.")
        try:
            if not self._client:
                if not cfg.api_key or not cfg.base_url:
                    raise RuntimeError("Cloudprinter sandbox credentials/configuration are incomplete.")
                self._client = SandboxHttpClient(cfg.api_key, cfg.base_url, "cloudprinter")
            response = self._client.request_json(
                "POST", self.order_path,
                {"reference": task.id, "metadata": {"sanovaTaskId": task.id}},
            )
            task.state = TaskState.SUBMITTED
            external_id = response.get("id") if isinstance(response, dict) else None
            return ProviderResult(True, ProviderStatus.SUBMITTED, external_id, "Cloudprinter sandbox accepted the request")
        except Exception as exc:
            err = self.normalize_error(exc)
            return ProviderResult(False, ProviderStatus.FAILED, message=err.message, error=err)
