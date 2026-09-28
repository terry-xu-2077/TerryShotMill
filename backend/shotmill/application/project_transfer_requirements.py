"""Portable dependency descriptions, never executable Provider configuration."""

import re

from shotmill.application.project_transfer_source import ProjectTransferSource
from shotmill.media.project_package import _portable_path


def _identifier(value: object) -> str | None:
    if not isinstance(value, str) or not value or len(value) > 1000:
        return None
    # Model identifiers may use namespace/name; machine paths and URLs may not.
    try:
        _portable_path(value)
    except ValueError:
        return None
    return value


def portable_provider_requirements(source: ProjectTransferSource) -> list[dict]:
    """Whitelist only labels needed to configure the destination machine.

Do not copy workflowSnapshot, modelInputs, localInference, credential fingerprints,
headers or endpoints. A requirement must never be passed to bind_profile().
Historical prompts/results remain separate from this dependency description.
"""
    requirements: list[dict] = []
    seen: set[tuple] = set()
    for kind, jobs in (("video", source.jobs), ("prompt", source.prompt_jobs)):
        for job in jobs:
            profile = job.provider_profile_snapshot
            provider = profile.get("providerId")
            if (not isinstance(provider, str)
                    or not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", provider)):
                provider = None
            workflow = _identifier(profile.get("workflowId")) if kind == "video" else None
            model = _identifier(profile.get("modelId"))
            identity = (kind, provider, workflow, model)
            if identity in seen:
                continue
            seen.add(identity)
            requirement = {"kind": kind, "requiresConfiguration": True}
            if provider:
                requirement["providerId"] = provider
            if workflow:
                requirement["workflowId"] = workflow
            if model:
                requirement["modelId"] = model
            requirements.append(requirement)
    # A task need not have generated a Job yet. Its selected profile is still a
    # destination dependency, not permission to bind a same-named local profile.
    for task in source.tasks:
        params = task.generation_params
        profile = params.get("workflowProfileId") or params.get("profileId")
        selection = params.get("workflowInputs") or {}
        workflow = selection.get("workflowId") if isinstance(selection, dict) else None
        if not profile and not workflow:
            continue
        requirement = {"kind": "video", "requiresConfiguration": True}
        for key, value in (("workflowProfileId", profile), ("workflowId", workflow)):
            identifier = _identifier(value)
            if identifier:
                requirement[key] = identifier
        if requirement not in requirements:
            requirements.append(requirement)
    return requirements
