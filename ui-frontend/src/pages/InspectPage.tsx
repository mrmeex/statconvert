import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActionIcon, Box, Button, Checkbox, Group, Loader, NumberInput, Paper, Select, Stack,
  Tabs, TextInput, Tooltip,
} from "@mantine/core";
import { IconFileExport, IconRefresh } from "@tabler/icons-react";

import { CommandPreview } from "../components/CommandPreview";
import { ErrorAlert } from "../components/ErrorAlert";
import { InspectResultView } from "../components/InspectResultView";
import { MetadataSidecarEditor } from "../components/MetadataSidecarEditor";
import { PathPickerField } from "../components/PathPickerField";
import { ResultView } from "../components/ResultView";
import { WorkflowHeader } from "../components/WorkflowHeader";
import { postJson } from "../lib/api";
import type { InspectResponse } from "../lib/types";

const tabs = [
  ["info", "Overview"], ["peek", "Preview"], ["schema", "Schema"],
  ["labels", "Labels"], ["metadata", "Metadata"], ["summary", "Summary"],
  ["describe", "Describe"], ["frequencies", "Frequencies"],
  ["missing", "Missing"], ["objects", "Objects"],
] as const;

interface CachedInspect { data: Record<string, unknown>; command: string }

const scriptFormats = [
  { value: "r", label: "R", extension: ".R" },
  { value: "spss", label: "SPSS", extension: ".sps" },
  { value: "stata", label: "Stata", extension: ".do" },
] as const;

