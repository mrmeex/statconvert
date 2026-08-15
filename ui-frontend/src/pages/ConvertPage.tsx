import { useState } from "react";
import {
  Box,
  Alert,
  Button,
  Checkbox,
  Group,
  NumberInput,
  Paper,
  Select,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { IconAlertTriangle, IconPlayerPlay, IconRoute } from "@tabler/icons-react";

import { CommandPreview } from "../components/CommandPreview";
import { ErrorAlert } from "../components/ErrorAlert";
import { JobProgress } from "../components/JobProgress";
import { PathPickerField } from "../components/PathPickerField";
import { ResultView } from "../components/ResultView";
import { TransferPlanView } from "../components/TransferPlanView";
import { WorkflowHeader } from "../components/WorkflowHeader";
import { executeWorkflow, planWorkflow } from "../lib/api";
import { writableFormatOptions } from "../lib/formats";
import { ensureOutputExtension, outputExtensionWarning, updateGeneratedExtension } from "../lib/outputPath";
import type { PlanResponse } from "../lib/types";

const formats = writableFormatOptions;
const policies = [
  { value: "current", label: "Current behavior / no policy" },
  { value: "safe", label: "Safe" },
  { value: "strict", label: "Strict" },
  { value: "analysis-ready", label: "Analysis-ready (plan only)" },
  { value: "preserve-metadata", label: "Preserve metadata" },
  { value: "smallest-types", label: "Smallest types" },
];

export function ConvertPage() {
  const [inputPath, setInputPath] = useState("");
  const [outputPath, setOutputPath] = useState("");
  const [targetFormat, setTargetFormat] = useState<string | null>("parquet");
  const [outputAutoExtended, setOutputAutoExtended] = useState(false);
  const [objectSelector, setObjectSelector] = useState("");
  const [overwrite, setOverwrite] = useState(false);
  const [createDirs, setCreateDirs] = useState(false);
  const [stream, setStream] = useState(false);
  const [chunkSize, setChunkSize] = useState<number | string>(100000);
  const [policy, setPolicy] = useState("current");
  const [optimizeTypes, setOptimizeTypes] = useState(false);
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  const selectedPolicy = policy === "current" ? null : policy;
  const invalidatePlan = () => { setPlan(null); setJobId(null); };
  const payload = (): Record<string, unknown> => ({
    input_path: inputPath,
    output_path: ensureOutputExtension(outputPath, targetFormat),
    target_format: targetFormat,
    object_selector: objectSelector || null,
    overwrite,
    create_dirs: createDirs,
    stream,
    chunk_size: stream ? Number(chunkSize) || 100000 : null,
    policy: selectedPolicy,
    optimize_types: optimizeTypes,
  });

  const runPlan = async () => {
    setLoading(true);
    setError(null);
    setJobId(null);
    try {
      setPlan(await planWorkflow("convert", payload()));
    } catch (nextError) {
      setError(nextError);
      setPlan(null);
    } finally {
      setLoading(false);
    }
  };

  const run = async () => {
    setLoading(true);
    setError(null);
    setJobId(null);
    try {
      const created = await executeWorkflow("convert", payload());
      setJobId(created.job_id);
      setPlan(null);
    } catch (nextError) {
      setError(nextError);
    } finally {
      setLoading(false);
    }
  };

  const commitOutputPath = (value: string, generatedExtension = false) => {
    const next = ensureOutputExtension(value, targetFormat);
    setOutputPath(next);
    setOutputAutoExtended(generatedExtension || next !== value);
  };
  const changeTargetFormat = (value: string | null) => {
    if (outputAutoExtended) setOutputPath(updateGeneratedExtension(outputPath, targetFormat, value));
    else {
      const next = ensureOutputExtension(outputPath, value);
      if (next !== outputPath) { setOutputPath(next); setOutputAutoExtended(true); }
    }
    setTargetFormat(value);
    invalidatePlan();
  };
  const extensionWarning = outputExtensionWarning(outputPath, targetFormat);
  const transferPlan = plan?.details.transfer_plan;
  const changePolicy = (value: string | null) => {
    setPolicy(value ?? "current");
    setOptimizeTypes(false);
    if (value && value !== "current") setStream(false);
    invalidatePlan();
  };

  return (
    <Box className="page-content">
      <WorkflowHeader
        title="Convert"
        description="Plan and run one existing StatConvert conversion with the same output-safety and streaming capability checks as the CLI."
      />
      <Stack gap="lg">
        <Paper withBorder radius="lg" p="lg">
          <Stack gap="md">
            <PathPickerField label="Input path" value={inputPath} onChange={(value) => { setInputPath(value); invalidatePlan(); }} required />
            <PathPickerField label="Output path" value={outputPath} onChange={(value) => { setOutputPath(value); setOutputAutoExtended(false); invalidatePlan(); }} onCommit={(value, generated) => { commitOutputPath(value, generated); invalidatePlan(); }} selection="save_file" extensions={targetFormat ? [`.${targetFormat}`] : []} required />
            <Group grow align="start">
              <Select label="Target format" data={formats} searchable value={targetFormat} onChange={changeTargetFormat} />
              <TextInput label="Object selector" value={objectSelector} onChange={(event) => { setObjectSelector(event.currentTarget.value); invalidatePlan(); }} />
            </Group>
            <Select
              label="Transfer policy"
              description="Current behavior keeps the existing 1.3.1 conversion path. Policies are explicit and never saved as a default."
              data={policies}
              value={policy}
              onChange={changePolicy}
            />
            <Group>
              <Checkbox label="Overwrite existing output" checked={overwrite} onChange={(event) => { setOverwrite(event.currentTarget.checked); invalidatePlan(); }} />
              <Checkbox label="Create missing directories" checked={createDirs} onChange={(event) => { setCreateDirs(event.currentTarget.checked); invalidatePlan(); }} />
              <Checkbox label="Stream supported text formats" checked={stream} disabled={selectedPolicy !== null} onChange={(event) => { setStream(event.currentTarget.checked); invalidatePlan(); }} />
            </Group>
            {stream && <NumberInput label="Chunk size" min={1} value={chunkSize} onChange={(value) => { setChunkSize(value); invalidatePlan(); }} />}
            {policy === "smallest-types" && (
              <Checkbox
                label="Apply exact type optimization"
                description="Unchecked by default. Only exact lossless decisions proven by the backend planner are applied."
                checked={optimizeTypes}
                disabled={!plan?.valid || !transferPlan}
                onChange={(event) => { setOptimizeTypes(event.currentTarget.checked); invalidatePlan(); }}
              />
            )}
            {policy === "analysis-ready" && <Text size="sm" c="dimmed">Analysis-ready is plan-only in 1.4.0; semantic recommendations are never applied.</Text>}
            {extensionWarning && <Alert color="orange" icon={<IconAlertTriangle size={18} />}>{extensionWarning}</Alert>}
            <Group justify="flex-end">
              <Button variant="light" leftSection={<IconRoute size={17} />} onClick={() => void runPlan()} loading={loading} disabled={!inputPath || !outputPath || Boolean(extensionWarning)}>{selectedPolicy ? "Preview transfer plan" : "Plan conversion"}</Button>
              <Button leftSection={<IconPlayerPlay size={17} />} onClick={() => void run()} loading={loading} disabled={!plan?.valid}>Run conversion</Button>
            </Group>
          </Stack>
        </Paper>
        <ErrorAlert error={error} />
        {plan && <CommandPreview command={plan.command} />}
        {Boolean(transferPlan) && <TransferPlanView plan={transferPlan as Record<string, unknown>} />}
        {plan && !transferPlan && <ResultView data={plan.details} title="Conversion plan" />}
        <JobProgress jobId={jobId} />
      </Stack>
    </Box>
  );
}
