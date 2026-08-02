import { ResultView } from "./ResultView";

interface WorkflowResultViewProps {
  workflow: string;
  data: Record<string, unknown>;
}

function record(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function details(data: Record<string, unknown>): Record<string, unknown> {
  return record(record(data.plan).details);
}

function compact(values: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(values).filter(([, value]) => value !== undefined && value !== null && value !== ""));
}

function pathFormat(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const name = value.replaceAll("\\", "/").split("/").at(-1) ?? "";
  return name.includes(".") ? name.split(".").at(-1)?.toLowerCase() : undefined;
}

export function WorkflowResultView({ workflow, data }: WorkflowResultViewProps) {
  const plan = details(data);
  let summary: Record<string, unknown> = data;

  if (workflow === "convert") {
    const conversion = record(data.conversion);
    summary = compact({
      status: "Completed",
      input_path: plan.input_path,
      output_path: conversion.output_path ?? plan.output_path,
      source_format: pathFormat(plan.input_path),
      target_format: pathFormat(conversion.output_path ?? plan.output_path),
      source_backend: plan.input_backend,
      target_backend: plan.output_backend,
      rows: conversion.rows,
      columns: conversion.columns,
      streaming: conversion.streaming ?? plan.stream,
      chunks: conversion.chunks,
    });
  } else if (workflow === "transform") {
    const transformPlan = record(plan.plan);
    summary = compact({
      status: "Completed",
      input_path: plan.input_path,
      output_path: data.output_path ?? plan.output_path,
      target_format: pathFormat(data.output_path ?? plan.output_path),
      steps: Array.isArray(transformPlan.steps) ? transformPlan.steps.length : undefined,
      rows: data.rows,
      columns: data.columns,
    });
  } else if (workflow === "report") {
    summary = compact({
      status: "Completed",
      input_path: plan.input_path,
      output_path: data.output_file ?? plan.output_path,
      report_format: data.format,
      preset: data.preset ?? plan.preset,
      rows: plan.rows,
      columns: plan.columns,
      sections_included: data.section_keys ?? plan.sections,
      issues: data.issues,
      has_errors: data.has_errors,
      has_warnings: data.has_warnings,
      schema_contract: plan.schema_contract,
    });
  } else if (workflow === "collect") {
    summary = compact({
      status: "Completed",
      manifest_path: plan.manifest_path,
      output_path: data.output_path ?? plan.output_path,
      objects_collected: data.objects,
      rows: data.rows,
      object_names: data.object_names,
    });
  } else if (workflow === "config") {
    summary = compact({
      status: data.status ?? "Completed",
      config_path: data.config_path,
      workflow: data.command,
      cli_command: data.cli_command,
    });
  }

  return <ResultView data={summary} rawData={data} title="Job result" />;
}
