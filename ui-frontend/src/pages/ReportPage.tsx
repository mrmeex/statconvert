import { useState } from "react";
import { Alert, Box, Button, Checkbox, Group, NumberInput, Paper, Select, Stack, TextInput } from "@mantine/core";
import { IconAlertTriangle, IconFileAnalytics, IconPlayerPlay } from "@tabler/icons-react";

import { CommandPreview } from "../components/CommandPreview";
import { ErrorAlert } from "../components/ErrorAlert";
import { JobProgress } from "../components/JobProgress";
import { PathPickerField } from "../components/PathPickerField";
import { ResultView } from "../components/ResultView";
import { WorkflowHeader } from "../components/WorkflowHeader";
import { executeWorkflow, planWorkflow } from "../lib/api";
import { formatOptions } from "../lib/formats";
import { ensureOutputExtension, outputExtensionWarning, updateGeneratedExtension } from "../lib/outputPath";
import type { PlanResponse } from "../lib/types";

const list = (value: string) => value.split(",").map((item) => item.trim()).filter(Boolean);
const reportFormats = formatOptions(["html", "json", "csv"]);

export function ReportPage() {
  const [inputPath, setInputPath] = useState("");
  const [outputPath, setOutputPath] = useState("");
  const [outputAutoExtended, setOutputAutoExtended] = useState(false);
  const [objectSelector, setObjectSelector] = useState("");
  const [schemaContract, setSchemaContract] = useState("");
  const [outputFormat, setOutputFormat] = useState<string | null>("html");
  const [preset, setPreset] = useState<string | null>("quick");
  const [columns, setColumns] = useState("");
  const [frequencies, setFrequencies] = useState(false);
  const [strict, setStrict] = useState(false);
  const [overwrite, setOverwrite] = useState(false);
  const [createDirs, setCreateDirs] = useState(false);
  const [maxRows, setMaxRows] = useState<number | string>(1000);
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  const payload = (): Record<string, unknown> => ({
    input_path: inputPath,
    output_path: ensureOutputExtension(outputPath, outputFormat),
    object_selector: objectSelector || null,
    output_format: outputFormat,
    preset,
    frequencies,
    columns: columns ? list(columns) : null,
    max_table_rows: Number(maxRows) || 1000,
    strict_validation: strict,
    schema_contract: schemaContract || null,
    overwrite,
    create_dirs: createDirs,
  });
  const check = async () => { setLoading(true); setError(null); setJobId(null); try { setPlan(await planWorkflow("report", payload())); } catch (nextError) { setError(nextError); setPlan(null); } finally { setLoading(false); } };
  const run = async () => { setLoading(true); setError(null); setJobId(null); try { const created = await executeWorkflow("report", payload()); setJobId(created.job_id); setPlan(null); } catch (nextError) { setError(nextError); } finally { setLoading(false); } };
  const commitOutputPath = (value: string, generatedExtension = false) => {
    const next = ensureOutputExtension(value, outputFormat);
    setOutputPath(next);
    setOutputAutoExtended(generatedExtension || next !== value);
  };
  const changeOutputFormat = (value: string | null) => {
    if (outputAutoExtended) setOutputPath(updateGeneratedExtension(outputPath, outputFormat, value));
    else {
      const next = ensureOutputExtension(outputPath, value);
      if (next !== outputPath) { setOutputPath(next); setOutputAutoExtended(true); }
    }
    setOutputFormat(value);
  };
  const extensionWarning = outputExtensionWarning(outputPath, outputFormat);
  const reportExtensionWarning = extensionWarning?.replace(
    "choose a matching format or path before planning.",
    "the report content will use the selected format.",
  );

  return (
    <Box className="page-content">
      <WorkflowHeader title="Report" description="Generate an existing JSON, CSV, or static HTML dataset report with bounded tables and output safety." />
      <Stack gap="lg">
        <Paper withBorder radius="lg" p="lg"><Stack gap="md">
          <PathPickerField label="Input dataset" value={inputPath} onChange={setInputPath} required />
          <PathPickerField label="Output report" value={outputPath} onChange={(value) => { setOutputPath(value); setOutputAutoExtended(false); }} onCommit={commitOutputPath} selection="save_file" extensions={outputFormat ? [`.${outputFormat}`] : []} required />
          <Group grow><TextInput label="Object selector" value={objectSelector} onChange={(event) => setObjectSelector(event.currentTarget.value)} /><Select label="Output format" data={reportFormats} value={outputFormat} onChange={changeOutputFormat} /><Select label="Preset" data={["quick", "full", "validation", "metadata"]} clearable value={preset} onChange={setPreset} /></Group>
          <PathPickerField label="Optional schema contract" value={schemaContract} onChange={setSchemaContract} extensions={[".toml"]} />
          <Group grow><TextInput label="Profile columns" description="Comma-separated; blank uses defaults." value={columns} onChange={(event) => setColumns(event.currentTarget.value)} /><NumberInput label="Maximum rows per rendered table" min={1} max={100000} value={maxRows} onChange={setMaxRows} /></Group>
          <Group><Checkbox label="Include frequency tables" checked={frequencies} onChange={(event) => setFrequencies(event.currentTarget.checked)} /><Checkbox label="Strict validation" checked={strict} onChange={(event) => setStrict(event.currentTarget.checked)} /><Checkbox label="Overwrite existing report" checked={overwrite} onChange={(event) => setOverwrite(event.currentTarget.checked)} /><Checkbox label="Create missing directories" checked={createDirs} onChange={(event) => setCreateDirs(event.currentTarget.checked)} /></Group>
          {reportExtensionWarning && <Alert color="orange" icon={<IconAlertTriangle size={18} />}>{reportExtensionWarning}</Alert>}
          <Group justify="flex-end"><Button variant="light" leftSection={<IconFileAnalytics size={17} />} onClick={() => void check()} disabled={!inputPath || !outputPath} loading={loading}>Check report</Button><Button leftSection={<IconPlayerPlay size={17} />} onClick={() => void run()} disabled={!plan?.valid} loading={loading}>Generate report</Button></Group>
        </Stack></Paper>
        <ErrorAlert error={error} />
        {plan && <CommandPreview command={plan.command} />}
        {plan && <ResultView data={plan.details} title="Report plan" />}
        <JobProgress jobId={jobId} />
      </Stack>
    </Box>
  );
}
