import {
  Badge, Box, Group, Paper, ScrollArea, SimpleGrid, Table, Text, Title,
} from "@mantine/core";

import { RawDetails } from "./RawDetails";
import { jobStatusColor } from "../lib/status";

interface BatchResultViewProps {
  data: Record<string, unknown>;
  title: string;
}

function record(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function display(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return Object.entries(record(value))
    .map(([key, count]) => `${key}: ${String(count)}`).join(", ") || "—";
  return String(value);
}

export function BatchResultView({ data, title }: BatchResultViewProps) {
  const counts = record(data.counts ?? data.summary);
  const rows = Array.isArray(data.items)
    ? data.items.filter((item): item is Record<string, unknown> =>
      typeof item === "object" && item !== null && !Array.isArray(item))
    : [];
  const truncation = record(data.truncation);
  const omitted = Number(truncation.items_omitted ?? 0);
  const columns = [
    ["input_file", "Input"], ["output_file", "Output"], ["status", "Status"],
    ["read_state", "Read"], ["rows", "Rows"], ["columns", "Columns"],
    ["recipe_compatibility_status", "Recipe"], ["policy_status", "Policy"],
    ["optimization_applied_count", "Optimized"], ["optimization_kept_count", "Kept"],
    ["optimization_manual_count", "Manual"], ["reason", "Warning / error"],
  ] as const;

  return (
    <Paper withBorder radius="lg" p="lg">
      <Group justify="space-between" mb="md">
        <Title order={3}>{title}</Title>
        <Badge variant="light">{display(data.phase ?? data.mode ?? "execution")}</Badge>
      </Group>
      <SimpleGrid cols={{ base: 2, sm: 3, lg: 6 }} mb="lg">
        {Object.entries(counts)
          .filter(([key, value]) => ["total", "pending", "success", "failed", "skipped", "blocked"].includes(key) && typeof value !== "object")
          .map(([key, value]) => (
            <Box className="result-stat" key={key}>
              <Text size="xs" c="dimmed" tt="uppercase" fw={700}>{key}</Text>
              <Text fw={700}>{display(value)}</Text>
            </Box>
          ))}
      </SimpleGrid>
      {Array.isArray(data.checks_not_performed) && data.checks_not_performed.length > 0 && (
        <Text size="sm" c="dimmed" mb="md">
          Not checked: {data.checks_not_performed.map(String).join("; ")}.
        </Text>
      )}
      <ScrollArea>
        <Table striped highlightOnHover className="result-table">
          <Table.Thead><Table.Tr>{columns.map(([, label]) => <Table.Th key={label}>{label}</Table.Th>)}</Table.Tr></Table.Thead>
          <Table.Tbody>{rows.map((row, index) => (
            <Table.Tr key={`${String(row.input_file ?? "item")}-${index}`}>
              {columns.map(([key]) => (
                <Table.Td key={key} title={display(row[key])}>
                  {key === "status"
                    ? <Badge variant="light" color={jobStatusColor(display(row[key]))}>{display(row[key])}</Badge>
                    : display(row[key])}
                </Table.Td>
              ))}
            </Table.Tr>
          ))}</Table.Tbody>
        </Table>
      </ScrollArea>
      {omitted > 0 && <Text size="sm" c="dimmed" mt="sm">{omitted} additional items omitted from this bounded view.</Text>}
      <RawDetails data={data} />
    </Paper>
  );
}
