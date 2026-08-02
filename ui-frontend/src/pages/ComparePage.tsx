import { useState } from "react";
import { Box, Button, Checkbox, Group, NumberInput, Paper, Stack, TextInput } from "@mantine/core";
import { IconArrowsDiff, IconPlayerPlay } from "@tabler/icons-react";

import { CommandPreview } from "../components/CommandPreview";
import { ErrorAlert } from "../components/ErrorAlert";
import { JobProgress } from "../components/JobProgress";
import { PathPickerField } from "../components/PathPickerField";
import { ResultView } from "../components/ResultView";
import { WorkflowHeader } from "../components/WorkflowHeader";
import { executeWorkflow, planWorkflow } from "../lib/api";
import type { PlanResponse } from "../lib/types";

const list = (value: string) => value.split(",").map((item) => item.trim()).filter(Boolean);

export function ComparePage() {
  const [leftPath, setLeftPath] = useState("");
  const [rightPath, setRightPath] = useState("");
  const [leftObject, setLeftObject] = useState("");
  const [rightObject, setRightObject] = useState("");
  const [columns, setColumns] = useState("");
  const [ignoreColumns, setIgnoreColumns] = useState("");
  const [keyColumns, setKeyColumns] = useState("");
  const [compareValues, setCompareValues] = useState(true);
  const [sampleSize, setSampleSize] = useState<number | string>(100);
  const [numericTolerance, setNumericTolerance] = useState<number | string>(0);
  const [maxDifferences, setMaxDifferences] = useState<number | string>(50);
  const [strict, setStrict] = useState(false);
  const [reportPath, setReportPath] = useState("");
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  const payload = (): Record<string, unknown> => ({
    left_path: leftPath,
    right_path: rightPath,
    left_object_selector: leftObject || null,
    right_object_selector: rightObject || null,
    compare_values: compareValues,
    sample_size: compareValues && Number(sampleSize) > 0 ? Number(sampleSize) : null,
    columns: columns ? list(columns) : null,
    ignore_columns: list(ignoreColumns),
    key_columns: list(keyColumns),
    numeric_tolerance: Number(numericTolerance) || 0,
    max_differences: Number(maxDifferences) || 50,
    strict,
    report_path: reportPath || null,
  });

  const planComparison = async () => {
    setLoading(true); setError(null);
    setJobId(null);
    try { setPlan(await planWorkflow("compare", payload())); }
    catch (nextError) { setError(nextError); setPlan(null); }
    finally { setLoading(false); }
  };
  const run = async () => {
    setLoading(true); setError(null);
    setJobId(null);
    try { const created = await executeWorkflow("compare", payload()); setJobId(created.job_id); setPlan(null); }
    catch (nextError) { setError(nextError); }
    finally { setLoading(false); }
  };

  return (
    <Box className="page-content">
      <WorkflowHeader title="Compare" description="Compare structure, metadata, and bounded value differences through StatConvert’s existing comparison engine." badge="1.0.0e" />
      <Stack gap="lg">
        <Paper withBorder radius="lg" p="lg"><Stack gap="md">
          <Group grow align="start">
            <PathPickerField label="Left dataset" value={leftPath} onChange={setLeftPath} required />
            <PathPickerField label="Right dataset" value={rightPath} onChange={setRightPath} required />
          </Group>
          <Group grow><TextInput label="Left object" value={leftObject} onChange={(event) => setLeftObject(event.currentTarget.value)} /><TextInput label="Right object" value={rightObject} onChange={(event) => setRightObject(event.currentTarget.value)} /></Group>
          <Group grow><TextInput label="Columns" description="Comma-separated selection." value={columns} onChange={(event) => setColumns(event.currentTarget.value)} /><TextInput label="Ignore columns" value={ignoreColumns} onChange={(event) => setIgnoreColumns(event.currentTarget.value)} /><TextInput label="Key columns" value={keyColumns} onChange={(event) => setKeyColumns(event.currentTarget.value)} /></Group>
          <Group grow><NumberInput label="Sample rows" min={1} value={sampleSize} onChange={setSampleSize} disabled={!compareValues} /><NumberInput label="Numeric tolerance" min={0} value={numericTolerance} onChange={setNumericTolerance} /><NumberInput label="Maximum detailed differences" min={1} max={1000} value={maxDifferences} onChange={setMaxDifferences} /></Group>
          <PathPickerField label="Optional comparison report" value={reportPath} onChange={setReportPath} selection="save_file" extensions={[".json", ".csv", ".html"]} />
          <Group><Checkbox label="Compare values" checked={compareValues} onChange={(event) => setCompareValues(event.currentTarget.checked)} /><Checkbox label="Strict warning policy" checked={strict} onChange={(event) => setStrict(event.currentTarget.checked)} /></Group>
          <Group justify="flex-end"><Button variant="light" leftSection={<IconArrowsDiff size={17} />} onClick={() => void planComparison()} disabled={!leftPath || !rightPath} loading={loading}>Check comparison</Button><Button leftSection={<IconPlayerPlay size={17} />} onClick={() => void run()} disabled={!plan?.valid} loading={loading}>Run comparison</Button></Group>
        </Stack></Paper>
        <ErrorAlert error={error} />
        {plan && <CommandPreview command={plan.command} />}
        {plan && <ResultView data={plan.details} title="Comparison plan" />}
        <JobProgress jobId={jobId} />
      </Stack>
    </Box>
  );
}
