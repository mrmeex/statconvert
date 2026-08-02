import { useState } from "react";
import {
  ActionIcon, Alert, Button, Checkbox, Group, MultiSelect, Select,
  Stack, Text, TextInput, Textarea, Tooltip,
} from "@mantine/core";
import { IconAlertCircle, IconPlus, IconTrash } from "@tabler/icons-react";

import type { PlannedTransformStep, TransformCondition, TransformStep } from "../lib/types";
import { ExpressionEditor } from "./ExpressionEditor";

interface TransformStepEditorProps {
  step: TransformStep;
  columns: string[];
  planned?: PlannedTransformStep;
  onChange: (step: TransformStep) => void;
}

const typeOptions = ["string", "integer", "float", "boolean", "datetime", "date", "category"];
const operators = ["eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "contains", "not_contains", "startswith", "endswith", "is_missing", "not_missing"];

function MappingEditor({ value, onChange, label }: { value: Record<string, string | number | boolean>; onChange: (value: Record<string, string>) => void; label: string }) {
  const [draft, setDraft] = useState(Object.entries(value).map(([from, to]) => `${from}=${String(to)}`).join("\n"));
  return <Textarea label={label} description="One OLD=NEW mapping per line." autosize minRows={3} value={draft} onChange={(event) => {
    const next = event.currentTarget.value;
    setDraft(next);
    const mapping: Record<string, string> = {};
    for (const line of next.split("\n")) {
      const separator = line.indexOf("=");
      if (separator > 0) mapping[line.slice(0, separator).trim()] = line.slice(separator + 1).trim();
    }
    onChange(mapping);
  }} />;
}

function ConditionEditor({ conditions, columns, onChange }: { conditions: TransformCondition[]; columns: string[]; onChange: (value: TransformCondition[]) => void }) {
  const update = (index: number, patch: Partial<TransformCondition>) => onChange(conditions.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item));
  return <Stack gap="xs">
    {conditions.map((condition, index) => <Group key={index} grow align="end">
      <Select label={index === 0 ? "Column" : undefined} searchable data={columns} value={condition.column || null} onChange={(value) => update(index, { column: value ?? "" })} />
      <Select label={index === 0 ? "Operator" : undefined} data={operators} value={condition.operator} onChange={(value) => update(index, { operator: value ?? "eq" })} />
      <TextInput label={index === 0 ? "Value" : undefined} value={String(condition.value ?? "")} disabled={["is_missing", "not_missing"].includes(condition.operator)} onChange={(event) => update(index, { value: event.currentTarget.value })} />
      <Tooltip label="Remove condition"><ActionIcon color="red" variant="subtle" onClick={() => onChange(conditions.filter((_, itemIndex) => itemIndex !== index))}><IconTrash size={17} /></ActionIcon></Tooltip>
    </Group>)}
    <Button variant="subtle" size="xs" leftSection={<IconPlus size={15} />} onClick={() => onChange([...conditions, { column: columns[0] ?? "", operator: "eq", value: "" }])}>Add condition</Button>
  </Stack>;
}

export function TransformStepEditor({ step, columns, planned, onChange }: TransformStepEditorProps) {
  const patch = (value: Partial<TransformStep>) => onChange({ ...step, ...value });
  return (
    <Stack gap="sm">
      {planned?.errors.map((error) => <Alert key={`${error.code}-${error.field}`} color="red" icon={<IconAlertCircle size={16} />} py="xs"><Text size="sm">{error.message}</Text></Alert>)}
      {step.type === "select" && <><MultiSelect label="Columns to keep, in order" searchable data={columns} value={step.columns ?? []} onChange={(value) => patch({ columns: value })} /><Checkbox label="Ignore unavailable columns" checked={step.ignore_missing ?? false} onChange={(event) => patch({ ignore_missing: event.currentTarget.checked })} /></>}
      {step.type === "drop" && <><MultiSelect label="Columns to remove" searchable data={columns} value={step.columns ?? []} onChange={(value) => patch({ columns: value })} /><Checkbox label="Ignore unavailable columns" checked={step.ignore_missing ?? false} onChange={(event) => patch({ ignore_missing: event.currentTarget.checked })} /></>}
      {step.type === "rename" && <><MappingEditor label="Rename mappings" value={step.map ?? {}} onChange={(map) => patch({ map })} /><Checkbox label="Ignore unavailable source columns" checked={step.ignore_missing ?? false} onChange={(event) => patch({ ignore_missing: event.currentTarget.checked })} /></>}
      {step.type === "convert_type" && <Group grow align="start"><Select label="Column" searchable data={columns} value={step.column ?? null} onChange={(value) => patch({ column: value ?? "" })} /><Select label="Target type" data={typeOptions} value={step.data_type ?? null} onChange={(value) => patch({ data_type: value ?? "string" })} /><Select label="On conversion error" data={["raise", "coerce", "ignore"]} value={step.errors ?? "raise"} onChange={(value) => patch({ errors: (value ?? "raise") as TransformStep["errors"] })} /></Group>}
      {step.type === "convert_type" && (step.data_type === "date" || step.data_type === "datetime") && <TextInput label="Optional datetime format" value={step.datetime_format ?? ""} onChange={(event) => patch({ datetime_format: event.currentTarget.value || undefined })} />}
      {step.type === "derive" && <><TextInput label="New column" value={step.column ?? ""} onChange={(event) => patch({ column: event.currentTarget.value })} /><ExpressionEditor value={step.expression ?? ""} onChange={(expression) => patch({ expression })} purpose="derive" columns={columns} /></>}
      {step.type === "filter" && <>
        <Select label="Filter mode" data={[{ value: "expression", label: "Safe expression" }, { value: "conditions", label: "Structured conditions" }]} value={step.expression !== undefined ? "expression" : "conditions"} onChange={(value) => value === "expression" ? onChange({ id: step.id, type: "filter", expression: "", reset_index: step.reset_index ?? true }) : onChange({ id: step.id, type: "filter", conditions: [{ column: columns[0] ?? "", operator: "eq", value: "" }], mode: "and", reset_index: step.reset_index ?? true })} />
        {step.expression !== undefined ? <ExpressionEditor value={step.expression} onChange={(expression) => patch({ expression })} purpose="filter" columns={columns} /> : <><ConditionEditor conditions={step.conditions ?? []} columns={columns} onChange={(conditions) => patch({ conditions })} /><Select label="Combine conditions" data={["and", "or"]} value={step.mode ?? "and"} onChange={(value) => patch({ mode: (value ?? "and") as "and" | "or" })} /></>}
        <Checkbox label="Reset row index after filtering" checked={step.reset_index ?? true} onChange={(event) => patch({ reset_index: event.currentTarget.checked })} />
      </>}
      {step.type === "recode" && <><Select label="Column" searchable data={columns} value={step.column ?? null} onChange={(value) => patch({ column: value ?? "" })} /><MappingEditor label="Value mappings" value={step.map ?? {}} onChange={(map) => patch({ map })} /><TextInput label="Optional default for unmapped non-missing values" value={String(step.default ?? "")} onChange={(event) => patch({ default: event.currentTarget.value || undefined })} /><Checkbox label="Update normalized value labels" checked={step.update_value_labels ?? true} onChange={(event) => patch({ update_value_labels: event.currentTarget.checked })} /></>}
      {planned && <Group gap="xs"><Text size="xs" c="dimmed">Projected output:</Text>{planned.output_columns.map((column) => <Text key={column} size="xs" ff="monospace">{column}</Text>)}</Group>}
    </Stack>
  );
}
