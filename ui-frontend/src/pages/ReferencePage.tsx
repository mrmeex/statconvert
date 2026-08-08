import { useEffect, useMemo, useState } from "react";
import { Badge, Box, Group, Paper, ScrollArea, Stack, Table, Tabs, Text, TextInput } from "@mantine/core";
import { IconDatabase, IconSearch, IconServer, IconTableOptions } from "@tabler/icons-react";

import { CommandPreview } from "../components/CommandPreview";
import { ErrorAlert } from "../components/ErrorAlert";
import { WorkflowHeader } from "../components/WorkflowHeader";
import { getJson } from "../lib/api";
import type { DataResponse, ReferenceData } from "../lib/types";

type ReferenceKind = "formats" | "backends" | "capabilities";

const columns: Record<ReferenceKind, string[]> = {
  formats: ["extension", "name", "backend", "can_read", "can_write", "object_selection", "multi_object_write"],
  backends: ["backend", "implementation", "can_read", "can_write", "supports_streaming", "supports_custom_metadata", "object_selection"],
  capabilities: ["extension", "format", "backend", "can_read", "can_write", "object_selection", "multi_object_write", "supports_streaming", "supports_variable_labels", "supports_value_labels"],
};

function cell(value: unknown) {
  if (typeof value === "boolean") return <Badge color={value ? "green" : "gray"} variant="light">{value ? "Yes" : "No"}</Badge>;
  if (value === null || value === undefined || value === "") return <Text c="dimmed">—</Text>;
  return String(value);
}

export function ReferencePage() {
  const [active, setActive] = useState<ReferenceKind>("formats");
  const [datasets, setDatasets] = useState<Partial<Record<ReferenceKind, ReferenceData>>>({});
  const [search, setSearch] = useState("");
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all((["formats", "backends", "capabilities"] as ReferenceKind[]).map(async (kind) => {
      const response = await getJson<DataResponse<ReferenceData>>(`/api/reference/${kind}`);
      return [kind, response.data] as const;
    })).then((entries) => {
      if (!cancelled) setDatasets(Object.fromEntries(entries) as Record<ReferenceKind, ReferenceData>);
    }).catch((nextError) => { if (!cancelled) setError(nextError); });
    return () => { cancelled = true; };
  }, []);

  const current = datasets[active];
  const rows = useMemo(() => (current?.rows ?? []).filter((row) => JSON.stringify(row).toLowerCase().includes(search.toLowerCase())), [current, search]);
  return (
    <Box className="page-content">
      <WorkflowHeader title="Reference" description="Browse the live format, backend, and capability registries used by StatConvert." />
      <Stack gap="lg">
        <ErrorAlert error={error} />
        <Paper withBorder radius="lg" p="lg">
          <Tabs value={active} onChange={(value) => setActive((value ?? "formats") as ReferenceKind)}>
            <Group justify="space-between" align="end" mb="md">
              <Tabs.List><Tabs.Tab value="formats" leftSection={<IconDatabase size={16} />}>Formats</Tabs.Tab><Tabs.Tab value="backends" leftSection={<IconServer size={16} />}>Backends</Tabs.Tab><Tabs.Tab value="capabilities" leftSection={<IconTableOptions size={16} />}>Capabilities</Tabs.Tab></Tabs.List>
              <TextInput aria-label="Search reference" placeholder="Search registry" leftSection={<IconSearch size={16} />} value={search} onChange={(event) => setSearch(event.currentTarget.value)} />
            </Group>
            {(["formats", "backends", "capabilities"] as ReferenceKind[]).map((kind) => <Tabs.Panel value={kind} key={kind}>
              <Group justify="space-between" mb="sm"><Text size="sm" c="dimmed">{rows.length} of {datasets[kind]?.count ?? 0} records</Text></Group>
              <ScrollArea><Table striped highlightOnHover className="result-table"><Table.Thead><Table.Tr>{columns[kind].map((column) => <Table.Th key={column}>{column.replaceAll("_", " ")}</Table.Th>)}</Table.Tr></Table.Thead><Table.Tbody>{rows.map((row, index) => <Table.Tr key={index}>{columns[kind].map((column) => <Table.Td key={column}>{cell(row[column])}</Table.Td>)}</Table.Tr>)}</Table.Tbody></Table></ScrollArea>
              {rows.length === 0 && <Text ta="center" c="dimmed" py="xl">No registry records match this search.</Text>}
            </Tabs.Panel>)}
          </Tabs>
        </Paper>
        {current && <CommandPreview command={current.command} />}
      </Stack>
    </Box>
  );
}
