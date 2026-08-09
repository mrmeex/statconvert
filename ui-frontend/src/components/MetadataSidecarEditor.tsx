import { useEffect, useMemo, useState } from "react";
import {
  Alert, Button, Checkbox, Group, Paper, Select, Stack, Table, Text,
  Textarea, TextInput, Title,
} from "@mantine/core";
import { IconDeviceFloppy, IconEye, IconPlus, IconTrash } from "@tabler/icons-react";

import { postJson } from "../lib/api";
import type { InspectResponse } from "../lib/types";
import { ErrorAlert } from "./ErrorAlert";
import { PathPickerField } from "./PathPickerField";
import { RawDetails } from "./RawDetails";

interface VariableRow {
  name: string;
  originalLabel: string;
  label: string;
  originalMeasure: string;
  measure: string;
}

interface ValueLabelRow {
  column: string;
  type: "string" | "integer" | "float" | "boolean";
  value: string;
  originalLabel: string;
  label: string;
  existing: boolean;
}

interface Props {
  path: string;
  objectSelector: string;
  metadata: Record<string, unknown> | null;
}

const asRecord = (value: unknown): Record<string, unknown> =>
  typeof value === "object" && value !== null ? value as Record<string, unknown> : {};

const typedValue = (row: ValueLabelRow): string | number | boolean => {
  if (row.type === "integer") return Number.parseInt(row.value, 10);
  if (row.type === "float") return Number.parseFloat(row.value);
  if (row.type === "boolean") return row.value.toLowerCase() === "true";
  return row.value;
};

const valueType = (value: unknown): ValueLabelRow["type"] => {
  if (typeof value === "boolean") return "boolean";
  if (typeof value === "number") return Number.isInteger(value) ? "integer" : "float";
  return "string";
};

