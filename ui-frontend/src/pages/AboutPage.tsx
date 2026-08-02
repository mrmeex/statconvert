import { useEffect, useState } from "react";
import { Alert, Anchor, Badge, Box, Group, Paper, SimpleGrid, Stack, Table, Text, Title } from "@mantine/core";
import { IconLock, IconWorld } from "@tabler/icons-react";

import { ErrorAlert } from "../components/ErrorAlert";
import { getJson } from "../lib/api";
import type { AboutData, DataResponse } from "../lib/types";

export function AboutPage() {
  const [data, setData] = useState<AboutData | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => { void getJson<DataResponse<AboutData>>("/api/about").then((response) => setData(response.data)).catch(setError); }, []);
  if (!data) return <Box className="page-content"><Text>Loading runtime details…</Text><ErrorAlert error={error} /></Box>;
  return <Box className="page-content">
    <Group justify="space-between" align="flex-start" mb="xl"><Box><Text className="eyebrow">Product and runtime</Text><Title order={1}>About StatConvert</Title></Box><Badge variant="light">{data.version}</Badge></Group>
    <ErrorAlert error={error} />
    <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="lg">
      <Paper withBorder radius="lg" p="xl"><Title order={2} size="h3">StatConvert</Title><Stack mt="md" gap="xs"><Text><strong>Version:</strong> {data.version}</Text><Text><strong>UI mode:</strong> {data.ui_mode}</Text><Text><strong>License:</strong> {data.license}</Text><Text><strong>Python:</strong> {data.python_version}</Text><Text><strong>Platform:</strong> {data.platform}</Text></Stack></Paper>
      <Paper withBorder radius="lg" p="xl"><Group><IconLock size={22} /><Title order={2} size="h3">Local and private</Title></Group><Text mt="md">StatConvert UI runs on your machine. It does not upload files, use cloud processing, collect telemetry, create accounts, or expose a remote server. User-selected local paths are processed by the local Python process.</Text></Paper>
      <Paper withBorder radius="lg" p="xl"><Title order={2} size="h3">Runtime and network</Title><Stack mt="md" gap="xs"><Text><strong>Open URL:</strong> {data.open_url}</Text><Text><strong>Bound address:</strong> {data.bound_address}</Text><Text><strong>Static assets:</strong> {data.static_assets_present ? "available" : "missing"}</Text><Text size="sm" c="dimmed">statconvert.localhost is a browser-friendly alias for the loopback-only server.</Text></Stack></Paper>
      <Paper withBorder radius="lg" p="xl"><Group><IconWorld size={22} /><Title order={2} size="h3">Project links</Title></Group><Stack mt="md">{Object.entries(data.links).map(([name, url]) => <Anchor key={name} href={url} target="_blank" rel="noreferrer">{name === "product" ? "Product page" : name === "documentation" ? "Read the docs" : name === "github" ? "View on GitHub" : "Releases"}</Anchor>)}</Stack></Paper>
    </SimpleGrid>
    <Paper withBorder radius="lg" p="xl" mt="lg"><Title order={2} size="h3">Dependency versions</Title><Table mt="md" striped><Table.Tbody>{Object.entries(data.dependencies).map(([name, version]) => <Table.Tr key={name}><Table.Td fw={600}>{name}</Table.Td><Table.Td>{version}</Table.Td></Table.Tr>)}</Table.Tbody></Table></Paper>
  </Box>;
}
