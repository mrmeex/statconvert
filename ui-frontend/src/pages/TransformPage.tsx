import { useCallback, useEffect, useRef, useState } from "react";
import {
  Accordion, ActionIcon, Alert, Badge, Box, Button, Checkbox, Group, NumberInput, Paper,
  Select, Stack, Text, TextInput, Title, Tooltip,
} from "@mantine/core";
import {
  IconAlertCircle, IconArrowDown, IconArrowUp, IconCopy, IconEye,
  IconDownload, IconPlayerPlay, IconPlus, IconRefresh, IconTrash, IconUpload,
} from "@tabler/icons-react";

import { BeforeAfterPreview } from "../components/BeforeAfterPreview";
import { CommandPreview } from "../components/CommandPreview";
import { ErrorAlert } from "../components/ErrorAlert";
import { JobProgress } from "../components/JobProgress";
import { PathPickerField } from "../components/PathPickerField";
import { TomlPreview } from "../components/TomlPreview";
import { TransformStepEditor } from "../components/TransformStepEditor";
import { ResultView } from "../components/ResultView";
import { WorkflowHeader } from "../components/WorkflowHeader";
import { executeWorkflow, postJson } from "../lib/api";
import { writableFormatOptions } from "../lib/formats";
import { ensureOutputExtension, outputExtensionWarning, updateGeneratedExtension } from "../lib/outputPath";
import type {
  TransformFullPreviewResponse, TransformPlanResponse, TransformPreviewResponse,
  TransformRecipeFileResponse, TransformStep, TransformStepType,
} from "../lib/types";

const formats = writableFormatOptions;
const stepTypes: Array<{ value: TransformStepType; label: string }> = [
  { value: "select", label: "Select columns" }, { value: "drop", label: "Drop columns" },
  { value: "rename", label: "Rename columns" }, { value: "convert_type", label: "Convert type" },
  { value: "derive", label: "Derive column" }, { value: "filter", label: "Filter rows" },
  { value: "recode", label: "Recode values" }, { value: "sort", label: "Sort rows" },
  { value: "distinct", label: "Distinct rows" }, { value: "row_number", label: "Row number" },
];

function complete(step: TransformStep): boolean {
  if ((step.type === "select" || step.type === "drop") && !step.columns?.length) return false;
  if (step.type === "rename" && !Object.keys(step.map ?? {}).length) return false;
  if (step.type === "convert_type" && (!step.column || !step.data_type)) return false;
  if (step.type === "derive" && (!step.column || !step.expression)) return false;
  if (step.type === "filter" && !(step.expression || step.conditions?.length)) return false;
  if (step.type === "recode" && (!step.column || !(step.mappings?.length || Object.keys(step.map ?? {}).length))) return false;
  if (step.type === "sort" && (!step.keys?.length || step.keys.some((key) => !key.column.trim()))) return false;
  if (step.type === "distinct" && (!step.columns?.length || step.columns.some((column) => !column.trim()))) return false;
  if (step.type === "row_number" && (!step.column?.trim() || (step.step ?? 1) < 1)) return false;
  return true;
}

