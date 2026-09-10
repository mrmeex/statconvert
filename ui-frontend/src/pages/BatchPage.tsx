import { useCallback, useEffect, useState } from "react";
import {
  Accordion, Alert, Box, Button, Checkbox, Group, NumberInput, Paper, Select,
  Stack, Text, Textarea, TextInput,
} from "@mantine/core";
import { IconAlertTriangle, IconPlayerPlay, IconRoute } from "@tabler/icons-react";

import { BatchResultView } from "../components/BatchResultView";
import { CommandPreview } from "../components/CommandPreview";
import { ErrorAlert } from "../components/ErrorAlert";
import { JobProgress } from "../components/JobProgress";
import { PathPickerField } from "../components/PathPickerField";
import { WorkflowHeader } from "../components/WorkflowHeader";
import { executeWorkflow, getActiveJob, planWorkflow } from "../lib/api";
import { writableFormatOptions } from "../lib/formats";
import type { JobSnapshot, PlanResponse } from "../lib/types";

const formats = writableFormatOptions;
const policies = [
  { value: "current", label: "Current behavior (no policy)" },
  { value: "safe", label: "Safe" },
  { value: "strict", label: "Strict" },
  { value: "analysis-ready", label: "Analysis-ready (plan only)" },
  { value: "preserve-metadata", label: "Preserve metadata" },
  { value: "smallest-types", label: "Smallest types" },
];
const reportFormats = [
  { value: "csv", label: "CSV" }, { value: "json", label: "JSON" },
  { value: "html", label: "HTML" },
];
const splitPatterns = (value: string) => value.split(/[\n,]+/).map((item) => item.trim()).filter(Boolean);
const terminalStatuses = new Set(["succeeded", "failed", "cancelled"]);
let batchSessionJobId: string | null = null;
type BatchAction = "files" | "full" | "execute";