export function MetadataSidecarEditor({ path, objectSelector, metadata }: Props) {
  const dataset = asRecord(metadata?.dataset);
  const diagnostics = asRecord(metadata?.diagnostics);
  const source = asRecord(diagnostics.source);
  const container = Boolean(source.object_kind);
  const variablesData = useMemo(
    () => Array.isArray(metadata?.variables) ? metadata.variables.map(asRecord).slice(0, 100) : [],
    [metadata],
  );
  const [opened, setOpened] = useState(false);
  const [datasetLabel, setDatasetLabel] = useState("");
  const [originalDatasetLabel, setOriginalDatasetLabel] = useState("");
  const [notes, setNotes] = useState("");
  const [originalNotes, setOriginalNotes] = useState<string[]>([]);
  const [variables, setVariables] = useState<VariableRow[]>([]);
  const [valueLabels, setValueLabels] = useState<ValueLabelRow[]>([]);
  const [outputPath, setOutputPath] = useState("");
  const [overwrite, setOverwrite] = useState(false);
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    const label = typeof dataset.dataset_label === "string" ? dataset.dataset_label : "";
    const nextNotes = Array.isArray(dataset.notes) ? dataset.notes.map(String) : [];
    setDatasetLabel(label);
    setOriginalDatasetLabel(label);
    setNotes(nextNotes.join("\n"));
    setOriginalNotes(nextNotes);
    setVariables(variablesData.map((variable) => ({
      name: String(variable.name ?? ""),
      originalLabel: typeof variable.label === "string" ? variable.label : "",
      label: typeof variable.label === "string" ? variable.label : "",
      originalMeasure: typeof variable.measure === "string" ? variable.measure : "",
      measure: typeof variable.measure === "string" ? variable.measure : "",
    })));
    setValueLabels(variablesData.flatMap((variable) => {
      const column = String(variable.name ?? "");
      return (Array.isArray(variable.value_labels) ? variable.value_labels : []).slice(0, 100).map((item) => {
        const entry = asRecord(item);
        return {
          column,
          type: valueType(entry.value),
          value: String(entry.value ?? ""),
          originalLabel: String(entry.label ?? ""),
          label: String(entry.label ?? ""),
          existing: true,
        } satisfies ValueLabelRow;
      });
    }));
    setPreview(null);
    setSaved(false);
  }, [dataset.dataset_label, dataset.notes, variablesData]);

  const invalidate = () => { setPreview(null); setSaved(false); };
  const patch = () => {
    const result: Record<string, unknown> = {};
    if (datasetLabel !== originalDatasetLabel) {
      result.dataset_label = datasetLabel
        ? { action: "set", value: datasetLabel }
        : { action: "delete" };
    }
    const noteValues = notes.split("\n").map((note) => note.trim()).filter(Boolean);
    if (JSON.stringify(noteValues) !== JSON.stringify(originalNotes)) {
      result.notes = noteValues.length
        ? { action: "replace", values: noteValues }
        : { action: "delete" };
    }
    const variableOperations = variables.flatMap((row) => {
      if (row.label === row.originalLabel) return [];
      return [{ column: row.name, action: row.label ? "set" : "delete", ...(row.label ? { value: row.label } : {}) }];
    });
    if (variableOperations.length) result.variable_labels = variableOperations;
    const measurementOperations = variables.flatMap((row) => {
      if (row.measure === row.originalMeasure) return [];
      return [{ column: row.name, action: row.measure ? "set" : "delete", ...(row.measure ? { value: row.measure } : {}) }];
    });
    if (measurementOperations.length) result.measurement_levels = measurementOperations;
    const valueOperations = valueLabels.flatMap((row) => {
      if (row.existing && row.label === row.originalLabel) return [];
      if (!row.existing && (!row.column || !row.value || !row.label)) return [];
      return [{
        column: row.column,
        action: row.label ? "set" : "delete",
        value: typedValue(row),
        ...(row.label ? { label: row.label } : {}),
      }];
    });
    if (valueOperations.length) result.value_labels = valueOperations;
    return result;
  };

  const request = (confirmedPreview = false) => ({
    path,
    object_selector: objectSelector || null,
    output_path: outputPath,
    overwrite,
    confirmed_preview: confirmedPreview,
    patch: patch(),
  });

  const runPreview = async () => {
    setLoading(true); setError(null); setSaved(false);
    try {
      const response = await postJson<InspectResponse>("/api/inspect/metadata/sidecar/preview", request());
      setPreview(response.data);
    } catch (nextError) { setError(nextError); setPreview(null); }
    finally { setLoading(false); }
  };

  const save = async () => {
    setLoading(true); setError(null);
    try {
      const response = await postJson<InspectResponse>("/api/inspect/metadata/sidecar/save", request(true));
      setPreview(response.data); setSaved(true);
    } catch (nextError) { setError(nextError); setSaved(false); }
    finally { setLoading(false); }
  };

  const validPreview = preview?.valid === true && preview?.dry_run === true;
  return (
    <Paper withBorder radius="lg" p="lg">
      <Group justify="space-between">
        <div>
          <Title order={3}>Edit sidecar metadata</Title>
          <Text size="sm" c="dimmed">Preview first; saving writes only the selected sidecar target, never the source dataset.</Text>
        </div>
        <Button variant="light" onClick={() => setOpened((value) => !value)}>{opened ? "Close editor" : "Open editor"}</Button>
      </Group>
      {opened && (
        <Stack mt="lg" gap="md">
          {container && <Alert color="yellow">Container editing is deferred until sidecars can record deterministic object identity.</Alert>}
          <TextInput label="Dataset label" value={datasetLabel} disabled={container} onChange={(event) => { setDatasetLabel(event.currentTarget.value); invalidate(); }} />
          <Textarea label="Notes" description="One note per line; replacing this list is explicit in preview." autosize minRows={2} maxRows={6} value={notes} disabled={container} onChange={(event) => { setNotes(event.currentTarget.value); invalidate(); }} />
          <Title order={4}>Variable labels and measurement levels</Title>
          <Table.ScrollContainer minWidth={700}>
            <Table striped>
              <Table.Thead><Table.Tr><Table.Th>Column</Table.Th><Table.Th>Variable label</Table.Th><Table.Th>Measurement level</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>{variables.map((row, index) => (
                <Table.Tr key={row.name}>
                  <Table.Td>{row.name}</Table.Td>
                  <Table.Td><TextInput value={row.label} disabled={container} onChange={(event) => { setVariables((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, label: event.currentTarget.value } : item)); invalidate(); }} /></Table.Td>
                  <Table.Td><Select clearable data={["nominal", "ordinal", "scale"]} value={row.measure || null} disabled={container} onChange={(value) => { setVariables((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, measure: value ?? "" } : item)); invalidate(); }} /></Table.Td>
                </Table.Tr>
              ))}</Table.Tbody>
            </Table>
          </Table.ScrollContainer>
          <Group justify="space-between"><Title order={4}>Typed value labels</Title><Button variant="light" size="xs" leftSection={<IconPlus size={15} />} disabled={container || variables.length === 0} onClick={() => { setValueLabels((rows) => [...rows, { column: variables[0]?.name ?? "", type: "string", value: "", originalLabel: "", label: "", existing: false }]); invalidate(); }}>Add value label</Button></Group>
          <Table.ScrollContainer minWidth={850}>
            <Table striped>
              <Table.Thead><Table.Tr><Table.Th>Column</Table.Th><Table.Th>Type</Table.Th><Table.Th>Value</Table.Th><Table.Th>Label</Table.Th><Table.Th /></Table.Tr></Table.Thead>
              <Table.Tbody>{valueLabels.map((row, index) => (
                <Table.Tr key={`${row.column}-${row.type}-${row.value}-${index}`}>
                  <Table.Td><Select data={variables.map((item) => item.name)} value={row.column} disabled={container || row.existing} onChange={(value) => { setValueLabels((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, column: value ?? "" } : item)); invalidate(); }} /></Table.Td>
                  <Table.Td><Select data={["string", "integer", "float", "boolean"]} value={row.type} disabled={container || row.existing} onChange={(value) => { setValueLabels((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, type: (value ?? "string") as ValueLabelRow["type"] } : item)); invalidate(); }} /></Table.Td>
                  <Table.Td><TextInput value={row.value} disabled={container || row.existing} onChange={(event) => { setValueLabels((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, value: event.currentTarget.value } : item)); invalidate(); }} /></Table.Td>
                  <Table.Td><TextInput value={row.label} disabled={container} onChange={(event) => { setValueLabels((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, label: event.currentTarget.value } : item)); invalidate(); }} /></Table.Td>
                  <Table.Td><Button variant="subtle" color="red" size="xs" leftSection={<IconTrash size={14} />} disabled={container} onClick={() => { if (row.existing) setValueLabels((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, label: "" } : item)); else setValueLabels((items) => items.filter((_, itemIndex) => itemIndex !== index)); invalidate(); }}>Delete</Button></Table.Td>
                </Table.Tr>
              ))}</Table.Tbody>
            </Table>
          </Table.ScrollContainer>
          <PathPickerField label="Sidecar save target" description="Choose a JSON sidecar in an existing local folder." value={outputPath} onChange={(value) => { setOutputPath(value); invalidate(); }} selection="save_file" extensions={[".json"]} required />
          <Group justify="space-between">
            <Checkbox label="Replace existing sidecar" checked={overwrite} onChange={(event) => { setOverwrite(event.currentTarget.checked); invalidate(); }} />
            <Group>
              <Button variant="light" leftSection={<IconEye size={17} />} disabled={container || !path || !outputPath} loading={loading} onClick={() => void runPreview()}>Validate and preview</Button>
              <Button leftSection={<IconDeviceFloppy size={17} />} disabled={!validPreview} loading={loading} onClick={() => void save()}>Save sidecar</Button>
            </Group>
          </Group>
          <ErrorAlert error={error} />
          {saved && <Alert color="green">Sidecar saved atomically. The source dataset was not modified.</Alert>}
          {preview && <Alert color={preview.valid ? "green" : "red"}>Preview valid: {String(preview.valid)} · changes: {Array.isArray(preview.changes) ? preview.changes.length : 0} · source data modified: false</Alert>}
          {preview && <RawDetails data={preview} />}
        </Stack>
      )}
    </Paper>
  );
}