export function TransformPage() {
  const counter = useRef(0);
  const [inputPath, setInputPath] = useState(""); const [outputPath, setOutputPath] = useState("");
  const [targetFormat, setTargetFormat] = useState<string | null>("parquet"); const [objectSelector, setObjectSelector] = useState("");
  const [outputAutoExtended, setOutputAutoExtended] = useState(false);
  const [overwrite, setOverwrite] = useState(false); const [createDirs, setCreateDirs] = useState(false);
  const [steps, setSteps] = useState<TransformStep[]>([]); const [newStepType, setNewStepType] = useState<TransformStepType | null>("derive");
  const [recipePath, setRecipePath] = useState(""); const [recipeName, setRecipeName] = useState(""); const [recipeDescription, setRecipeDescription] = useState(""); const [overwriteRecipe, setOverwriteRecipe] = useState(false);
  const [previewLimit, setPreviewLimit] = useState<number | string>(20);
  const [plan, setPlan] = useState<TransformPlanResponse | null>(null); const [preview, setPreview] = useState<TransformPreviewResponse["data"] | null>(null); const [fullPreview, setFullPreview] = useState<TransformFullPreviewResponse["data"] | null>(null);
  const [jobId, setJobId] = useState<string | null>(null); const [error, setError] = useState<unknown>(null); const [planning, setPlanning] = useState(false); const [working, setWorking] = useState(false);

  const nextId = () => `step-${Date.now()}-${++counter.current}`;
  const defaultStep = (type: TransformStepType): TransformStep => {
    const first = plan?.details.plan.initial_columns[0] ?? "column";
    const id = nextId();
    if (type === "select" || type === "drop") return { id, type, columns: [first], ignore_missing: false };
    if (type === "rename") return { id, type, map: { [first]: "renamed_column" }, ignore_missing: false };
    if (type === "convert_type") return { id, type, column: first, data_type: "string", errors: "raise" };
    if (type === "derive") return { id, type, column: "new_column", expression: first };
    if (type === "filter") return { id, type, expression: `${first} == ${first}`, reset_index: true };
    if (type === "sort") return { id, type, keys: [{ column: first, order: "ascending", nulls: "last" }] };
    if (type === "distinct") return { id, type, columns: [first], keep: "first" };
    if (type === "row_number") return { id, type, column: "row_id", start: 1, step: 1 };
    return { id, type, column: first, mappings: [{ from: "old", to: "new" }], update_value_labels: true };
  };
  const payload = useCallback((): Record<string, unknown> => ({ input_path: inputPath, output_path: ensureOutputExtension(outputPath, targetFormat), target_format: targetFormat, object_selector: objectSelector || null, overwrite, create_dirs: createDirs, steps, recipe_name: recipeName || null, recipe_description: recipeDescription || null, preview_limit: Number(previewLimit) || 20 }), [createDirs, inputPath, objectSelector, outputPath, overwrite, previewLimit, recipeDescription, recipeName, steps, targetFormat]);
  const canPlan = Boolean(inputPath && outputPath && targetFormat && steps.every(complete));

  const refreshPlan = useCallback(async () => {
    if (!canPlan) { setPlan(null); return; }
    setPlanning(true); setError(null);
    try { setPlan(await postJson<TransformPlanResponse>("/api/transform/plan", payload())); }
    catch (nextError) { setError(nextError); setPlan(null); }
    finally { setPlanning(false); }
  }, [canPlan, payload]);

  useEffect(() => {
    if (!canPlan) return;
    const timer = window.setTimeout(() => void refreshPlan(), 550);
    return () => window.clearTimeout(timer);
  }, [canPlan, refreshPlan]);

  const updateStep = (index: number, step: TransformStep) => { setSteps((current) => current.map((item, itemIndex) => itemIndex === index ? step : item)); setPreview(null); setFullPreview(null); };
  const move = (index: number, offset: number) => setSteps((current) => { const next = [...current]; const target = index + offset; if (target < 0 || target >= next.length) return current; [next[index], next[target]] = [next[target], next[index]]; return next; });
  const runPreview = async () => { setWorking(true); setError(null); setFullPreview(null); try { const response = await postJson<TransformPreviewResponse>("/api/transform/preview-recipe", payload()); setPreview(response.data); } catch (nextError) { setError(nextError); } finally { setWorking(false); } };
  const runFullPreview = async () => { setWorking(true); setError(null); setPreview(null); try { const response = await postJson<TransformFullPreviewResponse>("/api/transform/preview-full", payload()); setFullPreview(response.data); } catch (nextError) { setError(nextError); } finally { setWorking(false); } };
  const loadRecipe = async () => { setWorking(true); setError(null); try { const response = await postJson<TransformRecipeFileResponse>("/api/transform/recipe/load", { path: recipePath }); const loaded = response.data.recipe; setSteps(loaded.steps.map((step) => ({ ...step, id: nextId() } as TransformStep))); setRecipeName(loaded.name ?? ""); setRecipeDescription(loaded.description ?? ""); setPreview(null); setFullPreview(null); } catch (nextError) { setError(nextError); } finally { setWorking(false); } };
  const saveRecipe = async () => { const path = ensureOutputExtension(recipePath, "toml"); setRecipePath(path); setWorking(true); setError(null); try { await postJson<TransformRecipeFileResponse>("/api/transform/recipe/save", { output_path: path, name: recipeName || null, description: recipeDescription || null, steps, overwrite: overwriteRecipe, create_dirs: false }); } catch (nextError) { setError(nextError); } finally { setWorking(false); } };
  const run = async () => { setWorking(true); setError(null); setJobId(null); try { const created = await executeWorkflow("transform", payload()); setJobId(created.job_id); setPreview(null); setFullPreview(null); } catch (nextError) { setError(nextError); } finally { setWorking(false); } };
  const commitOutputPath = (value: string, generatedExtension = false) => { const next = ensureOutputExtension(value, targetFormat); setOutputPath(next); setOutputAutoExtended(generatedExtension || next !== value); };
  const commitRecipePath = (value: string) => setRecipePath(ensureOutputExtension(value, "toml"));
  const changeTargetFormat = (value: string | null) => {
    if (outputAutoExtended) setOutputPath(updateGeneratedExtension(outputPath, targetFormat, value));
    else {
      const next = ensureOutputExtension(outputPath, value);
      if (next !== outputPath) { setOutputPath(next); setOutputAutoExtended(true); }
    }
    setTargetFormat(value);
  };
  const extensionWarning = outputExtensionWarning(outputPath, targetFormat);

  return <Box className="page-content">
    <WorkflowHeader title="Transform" description="Build, validate, preview, and run an exact ordered transform recipe using StatConvert’s existing safe transformation engine." />
    <Stack gap="lg">
      <Paper withBorder radius="lg" p="lg"><Stack gap="md">
        <Group grow align="start"><PathPickerField label="Input dataset" value={inputPath} onChange={setInputPath} required /><PathPickerField label="Output dataset" value={outputPath} onChange={(value) => { setOutputPath(value); setOutputAutoExtended(false); }} onCommit={commitOutputPath} selection="save_file" extensions={targetFormat ? [`.${targetFormat}`] : []} required /></Group>
        <Group grow align="start"><Select label="Output format" searchable data={formats} value={targetFormat} onChange={changeTargetFormat} /><TextInput label="Object selector" description="Optional workbook sheet or container object." value={objectSelector} onChange={(event) => setObjectSelector(event.currentTarget.value)} /></Group>
        <Group><Checkbox label="Overwrite existing output" checked={overwrite} onChange={(event) => setOverwrite(event.currentTarget.checked)} /><Checkbox label="Create missing directories" checked={createDirs} onChange={(event) => setCreateDirs(event.currentTarget.checked)} /></Group>
        {extensionWarning && <Alert color="orange" icon={<IconAlertCircle size={17} />}>{extensionWarning}</Alert>}
      </Stack></Paper>

      <Paper withBorder radius="lg" p="lg"><Group justify="space-between" align="end" mb="md"><div><Title order={2}>Ordered recipe</Title><Text size="sm" c="dimmed">Every edit or reorder replans this step and all steps below it.</Text></div><Group align="end"><Select label="Step type" data={stepTypes} value={newStepType} onChange={(value) => setNewStepType(value as TransformStepType | null)} /><Button leftSection={<IconPlus size={17} />} disabled={!newStepType} onClick={() => newStepType && setSteps((current) => [...current, defaultStep(newStepType)])}>Add step</Button></Group></Group>
        <Stack gap="sm" mb="md"><Group grow align="end"><TextInput label="Recipe name" value={recipeName} onChange={(event) => setRecipeName(event.currentTarget.value)} /><TextInput label="Recipe description" value={recipeDescription} onChange={(event) => setRecipeDescription(event.currentTarget.value)} /></Group><Group align="end"><Box style={{ flex: 1 }}><PathPickerField label="Portable recipe path" description="Enter a TOML path, select an existing recipe, or choose a folder and file name for saving." value={recipePath} onChange={setRecipePath} onCommit={commitRecipePath} extensions={[".toml"]} allowSaveSelection /></Box><Checkbox label="Overwrite recipe" checked={overwriteRecipe} onChange={(event) => setOverwriteRecipe(event.currentTarget.checked)} /><Button variant="light" leftSection={<IconUpload size={17} />} disabled={!recipePath.trim()} onClick={() => void loadRecipe()}>Load recipe</Button><Button variant="light" leftSection={<IconDownload size={17} />} disabled={!recipePath.trim() || !steps.length} onClick={() => void saveRecipe()}>Save recipe</Button></Group></Stack>
        {steps.length === 0 && <Alert color="blue">Add one of the ten supported ordered step types to begin.</Alert>}
        <Stack gap="sm">{steps.map((step, index) => {
          const planned = plan?.details.plan.steps[index]; const columns = planned?.input_columns ?? plan?.details.plan.initial_columns ?? [];
          return <Paper key={step.id} withBorder radius="md" p="md" className="transform-step"><Group justify="space-between" mb="sm"><Group><Badge>{index + 1}</Badge><Text fw={700}>{stepTypes.find((item) => item.value === step.type)?.label}</Text><Badge color={planned?.status === "invalid" ? "red" : planned ? "green" : complete(step) ? "gray" : "orange"} variant="light">{planned?.status ?? (complete(step) ? "waiting for plan" : "incomplete")}</Badge></Group><Group gap={4}><Tooltip label="Move up"><ActionIcon variant="subtle" disabled={index === 0} onClick={() => move(index, -1)}><IconArrowUp size={17} /></ActionIcon></Tooltip><Tooltip label="Move down"><ActionIcon variant="subtle" disabled={index === steps.length - 1} onClick={() => move(index, 1)}><IconArrowDown size={17} /></ActionIcon></Tooltip><Tooltip label="Duplicate"><ActionIcon variant="subtle" onClick={() => setSteps((current) => [...current.slice(0, index + 1), { ...step, id: nextId(), map: step.map ? { ...step.map } : undefined, mappings: step.mappings ? step.mappings.map((item) => ({ ...item })) : undefined, keys: step.keys ? step.keys.map((item) => ({ ...item })) : undefined, columns: step.columns ? [...step.columns] : undefined, conditions: step.conditions ? step.conditions.map((condition) => ({ ...condition })) : undefined }, ...current.slice(index + 1)])}><IconCopy size={17} /></ActionIcon></Tooltip><Tooltip label="Delete"><ActionIcon color="red" variant="subtle" onClick={() => setSteps((current) => current.filter((_, itemIndex) => itemIndex !== index))}><IconTrash size={17} /></ActionIcon></Tooltip></Group></Group><TransformStepEditor step={step} columns={columns} planned={planned} onChange={(value) => updateStep(index, value)} /></Paper>;
        })}</Stack>
      </Paper>

      <ErrorAlert error={error} />
      <JobProgress jobId={jobId} />
      {plan?.details.plan.errors.map((issue) => <Alert key={`${issue.step_index}-${issue.code}`} color="red" icon={<IconAlertCircle size={17} />}>Step {issue.step_index + 1}: {issue.message}</Alert>)}
      {plan && <Paper withBorder radius="lg" p="md"><Group justify="space-between"><div><Text fw={700}>Projected columns</Text><Text size="sm" c="dimmed">{plan.details.plan.final_columns.join(" · ") || "No projected columns"}</Text></div><Badge color={plan.valid ? "green" : "red"}>{plan.valid ? "Recipe valid" : "Recipe invalid"}</Badge></Group></Paper>}
      <Group justify="flex-end"><Button variant="light" leftSection={<IconRefresh size={17} />} onClick={() => void refreshPlan()} loading={planning} disabled={!canPlan || Boolean(extensionWarning)}>Replan</Button><NumberInput label="Sample rows" min={1} max={100} value={previewLimit} onChange={setPreviewLimit} w={130} /><Button variant="light" leftSection={<IconEye size={17} />} onClick={() => void runPreview()} loading={working} disabled={!plan?.valid || steps.length === 0 || Boolean(extensionWarning)}>Sample preview</Button><Button variant="light" leftSection={<IconEye size={17} />} onClick={() => void runFullPreview()} loading={working} disabled={!plan?.valid || steps.length === 0 || Boolean(extensionWarning)}>Full impact preview</Button><Button leftSection={<IconPlayerPlay size={17} />} onClick={() => void run()} loading={working} disabled={!plan?.valid || steps.length === 0 || Boolean(extensionWarning)}>Run transform</Button></Group>
      {plan && <CommandPreview command={plan.command} />}
      {plan && <Text size="sm" c="dimmed">{plan.details.command_note}</Text>}
      {plan && <Accordion variant="contained"><Accordion.Item value="recipe-toml"><Accordion.Control>Canonical portable recipe TOML</Accordion.Control><Accordion.Panel><TomlPreview toml={plan.details.toml} /></Accordion.Panel></Accordion.Item></Accordion>}
      <BeforeAfterPreview preview={preview} />
      {fullPreview && <Paper withBorder radius="lg" p="lg"><Title order={3}>Full impact preview</Title><Text size="sm" c="dimmed" mb="md">Exact full-dataset result; no data file or sidecar was written.</Text><Group mb="md"><Badge>{fullPreview.summary.rows_before} → {fullPreview.summary.rows_after} rows</Badge><Badge>{fullPreview.summary.rows_removed} removed</Badge><Badge>{fullPreview.summary.columns_before.length} → {fullPreview.summary.columns_after.length} columns</Badge><Badge>{fullPreview.output.metadata_mode}</Badge></Group><Stack gap="md"><ResultView title="Target and sidecar" data={fullPreview.output as Record<string, unknown>} /><ResultView title="Step impact" data={{ rows: fullPreview.steps }} rawData={fullPreview} /><ResultView title="Metadata impact" data={fullPreview.summary.metadata_changes as Record<string, unknown>} /><Group grow align="start"><ResultView title="Before sample" data={{ rows: fullPreview.sample.before }} /><ResultView title="After sample" data={{ rows: fullPreview.sample.after }} /></Group></Stack></Paper>}
    </Stack>
  </Box>;
}
