import { useState } from "react";
import { Alert, Box, Button, Checkbox, Code, Group, Paper, Stack, Text, Title } from "@mantine/core";
import { IconFilePlus, IconHelpCircle, IconPackages, IconPlayerPlay } from "@tabler/icons-react";

import { CommandPreview } from "../components/CommandPreview";
import { ErrorAlert } from "../components/ErrorAlert";
import { JobProgress } from "../components/JobProgress";
import { PathPickerField } from "../components/PathPickerField";
import { ResultView } from "../components/ResultView";
import { WorkflowHeader } from "../components/WorkflowHeader";
import { executeWorkflow, getJson, planWorkflow, postJson } from "../lib/api";
import type { DataResponse, PlanResponse } from "../lib/types";

interface ManifestExample extends Record<string, unknown> {
  csv: string;
  required_columns: string[];
  optional_columns: string[];
  notes: string[];
}

interface StarterResult extends Record<string, unknown> {
  output_path: string;
  rows: number;
}

export function CollectPage() {
  const [manifestPath, setManifestPath] = useState("");
  const [outputPath, setOutputPath] = useState("");
  const [baseDir, setBaseDir] = useState("");
  const [overwrite, setOverwrite] = useState(false);
  const [createDirs, setCreateDirs] = useState(false);
  const [validateInputs, setValidateInputs] = useState(false);
  const [strict, setStrict] = useState(false);
  const [showExample, setShowExample] = useState(false);
  const [manifestExample, setManifestExample] = useState<ManifestExample | null>(null);
  const [starterPath, setStarterPath] = useState("");
  const [starterOverwrite, setStarterOverwrite] = useState(false);
  const [starterCreateDirs, setStarterCreateDirs] = useState(false);
  const [starterResult, setStarterResult] = useState<StarterResult | null>(null);
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const payload = (): Record<string, unknown> => ({ manifest_path: manifestPath, output_path: outputPath, base_dir: baseDir || null, overwrite, create_dirs: createDirs, validate_inputs: validateInputs, strict_validation: strict });
  const check = async () => { setLoading(true); setError(null); setJobId(null); try { setPlan(await planWorkflow("collect", payload())); } catch (nextError) { setError(nextError); setPlan(null); } finally { setLoading(false); } };
  const run = async () => { setLoading(true); setError(null); setJobId(null); try { const created = await executeWorkflow("collect", payload()); setJobId(created.job_id); setPlan(null); } catch (nextError) { setError(nextError); } finally { setLoading(false); } };
  const toggleExample = async () => {
    const next = !showExample;
    setShowExample(next);
    if (!next || manifestExample) return;
    setError(null);
    try { setManifestExample((await getJson<DataResponse<ManifestExample>>("/api/collect/manifest-example")).data); }
    catch (nextError) { setError(nextError); }
  };
  const createStarter = async () => {
    setLoading(true); setError(null); setStarterResult(null);
    try {
      const response = await postJson<DataResponse<StarterResult>>("/api/collect/create-manifest", { output_path: starterPath, overwrite: starterOverwrite, create_dirs: starterCreateDirs });
      setStarterResult(response.data); setManifestPath(response.data.output_path);
    } catch (nextError) { setError(nextError); }
    finally { setLoading(false); }
  };
  return (
    <Box className="page-content">
      <WorkflowHeader title="Collect" description="Plan and write one manifest-selected, multi-object XLSX or ODS container through the existing collection service." badge="1.0.0e" />
      <Stack gap="lg">
        <Alert color="blue" icon={<IconHelpCircle size={18} />} title="What is a collection manifest?">
          <Text size="sm">Collect uses a CSV manifest to list input files, optional workbook/object selections, and the output worksheet/object name for each item. Create or edit the manifest first, select it below, then use Plan collection to validate the manifest, inputs, object choices, and output safety.</Text>
          <Button mt="sm" size="xs" variant="light" onClick={() => void toggleExample()}>{showExample ? "Hide manifest example" : "Show manifest example"}</Button>
        </Alert>
        {showExample && <Paper withBorder radius="lg" p="lg"><Stack gap="md">
          <div><Title order={3}>Collection manifest example</Title><Text size="sm" c="dimmed">Only <Code>input_file</Code> is required. Relative paths resolve from the manifest directory unless you select a base directory.</Text></div>
          {manifestExample ? <><Code block>{manifestExample.csv}</Code><Text size="sm">Optional columns: {manifestExample.optional_columns.join(", ")}</Text>{manifestExample.notes.map((note) => <Text size="sm" key={note}>• {note}</Text>)}</> : <Text size="sm" c="dimmed">Loading the current manifest example…</Text>}
          <Title order={4}>Create starter manifest</Title>
          <PathPickerField label="Starter manifest path" value={starterPath} onChange={setStarterPath} selection="save_file" extensions={[".csv"]} />
          <Group><Checkbox label="Overwrite existing starter" checked={starterOverwrite} onChange={(event) => setStarterOverwrite(event.currentTarget.checked)} /><Checkbox label="Create missing directories" checked={starterCreateDirs} onChange={(event) => setStarterCreateDirs(event.currentTarget.checked)} /></Group>
          <Group justify="space-between"><Text size="sm" c={starterResult ? "green" : "dimmed"}>{starterResult ? `Starter manifest written: ${starterResult.output_path}` : "The starter contains example rows; replace them with your input files before planning."}</Text><Button leftSection={<IconFilePlus size={17} />} onClick={() => void createStarter()} disabled={!starterPath} loading={loading}>Create starter manifest</Button></Group>
        </Stack></Paper>}
        <Paper withBorder radius="lg" p="lg"><Stack gap="md">
          <PathPickerField label="Object manifest" value={manifestPath} onChange={setManifestPath} extensions={[".csv"]} required />
          <PathPickerField label="Output workbook" value={outputPath} onChange={setOutputPath} selection="save_file" extensions={[".xlsx", ".ods"]} required />
          <PathPickerField label="Optional input base directory" description="Relative manifest paths otherwise resolve from the manifest directory." value={baseDir} onChange={setBaseDir} selection="directory" />
          <Group><Checkbox label="Overwrite existing workbook" checked={overwrite} onChange={(event) => setOverwrite(event.currentTarget.checked)} /><Checkbox label="Create missing directories" checked={createDirs} onChange={(event) => setCreateDirs(event.currentTarget.checked)} /><Checkbox label="Validate each input" checked={validateInputs} onChange={(event) => setValidateInputs(event.currentTarget.checked)} /><Checkbox label="Strict validation" checked={strict} onChange={(event) => { setStrict(event.currentTarget.checked); if (event.currentTarget.checked) setValidateInputs(true); }} /></Group>
          <Group justify="flex-end"><Button variant="light" leftSection={<IconPackages size={17} />} onClick={() => void check()} disabled={!manifestPath || !outputPath} loading={loading}>Plan collection</Button><Button leftSection={<IconPlayerPlay size={17} />} onClick={() => void run()} disabled={!plan?.valid} loading={loading}>Run collection</Button></Group>
        </Stack></Paper>
        <ErrorAlert error={error} />
        {plan && <CommandPreview command={plan.command} />}
        {plan && <ResultView data={plan.details} title="Collection workload" />}
        <JobProgress jobId={jobId} />
      </Stack>
    </Box>
  );
}