export function InspectPage() {
  const [path, setPath] = useState("");
  const [objectSelector, setObjectSelector] = useState("");
  const [activeTab, setActiveTab] = useState("info");
  const [rows, setRows] = useState<number | string>(10);
  const [recursive, setRecursive] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [command, setCommand] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const [scriptFormat, setScriptFormat] = useState<string | null>("r");
  const [scriptOutputPath, setScriptOutputPath] = useState("");
  const [overwriteScript, setOverwriteScript] = useState(false);
  const [scriptResult, setScriptResult] = useState<InspectResponse | null>(null);
  const [scriptError, setScriptError] = useState<unknown>(null);
  const [scriptLoading, setScriptLoading] = useState(false);
  const cache = useRef(new Map<string, CachedInspect>());
  const requestSequence = useRef(0);
  const tabLabel = useMemo(() => tabs.find(([value]) => value === activeTab)?.[1] ?? "Inspect", [activeTab]);
  const cacheKey = `${path}\0${objectSelector}\0${activeTab}\0${rows}\0${recursive}`;

  const inspect = useCallback(async (force = false) => {
    if (!path) return;
    const key = `${path}\0${objectSelector}\0${activeTab}\0${rows}\0${recursive}`;
    const cached = cache.current.get(key);
    if (cached && !force) {
      setResult(cached.data);
      setCommand(cached.command);
      setError(null);
      return;
    }
    const sequence = ++requestSequence.current;
    setLoading(true);
    setError(null);
    try {
      const payload: Record<string, unknown> = { path, object_selector: objectSelector || null };
      if (activeTab === "peek") payload.rows = Number(rows) || 10;
      if (activeTab === "objects") { delete payload.object_selector; payload.recursive = recursive; }
      if (activeTab === "frequencies") { payload.top = 20; payload.include_missing = false; payload.max_unique = 100; }
      const response = await postJson<InspectResponse>(`/api/inspect/${activeTab}`, payload);
      if (sequence !== requestSequence.current) return;
      const value = { data: response.data, command: response.command ?? "" };
      cache.current.set(key, value);
      setResult(value.data);
      setCommand(value.command);
    } catch (nextError) {
      if (sequence !== requestSequence.current) return;
      setError(nextError);
      setResult(null);
      setCommand("");
    } finally {
      if (sequence === requestSequence.current) setLoading(false);
    }
  }, [activeTab, objectSelector, path, recursive, rows]);

  useEffect(() => {
    if (!path) { setResult(null); setCommand(""); return; }
    const timer = window.setTimeout(() => void inspect(), 400);
    return () => window.clearTimeout(timer);
  }, [cacheKey, inspect, path]);

  const exportMetadataScript = async () => {
    if (!path || !scriptOutputPath || !scriptFormat) return;
    setScriptLoading(true);
    setScriptError(null);
    try {
      setScriptResult(await postJson<InspectResponse>("/api/inspect/metadata/export-script", {
        path,
        object_selector: objectSelector || null,
        output_path: scriptOutputPath,
        format: scriptFormat,
        overwrite: overwriteScript,
      }));
    } catch (nextError) {
      setScriptError(nextError);
      setScriptResult(null);
    } finally {
      setScriptLoading(false);
    }
  };

  const scriptExtension = scriptFormats.find((format) => format.value === scriptFormat)?.extension ?? ".R";

  return (
    <Box className="page-content">
      <WorkflowHeader title="Inspect" description="Explore one explicit local dataset path through bounded previews, metadata, profiles, and object discovery." />
      <Stack gap="lg">
        <Paper withBorder radius="lg" p="lg">
          <Stack gap="md">
            <PathPickerField
              label="Input path"
              description={activeTab === "objects" ? "Browse a dataset file or choose a folder for bounded object discovery." : "Choose one local dataset file."}
              placeholder="D:\\data\\survey.sav"
              value={path}
              onChange={setPath}
              allowDirectorySelection={activeTab === "objects"}
              required
            />
            <TextInput label="Object selector" description="Optional workbook sheet, R object, or other container object." value={objectSelector} onChange={(event) => setObjectSelector(event.currentTarget.value)} />
          </Stack>
        </Paper>

        <Group align="center" gap="sm" wrap="nowrap">
          <Tabs value={activeTab} onChange={(value) => setActiveTab(value ?? "info")} variant="pills" style={{ flex: 1, minWidth: 0 }}>
            <Tabs.List className="inspect-tabs">{tabs.map(([value, label]) => <Tabs.Tab key={value} value={value}>{label}</Tabs.Tab>)}</Tabs.List>
          </Tabs>
          <Tooltip label={`Refresh ${tabLabel}`}>
            <ActionIcon size="lg" variant="light" onClick={() => void inspect(true)} disabled={!path || loading} aria-label={`Refresh ${tabLabel}`}>
              {loading ? <Loader size={17} /> : <IconRefresh size={19} />}
            </ActionIcon>
          </Tooltip>
        </Group>

        {(activeTab === "peek" || activeTab === "objects") && (
          <Group className="inspect-options">
            {activeTab === "peek" && <NumberInput label="Rows" min={1} max={100} value={rows} onChange={setRows} w={120} />}
            {activeTab === "objects" && <Checkbox label="Include subfolders" checked={recursive} onChange={(event) => setRecursive(event.currentTarget.checked)} />}
          </Group>
        )}
        <ErrorAlert error={error} />
        {command && <CommandPreview command={command} />}
        <InspectResultView tab={activeTab} data={result} title={tabLabel} />
        {activeTab === "metadata" && (
          <MetadataSidecarEditor path={path} objectSelector={objectSelector} metadata={result} />
        )}
        {activeTab === "metadata" && (
          <Paper withBorder radius="lg" p="lg">
            <Stack gap="md">
              <Group grow align="start">
                <Select
                  label="Script format"
                  description="Uses the existing metadata helper-script exporter."
                  data={scriptFormats.map(({ value, label }) => ({ value, label }))}
                  value={scriptFormat}
                  onChange={(value) => { setScriptFormat(value); setScriptOutputPath(""); setScriptResult(null); }}
                  allowDeselect={false}
                />
                <PathPickerField
                  label="Script output path"
                  description={`Choose a ${scriptExtension} file in an existing local folder.`}
                  value={scriptOutputPath}
                  onChange={setScriptOutputPath}
                  selection="save_file"
                  extensions={[scriptExtension]}
                  required
                />
              </Group>
              <Group justify="space-between">
                <Checkbox label="Replace an existing script" checked={overwriteScript} onChange={(event) => setOverwriteScript(event.currentTarget.checked)} />
                <Button leftSection={<IconFileExport size={17} />} onClick={() => void exportMetadataScript()} loading={scriptLoading} disabled={!path || !scriptOutputPath || !scriptFormat}>
                  Export metadata script
                </Button>
              </Group>
              <ErrorAlert error={scriptError} />
              {scriptResult?.command && <CommandPreview command={scriptResult.command} />}
              {scriptResult && <ResultView data={scriptResult.data} title="Metadata script exported" />}
            </Stack>
          </Paper>
        )}
      </Stack>
    </Box>
  );
}
