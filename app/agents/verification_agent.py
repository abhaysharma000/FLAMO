"""Verification Agent specialist exporting the verification interface."""

from app.agents.verifier import VerifierAgent, verifier_agent

# Export specialized VerificationAgent
VerificationAgent = VerifierAgent
verification_agent = verifier_agent

__all__ = ["VerificationAgent", "verification_agent"]
