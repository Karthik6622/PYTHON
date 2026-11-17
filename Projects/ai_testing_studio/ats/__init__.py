"""AI Autonomous Testing Studio: an AI-assisted QA engineering platform."""

__version__ = "1.0.0"

# Verify HTTPS against the operating-system trust store, so corporate TLS proxies (whose root certificate is only
# installed in the OS) do not break calls to the model API and GitHub with CERTIFICATE_VERIFY_FAILED.
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:  # optional: falls back to certifi's bundle
    pass
