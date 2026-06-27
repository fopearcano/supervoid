"""Optional fine-tuning data pipeline (Prompt 18).

PREPARED, never auto-run. Collect only EXPLICITLY approved behaviour examples
(strong/corrected responses, correct tool choices, correct refusals, good plans,
structured proposals, approval-required actions, retrieval-needed / not-needed),
sanitise them (strip chain-of-thought; redact secrets; exclude private contracts
and member data unless approved + anonymised), export versioned train/val JSONL
split by project + task category, register LoRA/PEFT adapters, evaluate them
against the Phase-17 corpus, and deploy an adapter ONLY when it beats the base
without weakening permissions or approval behaviour. Rollback returns to base.
"""
from app.services.tuning.adapters import (
    active_adapter,
    approve_adapter,
    compare_results,
    default_training_parameters,
    deploy_adapter,
    deploy_gate,
    evaluate_adapter,
    get_adapter,
    list_adapters,
    record_evaluation,
    register_adapter,
    reject_adapter,
    rollback_to_base,
    vllm_lora_config,
)
from app.services.tuning.candidates import (
    approve_example,
    counts_by_status,
    get_example,
    list_examples,
    propose_example,
    reject_example,
)
from app.services.tuning.errors import (
    TuningDeployBlocked,
    TuningError,
    TuningExclusion,
)
from app.services.tuning.export import (
    export_dataset,
    get_dataset,
    get_dataset_by_version,
    list_datasets,
    split_by_project_and_category,
)
from app.services.tuning.sanitize import SanitizeResult, sanitize_example, scan

__all__ = [
    # sanitise
    "SanitizeResult",
    "sanitize_example",
    "scan",
    # candidates / review
    "propose_example",
    "approve_example",
    "reject_example",
    "get_example",
    "list_examples",
    "counts_by_status",
    # export
    "export_dataset",
    "get_dataset",
    "get_dataset_by_version",
    "list_datasets",
    "split_by_project_and_category",
    # adapters
    "register_adapter",
    "get_adapter",
    "list_adapters",
    "compare_results",
    "record_evaluation",
    "evaluate_adapter",
    "deploy_gate",
    "approve_adapter",
    "deploy_adapter",
    "rollback_to_base",
    "reject_adapter",
    "active_adapter",
    "vllm_lora_config",
    "default_training_parameters",
    # errors
    "TuningError",
    "TuningExclusion",
    "TuningDeployBlocked",
]
