import { useState } from "react";
import {
  Box,
  Button,
  Checkbox,
  Group,
  NumberInput,
  Paper,
  Select,
  Stack,
  TextInput,
} from "@mantine/core";
import { IconPlayerPlay, IconShieldCheck } from "@tabler/icons-react";

import { CommandPreview } from "../components/CommandPreview";
import { ErrorAlert } from "../components/ErrorAlert";
import { JobProgress } from "../components/JobProgress";
import { PathPickerField } from "../components/PathPickerField";
import { ResultView } from "../components/ResultView";
import { WorkflowHeader } from "../components/WorkflowHeader";
import { executeWorkflow, planWorkflow } from "../lib/api";
import type { PlanResponse } from "../lib/types";

const formats = ["csv", "json", "jsonl", "parquet", "feather", "xlsx", "ods", "sav", "dta", "rds"];

export function ValidatePage() {
  const [inputPath, setInputPath] = useState("");
  const [objectSelector, setObjectSelector] = useState("");
  const [targetFormat, setTargetFormat] = useState<string | null>(null);
  const [schemaContract, setSchemaContract] = useState("");
  const [strict, setStrict] = useState(false);
  const [stream, setStream] = useState(false);
  const [chunkSize, setChunkSize] = useState<number | string>(100000);
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  const payload = (): Record<string, unknown> => ({
    path: inputPath,
    object_selector: objectSelector || null,
    target_format: targetFormat,
    strict,
    schema_contract: schemaContract || null,
    stream,
    chunk_size: stream ? Number(chunkSize) || 100000 : null,
  });

  const planValidation = async () => {
    setLoading(true);
    setError(null);
    setJobId(null);
    try {
      setPlan(await planWorkflow("validate", payload()));
    } catch (nextError) {
      setError(nextError);
      setPlan(null);
    } finally {
      setLoading(false);
    }
  };

  const runValidation = async () => {
    setLoading(true);
    setError(null);
    try {
      const created = await executeWorkflow("validate", payload());
      setJobId(created.job_id);
      setPlan(null);
    } catch (nextError) {
      setError(nextError);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box className="page-content">
      <WorkflowHeader
        title="Validate"
        description="Check data quality, target readiness, and optional TOML schema contracts with the existing validation policy."
      />
      <Stack gap="lg">
        <Paper withBorder radius="lg" p="lg">
          <Stack gap="md">
            <PathPickerField label="Input path" value={inputPath} onChange={setInputPath} required />
            <Group grow align="start">
              <TextInput label="Object selector" value={objectSelector} onChange={(event) => setObjectSelector(event.currentTarget.value)} disabled={stream} />
              <Select label="Target-readiness format" data={formats} clearable searchable value={targetFormat} onChange={setTargetFormat} disabled={stream} />
            </Group>
            <PathPickerField label="Schema contract path" description={stream ? "Required for streaming validation." : "Optional version 1 TOML contract."} value={schemaContract} onChange={setSchemaContract} extensions={[".toml"]} />
            <Group>
              <Checkbox label="Strict warning policy" checked={strict} onChange={(event) => setStrict(event.currentTarget.checked)} />
              <Checkbox label="Stream CSV/JSONL/NDJSON" checked={stream} onChange={(event) => setStream(event.currentTarget.checked)} />
            </Group>
            {stream && <NumberInput label="Chunk size" min={1} value={chunkSize} onChange={setChunkSize} />}
            <Group justify="flex-end">
              <Button variant="light" leftSection={<IconShieldCheck size={17} />} onClick={() => void planValidation()} loading={loading} disabled={!inputPath}>Check options</Button>
              <Button leftSection={<IconPlayerPlay size={17} />} onClick={() => void runValidation()} loading={loading} disabled={!plan?.valid}>Run validation</Button>
            </Group>
          </Stack>
        </Paper>
        <ErrorAlert error={error} />
        {plan && <CommandPreview command={plan.command} />}
        {plan && <ResultView data={plan.details} title="Validation plan" />}
        <JobProgress jobId={jobId} />
      </Stack>
    </Box>
  );
}
