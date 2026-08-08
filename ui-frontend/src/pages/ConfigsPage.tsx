import { useState } from "react";
import {
  Box, Button, Checkbox, Group, Paper, Select, Stack, Textarea,
} from "@mantine/core";
import {
  IconDeviceFloppy, IconFilePlus, IconFolderOpen, IconPlayerPlay, IconShieldCheck,
} from "@tabler/icons-react";

import { CommandPreview } from "../components/CommandPreview";
import { ErrorAlert } from "../components/ErrorAlert";
import { JobProgress } from "../components/JobProgress";
import { PathPickerField } from "../components/PathPickerField";
import { ResultView } from "../components/ResultView";
import { WorkflowHeader } from "../components/WorkflowHeader";
import { postJson } from "../lib/api";
import type { ConfigData, DataResponse, JobCreated } from "../lib/types";

const commands = ["convert", "transform", "batch", "compare", "validate", "report", "collect"];

export function ConfigsPage() {
  const [configPath, setConfigPath] = useState("");
  const [toml, setToml] = useState("");
  const [starterCommand, setStarterCommand] = useState<string | null>("convert");
  const [overwrite, setOverwrite] = useState(false);
  const [createDirs, setCreateDirs] = useState(false);
  const [result, setResult] = useState<ConfigData | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  const perform = async (operation: () => Promise<DataResponse<ConfigData>>) => {
    setLoading(true);
    setError(null);
    setJobId(null);
    try {
      const response = await operation();
      setResult(response.data);
      if (typeof response.data.toml === "string") setToml(response.data.toml);
    } catch (nextError) {
      setError(nextError);
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  const createStarter = () => perform(() => postJson("/api/config/init", {
    command: starterCommand,
  }));
  const load = () => perform(() => postJson("/api/config/load", { config_path: configPath }));
  const validate = () => perform(() => postJson("/api/config/validate", {
    config_path: configPath || null,
    toml_text: toml,
  }));
  const save = () => perform(() => postJson("/api/config/export", {
    output_path: configPath,
    toml_text: toml,
    overwrite,
    create_dirs: createDirs,
  }));
  const run = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    setJobId(null);
    try {
      const created = await postJson<JobCreated>("/api/config/run", {
        config_path: configPath || null,
        toml_text: toml,
      });
      setJobId(created.job_id);
    } catch (nextError) {
      setError(nextError);
    } finally {
      setLoading(false);
    }
  };

  const command = result?.cli_command as string | undefined
    ?? `statconvert config ${result?.valid ? "validate" : "run"} ${configPath || "<saved-workflow.toml>"}`;
  const resultSummary = result
    ? Object.fromEntries(Object.entries(result).filter(([key]) => key !== "cli_command"))
    : null;

  return (
    <Box className="page-content">
      <WorkflowHeader title="Configs" description="Create, load, edit, validate, save, and run existing StatConvert TOML workflows." />
      <Stack gap="lg">
        <Paper withBorder radius="lg" p="lg">
          <Stack gap="md">
            <Group grow align="end">
              <Select label="Starter workflow" data={commands} value={starterCommand} onChange={setStarterCommand} />
              <Button variant="light" leftSection={<IconFilePlus size={17} />} onClick={() => void createStarter()} loading={loading}>Create starter</Button>
            </Group>
            <PathPickerField label="Config path" value={configPath} onChange={setConfigPath} extensions={[".toml"]} selection="save_file" />
            <Textarea label="Workflow TOML" description="Paste Transform TOML or edit any supported workflow. Validation always uses the existing config schema." value={toml} onChange={(event) => setToml(event.currentTarget.value)} autosize minRows={14} maxRows={28} className="toml-editor" />
            <Group>
              <Checkbox label="Overwrite existing config" checked={overwrite} onChange={(event) => setOverwrite(event.currentTarget.checked)} />
              <Checkbox label="Create missing directories" checked={createDirs} onChange={(event) => setCreateDirs(event.currentTarget.checked)} />
            </Group>
            <Group justify="flex-end">
              <Button variant="default" leftSection={<IconFolderOpen size={17} />} onClick={() => void load()} disabled={!configPath} loading={loading}>Load</Button>
              <Button variant="light" leftSection={<IconShieldCheck size={17} />} onClick={() => void validate()} disabled={!toml} loading={loading}>Validate</Button>
              <Button variant="light" leftSection={<IconDeviceFloppy size={17} />} onClick={() => void save()} disabled={!toml || !configPath} loading={loading}>Save</Button>
              <Button leftSection={<IconPlayerPlay size={17} />} onClick={() => void run()} disabled={!toml} loading={loading}>Run config</Button>
            </Group>
          </Stack>
        </Paper>
        <ErrorAlert error={error} />
        <CommandPreview command={command} />
        {result && <ResultView data={resultSummary} rawData={result} title="Config result" />}
        <JobProgress jobId={jobId} />
      </Stack>
    </Box>
  );
}
