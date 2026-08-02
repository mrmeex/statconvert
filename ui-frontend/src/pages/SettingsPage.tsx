import { useEffect, useState } from "react";
import {
  Alert, Badge, Box, Button, Code, Divider, Group, NumberInput, Paper,
  Select, Stack, Switch, Text, TextInput, Title,
} from "@mantine/core";
import { IconAlertTriangle, IconDeviceFloppy, IconRefresh } from "@tabler/icons-react";

import { ErrorAlert } from "../components/ErrorAlert";
import { PathPickerField } from "../components/PathPickerField";
import { getJson, postJson, putJson } from "../lib/api";
import type { DataResponse, SettingsData, UiSettings } from "../lib/types";

export function SettingsPage() {
  const [data, setData] = useState<SettingsData | null>(null);
  const [settings, setSettings] = useState<UiSettings | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setError(null);
    const response = await getJson<DataResponse<SettingsData>>("/api/settings");
    setData(response.data);
    setSettings(response.data.settings);
  };

  useEffect(() => { void load().catch(setError); }, []);

  const save = async () => {
    if (!settings) return;
    setBusy(true); setError(null); setStatus("");
    try {
      const response = await putJson<DataResponse<SettingsData>>("/api/settings", { settings });
      setData(response.data); setSettings(response.data.settings); setStatus("Settings saved.");
    } catch (nextError) { setError(nextError); }
    finally { setBusy(false); }
  };

  const reset = async () => {
    setBusy(true); setError(null); setStatus("");
    try {
      const response = await postJson<DataResponse<SettingsData>>("/api/settings/reset", {});
      setData(response.data); setSettings(response.data.settings); setStatus("Settings reset to safe defaults.");
    } catch (nextError) { setError(nextError); }
    finally { setBusy(false); }
  };

  if (!settings || !data) return <Box className="page-content"><Text>Loading local settings…</Text><ErrorAlert error={error} /></Box>;
  const setPaths = (patch: Partial<UiSettings["paths"]>) => setSettings({ ...settings, paths: { ...settings.paths, ...patch } });
  const setDisplay = (patch: Partial<UiSettings["display"]>) => setSettings({ ...settings, display: { ...settings.display, ...patch } });
  const setLogging = (patch: Partial<UiSettings["logging"]>) => setSettings({ ...settings, logging: { ...settings.logging, ...patch } });
  const effectiveLogs = settings.logging.directory || data.default_log_directory;

  return (
    <Box className="page-content">
      <Group justify="space-between" align="flex-start" mb="xl">
        <Box><Text className="eyebrow">Local application preferences</Text><Title order={1}>Settings</Title><Text c="dimmed">Stored separately from workflow TOML and used only by this local UI.</Text></Box>
        <Badge variant="light">Local only</Badge>
      </Group>
      <Stack gap="lg">
        {data.warning && <Alert color="yellow" icon={<IconAlertTriangle size={18} />} title="Settings file warning">{data.warning}</Alert>}
        <ErrorAlert error={error} />
        {status && <Alert color="green">{status}</Alert>}
        <Paper withBorder radius="lg" p="xl"><Title order={2} size="h3">Paths</Title><Stack mt="md">
          <PathPickerField label="Default working directory" selection="directory" value={settings.paths.default_working_directory} onChange={(value) => setPaths({ default_working_directory: value })} />
          <PathPickerField label="Path browser start directory" selection="directory" value={settings.paths.path_browser_start_directory} onChange={(value) => setPaths({ path_browser_start_directory: value })} />
          <Switch label="Remember last used input and output folders" description="Turning this off clears and stops using remembered folders." checked={settings.paths.remember_last_paths} onChange={(event) => setPaths(event.currentTarget.checked ? { remember_last_paths: true } : { remember_last_paths: false, last_input_directory: "", last_output_directory: "" })} />
          <Group grow><TextInput label="Last input directory" value={settings.paths.last_input_directory} onChange={(event) => setPaths({ last_input_directory: event.currentTarget.value })} /><TextInput label="Last output directory" value={settings.paths.last_output_directory} onChange={(event) => setPaths({ last_output_directory: event.currentTarget.value })} /></Group>
        </Stack></Paper>
        <Paper withBorder radius="lg" p="xl"><Title order={2} size="h3">Display</Title><Stack mt="md">
          <NumberInput label="Default table page size" description="Used by paginated tables; allowed range 5–500." min={5} max={500} value={settings.display.default_table_page_size} onChange={(value) => setDisplay({ default_table_page_size: Number(value) })} />
          <Switch label="Show equivalent CLI command previews" description="When disabled, command preview panels are hidden completely." checked={settings.display.show_command_preview} onChange={(event) => setDisplay({ show_command_preview: event.currentTarget.checked })} />
        </Stack></Paper>
        <Paper withBorder radius="lg" p="xl"><Group justify="space-between"><Title order={2} size="h3">Logging</Title><Badge color={settings.logging.enabled ? "green" : "gray"}>{settings.logging.enabled ? "Enabled" : "Disabled"}</Badge></Group><Stack mt="md">
          <Switch label="Enable logging for UI-run commands" checked={settings.logging.enabled} onChange={(event) => setLogging({ enabled: event.currentTarget.checked })} />
          <PathPickerField label="Logs directory" description={`Default: ${data.default_log_directory}`} selection="directory" value={settings.logging.directory} onChange={(value) => setLogging({ directory: value })} />
          <Select label="Log level" data={data.allowed_log_levels} value={settings.logging.level} onChange={(value) => value && setLogging({ level: value })} />
          <Text size="sm" c="dimmed">Existing CLI mapping</Text>
          <Code block>{settings.logging.enabled ? `--log "${effectiveLogs}\\<timestamp>_<workflow>_<job-id>.log" --log-level ${settings.logging.level}` : "No --log or --log-level options are applied."}</Code>
        </Stack></Paper>
        <Paper withBorder radius="lg" p="xl"><Title order={2} size="h3">Storage and diagnostics</Title><Stack mt="md" gap="xs">
          <Text size="sm"><strong>Settings file:</strong> {data.settings_file_path}</Text><Text size="sm"><strong>Config directory:</strong> {data.config_directory}</Text><Text size="sm"><strong>Default logs:</strong> {data.default_log_directory}</Text><Text size="sm"><strong>Platform:</strong> {data.platform}</Text>
          <Divider my="sm" /><Group><Button leftSection={<IconDeviceFloppy size={17} />} loading={busy} onClick={() => void save()}>Save settings</Button><Button variant="light" color="red" leftSection={<IconRefresh size={17} />} loading={busy} onClick={() => void reset()}>Reset settings</Button></Group>
        </Stack></Paper>
      </Stack>
    </Box>
  );
}
