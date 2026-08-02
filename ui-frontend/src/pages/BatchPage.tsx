import { useCallback, useEffect, useState } from "react";
import {
  Accordion, Alert, Box, Button, Checkbox, Group, NumberInput, Paper, Select,
  Stack, Textarea, TextInput,
} from "@mantine/core";
import { IconAlertTriangle, IconPlayerPlay, IconRoute } from "@tabler/icons-react";

import { CommandPreview } from "../components/CommandPreview";
import { ErrorAlert } from "../components/ErrorAlert";
import { JobProgress } from "../components/JobProgress";
import { PathPickerField } from "../components/PathPickerField";
import { ResultView } from "../components/ResultView";
import { WorkflowHeader } from "../components/WorkflowHeader";
import { executeWorkflow, getActiveJob, planWorkflow } from "../lib/api";
import type { JobSnapshot, PlanResponse } from "../lib/types";

const formats = ["csv", "json", "jsonl", "parquet", "feather", "xlsx", "ods", "sav", "dta", "rds"];
const splitPatterns = (value: string) => value.split(/[\n,]+/).map((item) => item.trim()).filter(Boolean);
const terminalStatuses = new Set(["succeeded", "failed", "cancelled"]);
let batchSessionJobId: string | null = null;

export function BatchPage() {
  const [inputPath, setInputPath] = useState(""); const [outputPath, setOutputPath] = useState("");
  const [targetFormat, setTargetFormat] = useState<string | null>("parquet");
  const [recursive, setRecursive] = useState(false); const [overwrite, setOverwrite] = useState(false); const [createDirs, setCreateDirs] = useState(true);
  const [preserveStructure, setPreserveStructure] = useState(true); const [objectMode, setObjectMode] = useState<string | null>("automatic"); const [objectSelector, setObjectSelector] = useState("");
  const [failFast, setFailFast] = useState(false); const [patterns, setPatterns] = useState(""); const [excludePatterns, setExcludePatterns] = useState(""); const [reportPath, setReportPath] = useState("");
  const [workers, setWorkers] = useState<number | string>("");
  const [stream, setStream] = useState(false); const [chunkSize, setChunkSize] = useState<number | string>(100000);
  const [plan, setPlan] = useState<PlanResponse | null>(null); const [jobId, setJobId] = useState<string | null>(() => batchSessionJobId); const [jobStatus, setJobStatus] = useState<string | null>(() => batchSessionJobId ? "connecting" : null); const [error, setError] = useState<unknown>(null); const [loading, setLoading] = useState(false);

  useEffect(() => {
    let mounted = true;
    void getActiveJob("batch").then(({ data }) => {
      if (!mounted || !data) return;
      batchSessionJobId = data.job_id;
      setJobId(data.job_id);
      setJobStatus(data.status);
    }).catch((nextError) => {
      if (mounted && !batchSessionJobId) setError(nextError);
    });
    return () => { mounted = false; };
  }, []);

  const payload = (): Record<string, unknown> => ({
    input_path: inputPath, output_path: outputPath, target_format: targetFormat,
    recursive, overwrite, create_dirs: createDirs, preserve_structure: preserveStructure,
    object_mode: objectMode, object_selector: objectMode === "specific" ? objectSelector || null : null,
    fail_fast: failFast, workers: workers === "" ? null : Number(workers), patterns: splitPatterns(patterns), exclude_patterns: splitPatterns(excludePatterns), report_path: reportPath || null,
    stream, chunk_size: stream ? Number(chunkSize) || 100000 : null,
  });
  const act = async (execute: boolean) => {
    setLoading(true); setError(null);
    if (!execute) {
      batchSessionJobId = null; setJobId(null); setJobStatus(null); setPlan(null);
    }
    try {
      if (execute) {
        const created = await executeWorkflow("batch", payload());
        batchSessionJobId = created.job_id; setJobId(created.job_id); setJobStatus(created.status); setPlan(null);
      } else {
        setPlan(await planWorkflow("batch", payload()));
      }
    } catch (nextError) {
      setError(nextError);
      if (!execute) setPlan(null);
      if (execute) {
        void getActiveJob("batch").then(({ data }) => {
          if (!data) return;
          batchSessionJobId = data.job_id; setJobId(data.job_id); setJobStatus(data.status);
        }).catch(() => undefined);
      }
    } finally { setLoading(false); }
  };
  const updateJob = useCallback((job: JobSnapshot) => {
    batchSessionJobId = job.job_id;
    setJobStatus(job.status);
  }, []);
  const activeJob = Boolean(jobId && !terminalStatuses.has(jobStatus ?? "connecting"));

  return (
    <Box className="page-content">
      <WorkflowHeader title="Batch Convert" description="Discover a folder workload, resolve container choices, and follow each conversion as it runs." />
      <Stack gap="lg">
        <Paper withBorder radius="lg" p="lg"><Stack gap="md">
          <PathPickerField label="Input folder" value={inputPath} onChange={setInputPath} selection="directory" required />
          <PathPickerField label="Output folder" value={outputPath} onChange={setOutputPath} selection="directory" required />
          <Select label="Target format" data={formats} searchable value={targetFormat} onChange={setTargetFormat} />
          <Group><Checkbox label="Include subfolders" checked={recursive} onChange={(event) => setRecursive(event.currentTarget.checked)} /><Checkbox label="Overwrite outputs" checked={overwrite} onChange={(event) => setOverwrite(event.currentTarget.checked)} /><Checkbox label="Create output directories" checked={createDirs} onChange={(event) => setCreateDirs(event.currentTarget.checked)} /></Group>
          <Accordion variant="separated"><Accordion.Item value="advanced"><Accordion.Control icon={<IconRoute size={18} />}>Advanced batch options</Accordion.Control><Accordion.Panel><Stack gap="md">
            <Select label="Workbook and container objects" description="Automatic pauses when containers are detected so no sheet or object is chosen silently." data={[{ value: "automatic", label: "Ask when containers are found" }, { value: "all", label: "Convert all supported objects" }, { value: "specific", label: "Convert one specific object in every file" }]} value={objectMode} onChange={setObjectMode} />
            {objectMode === "specific" && <TextInput label="Object name or zero-based index" value={objectSelector} onChange={(event) => setObjectSelector(event.currentTarget.value)} required />}
            <Group><Checkbox label="Preserve input folder structure" checked={preserveStructure} onChange={(event) => setPreserveStructure(event.currentTarget.checked)} /><Checkbox label="Stop after first failure" checked={failFast} onChange={(event) => setFailFast(event.currentTarget.checked)} /></Group>
            <NumberInput label="Workers" description="Leave empty to use StatConvert’s default. Set a number to control parallel batch workers where supported." min={1} allowDecimal={false} value={workers} onChange={setWorkers} placeholder="Automatic" />
            <Group grow align="start"><Textarea label="Include patterns" description="Comma or line separated globs." value={patterns} onChange={(event) => setPatterns(event.currentTarget.value)} /><Textarea label="Exclude patterns" description="Comma or line separated globs." value={excludePatterns} onChange={(event) => setExcludePatterns(event.currentTarget.value)} /></Group>
            <PathPickerField label="Optional result report" value={reportPath} onChange={setReportPath} selection="save_file" extensions={[".json", ".csv"]} />
            <Checkbox label="Stream supported text formats" checked={stream} onChange={(event) => setStream(event.currentTarget.checked)} disabled={objectMode !== "automatic"} />
            {stream && <NumberInput label="Chunk size" min={1} value={chunkSize} onChange={setChunkSize} />}
          </Stack></Accordion.Panel></Accordion.Item></Accordion>
          <Group justify="flex-end"><Button variant="light" leftSection={<IconRoute size={17} />} onClick={() => void act(false)} loading={loading} disabled={activeJob || !inputPath || !outputPath || !targetFormat}>Plan workload</Button><Button leftSection={<IconPlayerPlay size={17} />} onClick={() => void act(true)} loading={loading} disabled={activeJob || !plan?.valid}>Run batch</Button></Group>
        </Stack></Paper>
        <ErrorAlert error={error} />
        {plan?.warnings.map((warning) => <Alert key={warning} color="orange" icon={<IconAlertTriangle size={18} />}>{warning}</Alert>)}
        {plan && <CommandPreview command={plan.command} />}
        {plan && <ResultView data={plan.details} title="Planned workload" />}
        <JobProgress jobId={jobId} onUpdate={updateJob} />
      </Stack>
    </Box>
  );
}
