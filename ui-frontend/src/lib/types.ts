export interface ApiErrorPayload {
  error: {
    code: string;
    message: string;
    suggestion?: string | null;
    details?: Record<string, unknown>;
  };
}

export interface InspectResponse {
  data: Record<string, unknown>;
  command?: string;
}

export interface PathBrowseResponse {
  data: {
    root_path: string;
    directory: string;
    parent: string | null;
    selection: "file" | "directory" | "save_file";
    entries: Array<{ name: string; path: string; is_directory: boolean; size_bytes: number | null }>;
    truncated: boolean;
  };
}

export interface PlanResponse {
  workflow: "convert" | "batch" | "validate" | "transform" | "compare" | "report" | "collect";
  valid: boolean;
  command: string;
  details: Record<string, unknown>;
  warnings: string[];
}

export interface JobCreated {
  job_id: string;
  workflow: "convert" | "batch" | "validate" | "transform" | "config" | "compare" | "report" | "collect";
  status: string;
}

export interface DataResponse<T extends Record<string, unknown>> {
  data: T;
}

export interface ConfigData extends Record<string, unknown> {
  command: string;
  toml?: string;
  canonical_toml?: string;
  config_path?: string;
  output_path?: string | null;
  valid?: boolean;
  cli_command?: string;
}

export interface ReferenceData extends Record<string, unknown> {
  rows: Record<string, unknown>[];
  count: number;
  command: string;
}

export interface UiSettings {
  paths: {
    default_working_directory: string;
    path_browser_start_directory: string;
    remember_last_paths: boolean;
    last_input_directory: string;
    last_output_directory: string;
  };
  display: {
    default_table_page_size: number;
    show_command_preview: boolean;
  };
  logging: { enabled: boolean; directory: string; level: string };
}

export interface SettingsData extends Record<string, unknown> {
  settings: UiSettings;
  settings_file_path: string;
  config_directory: string;
  default_log_directory: string;
  effective_log_directory: string;
  platform: string;
  allowed_log_levels: string[];
  logging_cli_options: string[];
  warning: string | null;
}

export interface AboutData extends Record<string, unknown> {
  version: string;
  license: string;
  python_version: string;
  platform: string;
  executable: string;
  dependencies: Record<string, string>;
  ui_mode: string;
  bound_address: string;
  host: string;
  port: number;
  open_url: string;
  static_assets_present: boolean;
  settings_file_path: string;
  log_directory: string;
  privacy: Record<string, boolean>;
  links: Record<string, string>;
}

export type TransformStepType = "select" | "drop" | "rename" | "convert_type" | "derive" | "filter" | "recode" | "sort" | "distinct" | "row_number";

export interface TransformCondition {
  column: string;
  operator: string;
  value?: string | number | boolean | null;
}

export interface TransformStep {
  id: string;
  type: TransformStepType;
  columns?: string[];
  ignore_missing?: boolean;
  map?: Record<string, string | number | boolean>;
  mappings?: Array<{ from: string | number | boolean; to: string | number | boolean }>;
  column?: string;
  data_type?: string;
  errors?: "raise" | "coerce" | "ignore";
  datetime_format?: string;
  expression?: string;
  conditions?: TransformCondition[];
  mode?: "and" | "or";
  reset_index?: boolean;
  default?: string | number | boolean;
  update_value_labels?: boolean;
  keys?: Array<{ column: string; order: "ascending" | "descending"; nulls: "first" | "last" }>;
  keep?: "first" | "last";
  start?: number;
  step?: number;
}

export interface ExpressionFunction {
  name: string;
  category: string;
  minimum_arguments: number;
  maximum_arguments: number | null;
  signature: string | null;
  description: string | null;
  arguments: Array<{ name: string; kind: string; accepted_types: string[]; required: boolean; variadic: boolean }>;
  examples: string[];
  return_type: string;
  derive_allowed: boolean;
  filter_suitability: string;
  null_behavior: string | null;
  error_behavior: string | null;
}

export interface TransformFunctionResponse {
  data: { functions: ExpressionFunction[]; count: number; categories: string[] };
}

export interface ExpressionValidationResponse {
  data: {
    expression: string;
    valid: boolean;
    referenced_columns: string[];
    functions: string[];
    result_kind: string;
    span: { start: number; end: number };
    errors: Array<{ code: string; message: string; start: number; end: number; suggestion?: string }>;
    warnings: Array<{ code: string; message: string; start: number; end: number }>;
    purpose: "derive" | "filter";
  };
}

export interface PlannedTransformStep {
  step_index: number;
  step_id: string | null;
  step_type: TransformStepType;
  status: string;
  input_columns: string[];
  output_columns: string[];
  referenced_columns: string[];
  removed_columns: string[];
  renamed_columns: Record<string, string>;
  intended_types: Record<string, string>;
  errors: Array<{ code: string; message: string; field: string; referenced_column?: string; suggestion?: string }>;
  warnings: Array<{ code: string; message: string }>;
}

export interface TransformPlanResponse extends PlanResponse {
  workflow: "transform";
  details: {
    plan: {
      valid: boolean;
      initial_columns: string[];
      final_columns: string[];
      steps: PlannedTransformStep[];
      errors: Array<{ code: string; message: string; step_index: number }>;
      warnings: Array<{ code: string; message: string; step_index: number }>;
    };
    toml: string;
    command_note: string;
    input_path: string;
    output_path: string;
    object_selector: string | null;
  };
}

export interface TransformPreviewResponse {
  data: {
    valid: boolean;
    rows_before: number;
    sampled_rows: number;
    preview_rows: number;
    limit: number;
    columns_before: string[];
    columns_after: string[];
    before_rows: Record<string, unknown>[];
    sample_output_rows: Record<string, unknown>[];
    steps: Array<Record<string, unknown>>;
    errors: Array<Record<string, unknown>>;
    warnings: Array<Record<string, unknown>>;
  };
}

export interface TransformFullPreviewResponse {
  data: {
    valid: boolean;
    mode: "full_preview";
    output: { path: string; metadata_mode: string; sidecar_behavior: Record<string, unknown> };
    summary: {
      rows_before: number; rows_after: number; rows_removed: number;
      columns_before: string[]; columns_after: string[];
      columns_added: string[]; columns_removed: string[];
      columns_renamed: Record<string, string>;
      metadata_changes: Record<string, unknown>;
    };
    steps: Array<Record<string, unknown>>;
    sample: { before: Record<string, unknown>[]; after: Record<string, unknown>[] };
    truncation: Record<string, unknown>;
  };
}

export interface TransformRecipeFileResponse {
  data: {
    path: string;
    recipe: {
      version: number;
      name?: string;
      description?: string;
      steps: Array<Omit<TransformStep, "id">>;
    };
    canonical_toml: string;
  };
}

export interface JobEvent {
  sequence: number;
  kind: string;
  timestamp: string;
  message?: string | null;
  progress?: number | null;
  data: Record<string, unknown>;
}

export interface JobSnapshot {
  job_id: string;
  workflow: string;
  status: string;
  progress: number;
  result?: Record<string, unknown> | null;
  error?: { code: string; message: string } | null;
  cancel_requested: boolean;
  events: JobEvent[];
}
