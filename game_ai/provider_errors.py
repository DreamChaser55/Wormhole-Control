"""Payload-free provider diagnostics shared by the GUI, telemetry and bridge."""
import ssl


class CertificateConfigurationError(RuntimeError):
    """An explicit CA override could not be loaded with verification enabled."""


MESSAGES = {
    "certificate_trust": "TLS certificate verification failed. Check the operating system trust store or configure SSL_CERT_FILE with a trusted PEM CA bundle.",
    "certificate_configuration": "The configured TLS CA bundle could not be loaded. Check SSL_CERT_FILE or SSL_CERT_DIR.",
    "timeout": "The planning provider request timed out.",
    "authentication": "The planning provider rejected the configured credentials.",
    "quota": "The planning provider quota is exhausted.",
    "rate_limit": "The planning provider rate limit was reached.",
    "connection": "The planning provider could not be reached. Check connectivity and proxy configuration.",
    "provider_error": "The planning provider request failed.",
    "cancellation_timeout": "The previous AI request did not stop within the cancellation deadline.",
}


def classify_provider_error(error):
    """Inspect bounded exception chains, never their messages or request payloads."""
    pending, seen, names = [error], set(), set()
    while pending and len(seen) < 16:
        item = pending.pop()
        if id(item) in seen:
            continue
        seen.add(id(item))
        if isinstance(item, ssl.SSLCertVerificationError):
            return "certificate_trust"
        if isinstance(item, CertificateConfigurationError):
            return "certificate_configuration"
        names.add(type(item).__name__)
        if type(item).__name__ == "RateLimitError" and getattr(item, "code", None) == "insufficient_quota":
            return "quota"
        for cause in (item.__cause__, item.__context__):
            if isinstance(cause, BaseException):
                pending.append(cause)
    if names & {"PlanningRetirementError"}:
        return "cancellation_timeout"
    if names & {"TimeoutError", "APITimeoutError", "ConnectTimeout", "ReadTimeout", "WriteTimeout", "PoolTimeout"}:
        return "timeout"
    if names & {"AuthenticationError", "PermissionDeniedError"}:
        return "authentication"
    if "RateLimitError" in names:
        return "rate_limit"
    if names & {"APIConnectionError", "ConnectError", "ConnectionError"}:
        return "connection"
    return "provider_error"
