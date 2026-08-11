"""Response models for the initial local browser UI API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    """Local server readiness."""

    status: Literal["ok"] = "ok"


class VersionResponse(BaseModel):
    """Installed application identity."""

    version: str
    app_name: str = "StatConvert"
    license: str = "AGPL-3.0-or-later"


class EnvironmentResponse(BaseModel):
    """Safe local runtime facts used by the frontend shell."""

    python_version: str
    platform: str
    ui_mode: Literal["local"] = "local"
    server_host: str
    server_port: int
    static_assets_present: bool
    ui_dependencies: dict[str, bool]


class SettingsUpdateRequest(BaseModel):
    """Known local UI preferences managed separately from workflow TOML."""

    settings: dict[str, Any]


class RememberPathRequest(BaseModel):
    """One deliberate local path selection to remember."""

    path: str = Field(min_length=1)
    kind: Literal["input", "output"]


class DatasetRequest(BaseModel):
    """One explicit local dataset selection."""

    path: str = Field(min_length=1)
    object_selector: str | None = None


class PathInspectionRequest(BaseModel):
    """One explicit local path to inspect without reading a dataset."""

    path: str = Field(min_length=1)


class PathBrowseRequest(BaseModel):
    """One constrained local directory listing rooted at user-confirmed path."""

    root_path: str = Field(min_length=1)
    directory: str = Field(min_length=1)
    selection: Literal["file", "directory", "save_file"]
    extensions: list[str] = Field(default_factory=list, max_length=100)


class ObjectInspectionRequest(PathInspectionRequest):
    """Bounded object discovery options."""

    recursive: bool = False


class PeekRequest(DatasetRequest):
    """Bounded dataset preview request."""

    rows: int = Field(default=10, ge=1, le=100)


class ColumnsRequest(DatasetRequest):
    """Optional bounded column selection."""

    columns: list[str] | None = None


class FrequencyRequest(ColumnsRequest):
    """Bounded frequency-table request."""

    top: int = Field(default=20, ge=1, le=100)
    include_missing: bool = False
    max_unique: int | None = Field(default=100, ge=1, le=10_000)


class MetadataScriptExportRequest(DatasetRequest):
    """Export one existing metadata helper-script format to a local path."""

    output_path: str = Field(min_length=1)
    format: Literal["r", "spss", "stata"]
    overwrite: bool = False


class MetadataSidecarEditRequest(DatasetRequest):
    """Closed metadata patch preview/save request for one explicit sidecar target."""

    output_path: str = Field(min_length=1)
    patch: dict[str, Any]
    overwrite: bool = False
    confirmed_preview: bool = False


class ConvertRequest(BaseModel):
    """Supported single-file conversion options for the first GUI slice."""

    input_path: str = Field(min_length=1)
    output_path: str = Field(min_length=1)
    target_format: str | None = None
    object_selector: str | None = None
    overwrite: bool = False
    create_dirs: bool = False
    stream: bool = False
    chunk_size: int | None = Field(default=None, ge=1)


class BatchRequest(BaseModel):
    """Supported folder batch options for the first GUI slice."""

    input_path: str = Field(min_length=1)
    output_path: str = Field(min_length=1)
    target_format: str = Field(min_length=1)
    recursive: bool = False
    overwrite: bool = False
    create_dirs: bool = False
    preserve_structure: bool = True
    object_mode: Literal["automatic", "all", "specific"] = "automatic"
    object_selector: str | None = None
    fail_fast: bool = False
    workers: int | None = Field(default=None, ge=1)
    patterns: list[str] = Field(default_factory=list, max_length=100)
    exclude_patterns: list[str] = Field(default_factory=list, max_length=100)
    report_path: str | None = None
    stream: bool = False
    chunk_size: int | None = Field(default=None, ge=1)


class ValidateRequest(DatasetRequest):
    """Supported validation options for the first GUI slice."""

    target_format: str | None = None
    strict: bool = False
    schema_contract: str | None = None
    stream: bool = False
    chunk_size: int | None = Field(default=None, ge=1)


class TransformConditionRequest(BaseModel):
    """One existing structured filter condition."""

    model_config = ConfigDict(extra="forbid")

    column: str = Field(min_length=1)
    operator: str = Field(min_length=1)
    value: str | int | float | bool | None = None


class TransformSortKeyRequest(BaseModel):
    """One closed stable-sort key selected in the Transform editor."""

    model_config = ConfigDict(extra="forbid")

    column: str = Field(min_length=1)
    order: Literal["ascending", "descending"]
    nulls: Literal["first", "last"]


class TransformStepRequest(BaseModel):
    """One canonical ordered transform step table."""

    model_config = ConfigDict(extra="forbid")

    type: Literal[
        "select",
        "drop",
        "rename",
        "convert_type",
        "derive",
        "filter",
        "recode",
        "sort",
        "distinct",
        "row_number",
    ]
    id: str | None = None
    columns: list[str] | None = Field(default=None, max_length=500)
    ignore_missing: bool | None = None
    from_: str | None = Field(default=None, alias="from")
    to: str | None = None
    map: dict[str, str | int | float | bool] | None = None
    mappings: list[dict[str, str | int | float | bool]] | None = Field(
        default=None,
        max_length=10_000,
    )
    column: str | None = None
    data_type: str | None = None
    errors: Literal["raise", "coerce", "ignore"] | None = None
    datetime_format: str | None = None
    expression: str | None = Field(default=None, max_length=20_000)
    conditions: list[TransformConditionRequest] | None = Field(
        default=None,
        max_length=100,
    )
    mode: Literal["and", "or"] | None = None
    reset_index: bool | None = None
    default: str | int | float | bool | None = None
    update_value_labels: bool | None = None
    keys: list[TransformSortKeyRequest] | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    keep: Literal["first", "last"] | None = None
    start: int | None = None
    step: int | None = None

    def to_step_dict(self) -> dict[str, Any]:
        """Return aliases and only explicitly supplied fields."""

        return self.model_dump(by_alias=True, exclude_none=True)


class TransformRequest(BaseModel):
    """One ordered transform recipe for planning, preview, or execution."""

    input_path: str = Field(min_length=1)
    output_path: str = Field(min_length=1)
    target_format: str | None = None
    object_selector: str | None = None
    overwrite: bool = False
    create_dirs: bool = False
    steps: list[TransformStepRequest] = Field(default_factory=list, max_length=100)
    recipe_name: str | None = Field(default=None, max_length=200)
    recipe_description: str | None = Field(default=None, max_length=2_000)
    preview_limit: int = Field(default=50, ge=1, le=100)


class TransformRecipeLoadRequest(BaseModel):
    """One explicit portable recipe file selected for import."""

    path: str = Field(min_length=1)


class TransformRecipeSaveRequest(BaseModel):
    """One explicit portable recipe save target and visible ordered steps."""

    output_path: str = Field(min_length=1)
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2_000)
    steps: list[TransformStepRequest] = Field(min_length=1, max_length=100)
    overwrite: bool = False
    create_dirs: bool = False


class ExpressionValidationRequest(BaseModel):
    """Pure expression parsing request for one editor purpose."""

    expression: str = Field(max_length=20_000)
    purpose: Literal["derive", "filter"]


ConfigCommand = Literal[
    "convert", "transform", "batch", "compare", "validate", "report", "collect"
]


class ConfigInitRequest(BaseModel):
    """Create one existing validated starter workflow config."""

    command: ConfigCommand
    output_path: str | None = None
    overwrite: bool = False
    create_dirs: bool = False


class ConfigTextRequest(BaseModel):
    """Load, validate, or run TOML from a path or supplied editor text."""

    config_path: str | None = None
    toml_text: str | None = Field(default=None, max_length=1_000_000)


class ConfigExportRequest(BaseModel):
    """Write validated TOML to an explicit local path."""

    output_path: str = Field(min_length=1)
    toml_text: str = Field(max_length=1_000_000)
    overwrite: bool = False
    create_dirs: bool = False


class CompareRequest(BaseModel):
    """Existing dataset comparison options exposed by the browser UI."""

    left_path: str = Field(min_length=1)
    right_path: str = Field(min_length=1)
    object_selector: str | None = None
    left_object_selector: str | None = None
    right_object_selector: str | None = None
    compare_values: bool = True
    sample_size: int | None = Field(default=None, ge=1)
    columns: list[str] | None = Field(default=None, max_length=500)
    ignore_columns: list[str] = Field(default_factory=list, max_length=500)
    numeric_tolerance: float = Field(default=0.0, ge=0)
    key_columns: list[str] = Field(default_factory=list, max_length=100)
    max_differences: int = Field(default=50, ge=1, le=1000)
    strict: bool = False
    report_path: str | None = None
    report_format: Literal["csv", "json", "html"] | None = None


class ReportRequest(BaseModel):
    """Existing bounded dataset-report options exposed by the browser UI."""

    input_path: str = Field(min_length=1)
    output_path: str = Field(min_length=1)
    object_selector: str | None = None
    output_format: Literal["csv", "json", "html"] | None = None
    overwrite: bool = False
    create_dirs: bool = False
    preset: Literal["quick", "full", "validation", "metadata"] | None = None
    sections: list[str] | None = Field(default=None, max_length=20)
    frequencies: bool = False
    columns: list[str] | None = Field(default=None, max_length=500)
    frequency_top: int = Field(default=20, ge=1, le=1000)
    frequency_include_missing: bool = False
    frequency_max_unique: int | None = Field(default=None, ge=1)
    max_table_rows: int = Field(default=1000, ge=1, le=100_000)
    max_preview_values: int = Field(default=5, ge=1, le=1000)
    target_format: str | None = None
    strict_validation: bool = False
    schema_contract: str | None = None


class CollectRequest(BaseModel):
    """Existing manifest-driven collection options exposed by the browser UI."""

    manifest_path: str = Field(min_length=1)
    output_path: str = Field(min_length=1)
    base_dir: str | None = None
    overwrite: bool = False
    create_dirs: bool = False
    validate_inputs: bool = False
    strict_validation: bool = False


class CollectManifestStarterRequest(BaseModel):
    """Safe output options for one current-schema starter manifest."""

    output_path: str = Field(min_length=1)
    overwrite: bool = False
    create_dirs: bool = False


class PlanResponse(BaseModel):
    """Read-only workflow plan and equivalent CLI command."""

    workflow: Literal[
        "convert", "batch", "validate", "transform", "compare", "report", "collect"
    ]
    valid: bool = True
    command: str
    details: dict[str, object]
    warnings: list[str] = Field(default_factory=list)


class JobCreatedResponse(BaseModel):
    """Identifier returned after background work is accepted."""

    job_id: str
    workflow: Literal[
        "convert", "batch", "validate", "transform", "config", "compare", "report", "collect"
    ]
    status: str
