"""Guided SME onboarding state machine and safe status checks."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class OnboardingStep:
    key: str
    title: str
    status: str
    explanation: str
    remediation: str | None = None

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class OnboardingService:
    """Builds a server-rendered guided setup model without exposing secrets."""

    async def build_setup_model(self, *, facts: dict[str, bool]) -> list[dict[str, str]]:
        steps: list[OnboardingStep] = []

        organization_ready = bool(facts.get("organization"))
        steps.append(
            OnboardingStep(
                key="organization",
                title="Create organization",
                status="implemented" if organization_ready else "blocked",
                explanation=(
                    "The deployment must have exactly one organization before team, project, or policy setup."
                ),
                remediation=None if organization_ready else "Use Organizations → Create organization.",
            )
        )

        oidc_ready = bool(facts.get("oidc")) and organization_ready
        steps.append(
            OnboardingStep(
                key="oidc",
                title="Configure human sign-in",
                status="implemented" if oidc_ready else "held",
                explanation=(
                    "OIDC enables centralized human sign-in. Local admin fallback remains documented for recovery."
                ),
                remediation=None if oidc_ready else "Set OIDC_* environment settings, then reload this page.",
            )
        )

        provider_ready = bool(facts.get("provider_configured")) and oidc_ready
        steps.append(
            OnboardingStep(
                key="provider",
                title="Configure provider",
                status="implemented" if provider_ready else "held",
                explanation=(
                    "Provider credentials stay server-side in environment variables. They are never displayed here."
                ),
                remediation=None if provider_ready else "Add provider metadata and its API-key environment name.",
            )
        )

        catalog_ready = bool(facts.get("catalog_imported")) and provider_ready
        steps.append(
            OnboardingStep(
                key="catalog",
                title="Approve catalog",
                status="implemented" if catalog_ready else "held",
                explanation=("Only explicitly approved models and tools can be assigned to policy bundles."),
                remediation=None if catalog_ready else "Import a reviewed catalog into an approved bundle revision.",
            )
        )

        policy_ready = bool(facts.get("policy_assigned")) and catalog_ready
        steps.append(
            OnboardingStep(
                key="policy",
                title="Assign policy",
                status="implemented" if policy_ready else "held",
                explanation=("Assignments bind to immutable revisions so later edits cannot silently change access."),
                remediation=None if policy_ready else "Preview a policy revision, confirm it, then assign it.",
            )
        )

        budget_ready = bool(facts.get("budget_defined")) and policy_ready
        steps.append(
            OnboardingStep(
                key="budget",
                title="Define budget",
                status="implemented" if budget_ready else "held",
                explanation=("PostgreSQL budgets reserve atomically with lifetime key limits."),
                remediation=None if budget_ready else "Create at least one active recurring budget period.",
            )
        )

        service_account_ready = bool(facts.get("service_account")) and budget_ready
        steps.append(
            OnboardingStep(
                key="service-account",
                title="Prepare workload identity",
                status="implemented" if service_account_ready else "deferred",
                explanation=("Service accounts separate human owners from automated workloads."),
                remediation=None if service_account_ready else "Create a service account after budgets are active.",
            )
        )

        strict_key_ready = bool(facts.get("strict_key_issued")) and service_account_ready
        steps.append(
            OnboardingStep(
                key="strict-key",
                title="Issue strict-mode key",
                status="implemented" if strict_key_ready else "blocked",
                explanation=("A usable key requires explicit endpoint/model/provider policy and accounting."),
                remediation=None if strict_key_ready else "Complete the prior prerequisites, then issue a standard key.",
            )
        )
        return [step.to_dict() for step in steps]