export function BatchPage() {
  const [inputPath, setInputPath] = useState(""); const [outputPath, setOutputPath] = useState("");
  const [targetFormat, setTargetFormat] = useState<string | null>("parquet");
  const [recursive, setRecursive] = useState(false); const [overwrite, setOverwrite] = useState(false); const [createDirs, setCreateDirs] = useState(true);
  const [preserveStructure, setPreserveStructure] = useState(true); const [objectMode, setObjectMode] = useState<string | null>("automatic"); const [objectSelector, setObjectSelector] = useState("");
  const [failFast, setFailFast] = useState(false); const [allowBlocked, setAllowBlocked] = useState(false); const [patterns, setPatterns] = useState(""); const [excludePatterns, setExcludePatterns] = useState("");
  const [recipePath, setRecipePath] = useState(""); const [policy, setPolicy] = useState<string | null>("current"); const [optimizeTypes, setOptimizeTypes] = useState(false);
  const [reportPath, setReportPath] = useState(""); const [reportFormat, setReportFormat] = useState<string | null>("json");
  const [workers, setWorkers] = useState<number | string>("");
  const [stream, setStream] = useState(false); const [chunkSize, setChunkSize] = useState<number | string>(100000);
  const [plan, setPlan] = useState<PlanResponse | null>(null); const [jobId, setJobId] = useState<string | null>(() => batchSessionJobId); const [jobStatus, setJobStatus] = useState<string | null>(() => batchSessionJobId ? "connecting" : null); const [error, setError] = useState<unknown>(null); const [loading, setLoading] = useState(false);

  useEffect(() => {
    let mounted = true;
    void getActiveJob("batch").then(({ data }) => {
      if (!mounted || !data) return;
      batchSessionJobId = data.job_id; setJobId(data.job_id); setJobStatus(data.status);
    }).catch((nextError) => { if (mounted && !batchSessionJobId) setError(nextError); });
    return () => { mounted = false; };
  }, []);

  useEffect(() => {
    setPlan(null); setError(null);
    if (jobStatus && terminalStatuses.has(jobStatus)) {
      batchSessionJobId = null; setJobId(null); setJobStatus(null);
    }
  }, [
    inputPath, outputPath, targetFormat, recursive, overwrite, createDirs,
    preserveStructure, objectMode, objectSelector, failFast, allowBlocked,
    patterns, excludePatterns, recipePath, policy, optimizeTypes, reportPath,
    reportFormat, workers, stream, chunkSize,
  ]);

  const payload = (action: BatchAction): Record<string, unknown> => ({
    input_path: inputPath, output_path: outputPath, target_format: targetFormat,
    recursive, overwrite, create_dirs: createDirs, preserve_structure: preserveStructure,
    object_mode: objectMode, object_selector: objectMode === "specific" ? objectSelector || null : null,
    fail_fast: failFast, allow_blocked: allowBlocked,
    workers: workers === "" ? null : Number(workers), patterns: splitPatterns(patterns), exclude_patterns: splitPatterns(excludePatterns),
    recipe_path: recipePath || null, policy: policy === "current" ? null : policy,
    optimize_types: optimizeTypes, dry_run: action === "files", full_plan: action === "full",
    report_path: reportPath || null, report_format: reportPath ? reportFormat : null,
    stream, chunk_size: stream ? Number(chunkSize) || 100000 : null,
  });

  const act = async (action: BatchAction) => {
    setLoading(true); setError(null);
    if (action !== "execute") { batchSessionJobId = null; setJobId(null); setJobStatus(null); setPlan(null); }
    try {
      if (action === "execute") {
        const created = await executeWorkflow("batch", payload(action));
        batchSessionJobId = created.job_id; setJobId(created.job_id); setJobStatus(created.status); setPlan(null);
      } else setPlan(await planWorkflow("batch", payload(action)));
    } catch (nextError) {
      setError(nextError);
      if (action !== "execute") setPlan(null);
      if (action === "execute") void getActiveJob("batch").then(({ data }) => {
        if (!data) return; batchSessionJobId = data.job_id; setJobId(data.job_id); setJobStatus(data.status);
      }).catch(() => undefined);
    } finally { setLoading(false); }
  };
  const updateJob = useCallback((job: JobSnapshot) => { batchSessionJobId = job.job_id; setJobStatus(job.status); }, []);
  const activeJob = Boolean(jobId && !terminalStatuses.has(jobStatus ?? "connecting"));
  const hasDeepOptions = Boolean(recipePath || (policy && policy !== "current"));
  const runAllowed = Boolean(plan?.valid && policy !== "analysis-ready");
  const recipeName = recipePath.replaceAll("\\", "/").split("/").at(-1);
  const reportExtensions = reportFormat === "html"
    ? [".html", ".htm"]
    : reportFormat ? [`.${reportFormat}`] : [".json", ".csv", ".html", ".htm"];

  return (
    <Box className="page-content">
      <WorkflowHeader title="Batch Convert" description="Plan files quickly, or read datasets for explicit recipe and transfer-policy checks before running." />
      <Stack gap="lg">
        <Paper withBorder radius="lg" p="lg"><Stack gap="md">
          <PathPickerField label="Input folder" value={inputPath} onChange={setInputPath} selection="directory" required />
          <PathPickerField label="Output folder" value={outputPath} onChange={setOutputPath} selection="directory" required />
          <Select label="Target format" data={formats} searchable value={targetFormat} onChange={setTargetFormat} />
          <Group><Checkbox label="Include subfolders" checked={recursive} onChange={(event) => setRecursive(event.currentTarget.checked)} /><Checkbox label="Overwrite outputs and report" checked={overwrite} onChange={(event) => setOverwrite(event.currentTarget.checked)} /><Checkbox label="Create output/report directories" checked={createDirs} onChange={(event) => setCreateDirs(event.currentTarget.checked)} /></Group>

          <Paper withBorder radius="md" p="md"><Stack gap="sm">
            <PathPickerField label="Optional portable recipe" description="Select a local version 1 TOML recipe. StatConvert parses it; the recipe cannot control batch output naming." value={recipePath} onChange={(value) => { setRecipePath(value); if (value) setStream(false); }} extensions={[".toml"]} />
            {recipeName && <Text size="sm" c="dimmed">Selected recipe: {recipeName}</Text>}
            <Select label="Optional transfer policy" data={policies} value={policy} onChange={(value) => { setPolicy(value ?? "current"); if (value !== "smallest-types") setOptimizeTypes(false); if (value && value !== "current") setStream(false); }} />
            {policy === "smallest-types" && <Checkbox label="Apply exact smallest-type optimization" description="Applies only exact lossless decisions; manual, protected, and ambiguous columns stay unchanged." checked={optimizeTypes} onChange={(event) => setOptimizeTypes(event.currentTarget.checked)} />}
            {policy === "analysis-ready" && <Alert color="blue">Analysis-ready is plan-only. Run is disabled for this policy.</Alert>}
          </Stack></Paper>

          <Accordion variant="separated"><Accordion.Item value="advanced"><Accordion.Control icon={<IconRoute size={18} />}>Advanced batch options</Accordion.Control><Accordion.Panel><Stack gap="md">
            <Select label="Workbook and container objects" description="Automatic pauses when containers are detected so no sheet or object is chosen silently." data={[{ value: "automatic", label: "Ask when containers are found" }, { value: "all", label: "Convert all supported objects" }, { value: "specific", label: "Convert one specific object in every file" }]} value={objectMode} onChange={setObjectMode} />
            {objectMode === "specific" && <TextInput label="Object name or zero-based index" value={objectSelector} onChange={(event) => setObjectSelector(event.currentTarget.value)} required />}
            <Group><Checkbox label="Preserve input folder structure" checked={preserveStructure} onChange={(event) => setPreserveStructure(event.currentTarget.checked)} /><Checkbox label="Stop after first failure" checked={failFast} onChange={(event) => setFailFast(event.currentTarget.checked)} /><Checkbox label="Allow filesystem-plan blockers" description="Execution keeps blocked items visible and processes eligible items. Full-plan blockers always prevent Run." checked={allowBlocked} onChange={(event) => setAllowBlocked(event.currentTarget.checked)} /></Group>
            <NumberInput label="Workers" description="Leave empty to use StatConvert’s default. Set a number to control parallel batch workers where supported." min={1} allowDecimal={false} value={workers} onChange={setWorkers} placeholder="Automatic" />
            <Group grow align="start"><Textarea label="Include patterns" description="Comma or line separated globs." value={patterns} onChange={(event) => setPatterns(event.currentTarget.value)} /><Textarea label="Exclude patterns" description="Comma or line separated globs." value={excludePatterns} onChange={(event) => setExcludePatterns(event.currentTarget.value)} /></Group>
            <Group grow align="start"><PathPickerField label="Optional explicit batch report" description="Written only when this path is supplied; normal overwrite/create-directory choices also apply." value={reportPath} onChange={setReportPath} selection="save_file" extensions={reportExtensions} /><Select label="Report format" data={reportFormats} value={reportFormat} onChange={setReportFormat} disabled={!reportPath} /></Group>
            <Checkbox label="Stream supported text formats" checked={stream} onChange={(event) => setStream(event.currentTarget.checked)} disabled={objectMode !== "automatic" || hasDeepOptions} />
            {stream && <NumberInput label="Chunk size" min={1} value={chunkSize} onChange={setChunkSize} />}
          </Stack></Accordion.Panel></Accordion.Item></Accordion>

          <Alert color="blue" title="Lightweight file planning">Plan files checks files, paths, conflicts, and directories. It does not read datasets, inspect schemas, check recipe compatibility, or run transfer policies.</Alert>
          {hasDeepOptions && <Alert color="blue" title="Full planning">Full plan reads selected datasets, checks recipe compatibility and policy decisions per item, and scans complete columns for policy planning. It writes no data outputs or sidecars; an explicit report path is the only planned write.</Alert>}
          <Group justify="flex-end">
            <Button variant="light" leftSection={<IconRoute size={17} />} onClick={() => void act("files")} loading={loading} disabled={activeJob || !inputPath || !outputPath || !targetFormat || Boolean(policy && policy !== "current")}>Plan files</Button>
            {hasDeepOptions && <Button variant="light" leftSection={<IconRoute size={17} />} onClick={() => void act("full")} loading={loading} disabled={activeJob || !inputPath || !outputPath || !targetFormat}>Full plan</Button>}
            <Button leftSection={<IconPlayerPlay size={17} />} onClick={() => void act("execute")} loading={loading} disabled={activeJob || !runAllowed}>Run batch</Button>
          </Group>
        </Stack></Paper>
        <ErrorAlert error={error} />
        {plan?.warnings.map((warning) => <Alert key={warning} color="orange" icon={<IconAlertTriangle size={18} />}>{warning}</Alert>)}
        {plan && <CommandPreview command={plan.command} />}
        {plan && <BatchResultView data={plan.details} title={plan.details.phase === "full_plan" ? "Full plan" : "Lightweight file plan"} />}
        <JobProgress jobId={jobId} onUpdate={updateJob} />
      </Stack>
    </Box>
  );
}
