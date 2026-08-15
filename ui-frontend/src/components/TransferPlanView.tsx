import {
  Badge,
  Box,
  Paper,
  ScrollArea,
  SimpleGrid,
  Table,
  Text,
  Title,
} from "@mantine/core";

import { RawDetails } from "./RawDetails";

interface TransferPlanViewProps {
  plan: Record<string, unknown> | null;
}

const records = (value: unknown): Record<string, unknown>[] =>
  Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
    : [];

const object = (value: unknown): Record<string, unknown> =>
  typeof value === "object" && value !== null ? value as Record<string, unknown> : {};

const text = (value: unknown): string => {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
};

export function TransferPlanView({ plan }: TransferPlanViewProps) {
  if (!plan) return null;
  const summary = object(plan.summary);
  const target = object(plan.target);
  const truncated = object(plan.truncated);
  const decisions = records(plan.decisions).filter((decision) => decision.action !== "keep");
  const issues = records(plan.issues);
  const status = text(plan.status);
  const statusColor = status === "blocked" ? "red" : status === "warnings" ? "yellow" : "green";
  const metrics = [
    ["Policy", plan.policy],
    ["Target", `${text(target.format)} (${text(target.extension)})`],
    ["Status", plan.status],
    ["Changed / proposed", summary.changed_proposed_count],
    ["Manual", summary.manual_count],
    ["Unchanged", summary.unchanged_count],
    ["Warnings", summary.warning_count],
    ["Errors", summary.error_count],
    ["Metadata disposition", summary.metadata_disposition_counts],
    ["Sidecar requirements", object(summary.metadata_disposition_counts).sidecar ?? 0],
  ] as const;

  return (
    <Paper withBorder radius="lg" p="lg">
      <Title order={3} mb="md">Transfer plan</Title>
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 5 }} mb="lg">
        {metrics.map(([label, value]) => (
          <Box className="result-stat" key={label}>
            <Text size="xs" c="dimmed" tt="uppercase" fw={700}>{label}</Text>
            {label === "Status"
              ? <Badge color={statusColor} variant="light">{status}</Badge>
              : <Text fw={700}>{text(value)}</Text>}
          </Box>
        ))}
      </SimpleGrid>

      <Title order={4} mb="xs">Changed and manual decisions</Title>
      {decisions.length === 0 ? <Text size="sm" c="dimmed">No changed or manual decisions.</Text> : (
        <ScrollArea>
          <Table striped highlightOnHover className="result-table">
            <Table.Thead><Table.Tr>{["column", "current_storage_type", "proposed_storage_type", "action", "reason_code", "evidence_level"].map((column) => <Table.Th key={column}>{column.replaceAll("_", " ")}</Table.Th>)}</Table.Tr></Table.Thead>
            <Table.Tbody>{decisions.map((decision, index) => <Table.Tr key={`${text(decision.column)}-${index}`}>{["column", "current_storage_type", "proposed_storage_type", "action", "reason_code", "evidence_level"].map((column) => <Table.Td key={column}>{text(decision[column])}</Table.Td>)}</Table.Tr>)}</Table.Tbody>
          </Table>
        </ScrollArea>
      )}

      <Title order={4} mt="xl" mb="xs">Transfer findings</Title>
      {issues.length === 0 ? <Text size="sm" c="green">No transfer findings.</Text> : (
        <ScrollArea>
          <Table striped highlightOnHover className="result-table">
            <Table.Thead><Table.Tr>{["severity", "code", "column", "field", "message"].map((column) => <Table.Th key={column}>{column}</Table.Th>)}</Table.Tr></Table.Thead>
            <Table.Tbody>{issues.map((issue, index) => <Table.Tr key={`${text(issue.code)}-${index}`}>{["severity", "code", "column", "field", "message"].map((column) => <Table.Td key={column}>{text(issue[column])}</Table.Td>)}</Table.Tr>)}</Table.Tbody>
          </Table>
        </ScrollArea>
      )}
      {Boolean(truncated.decisions || truncated.issues || truncated.metadata) && (
        <Text size="xs" c="dimmed" mt="sm">Detailed output is bounded; omitted counts are available in Raw details.</Text>
      )}
      <RawDetails data={plan} />
    </Paper>
  );
}
