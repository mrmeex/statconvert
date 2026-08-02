import {
  Box,
  Paper,
  ScrollArea,
  SimpleGrid,
  Table,
  Text,
  Title,
} from "@mantine/core";

import { RawDetails } from "./RawDetails";

interface ResultViewProps {
  data: Record<string, unknown> | null;
  title?: string;
  rawData?: unknown;
}

function valueText(value: unknown): string {
  if (value === null || value === undefined) {
    return "—";
  }
  if (Array.isArray(value)) {
    return value.length ? value.map(String).join(", ") : "None";
  }
  if (typeof value === "object") {
    return `${Object.keys(value as Record<string, unknown>).length} fields`;
  }
  return String(value);
}

function rowArray(data: Record<string, unknown>): Record<string, unknown>[] | null {
  const candidates = ["rows", "profiles", "columns", "items", "variables", "files"];
  for (const key of candidates) {
    const value = data[key];
    if (
      Array.isArray(value) &&
      value.every((item) => typeof item === "object" && item !== null)
    ) {
      return value as Record<string, unknown>[];
    }
  }
  return null;
}

export function ResultView({ data, title = "Result", rawData }: ResultViewProps) {
  if (!data) {
    return null;
  }
  if (Array.isArray(data.issues) && typeof data.passed === "boolean") {
    const issues = data.issues as Record<string, unknown>[];
    const summaryEntries = ["status", "error_count", "warning_count"]
      .filter((key) => key in data)
      .map((key) => [key, data[key]] as const);
    const issueColumns = ["severity", "code", "source_rule", "column", "message", "affected_rows", "expected", "actual"]
      .filter((key) => issues.some((issue) => key in issue));
    return (
      <Paper withBorder radius="lg" p="lg">
        <Title order={3} mb="md">{title}</Title>
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} mb="lg">
          <Box className="result-stat">
            <Text size="xs" c="dimmed" tt="uppercase" fw={700}>Result</Text>
            <Text fw={700} c={data.passed ? "green" : "red"}>{data.passed ? "Passed" : "Failed"}</Text>
          </Box>
          {summaryEntries.map(([key, value]) => (
            <Box key={key} className="result-stat">
              <Text size="xs" c="dimmed" tt="uppercase" fw={700}>{key.replaceAll("_", " ")}</Text>
              <Text fw={700}>{valueText(value)}</Text>
            </Box>
          ))}
        </SimpleGrid>
        <Title order={4} mb="xs">Validation issues</Title>
        {issues.length === 0 ? <Text c="green" size="sm">No validation issues found.</Text> : renderTableWithColumns(issues, issueColumns)}
        <RawDetails data={rawData ?? data} />
      </Paper>
    );
  }
  if (data.variable_labels && data.value_labels) {
    const variableLabels = Object.entries(data.variable_labels as Record<string, unknown>).map(([variable, label]) => ({ variable, label }));
    const valueLabels = Object.entries(data.value_labels as Record<string, unknown[]>).flatMap(([variable, values]) => values.map((item) => ({ variable, ...(item as Record<string, unknown>) })));
    return (
      <Paper withBorder radius="lg" p="lg">
        <Title order={3} mb="md">{title}</Title>
        <Title order={4} mb="xs">Variable labels</Title>
        {renderTable(variableLabels)}
        <Title order={4} mt="xl" mb="xs">Value labels</Title>
        {renderTable(valueLabels)}
        <RawDetails data={rawData ?? data} />
      </Paper>
    );
  }
  if (Array.isArray(data.tables)) {
    const frequencyRows = (data.tables as Record<string, unknown>[]).flatMap((table) =>
      ((table.items as Record<string, unknown>[]) ?? []).map((item) => ({
        variable: table.column,
        variable_label: table.label,
        ...item,
      })),
    );
    return (
      <Paper withBorder radius="lg" p="lg">
        <Title order={3} mb="md">{title}</Title>
        {renderTable(frequencyRows)}
        <RawDetails data={rawData ?? data} />
      </Paper>
    );
  }
  const rows = rowArray(data);
  if (rows && rows.length > 0) {
    const columns = Array.from(
      new Set(rows.flatMap((row) => Object.keys(row))),
    ).slice(0, 12);
    return (
      <Paper withBorder radius="lg" p="lg">
        <Title order={3} mb="md">
          {title}
        </Title>
        <ScrollArea>
          <Table striped highlightOnHover className="result-table">
            <Table.Thead>
              <Table.Tr>
                {columns.map((column) => (
                  <Table.Th key={column}>{column.replaceAll("_", " ")}</Table.Th>
                ))}
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rows.slice(0, 200).map((row, index) => (
                <Table.Tr key={index}>
                  {columns.map((column) => (
                    <Table.Td key={column}>{valueText(row[column])}</Table.Td>
                  ))}
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </ScrollArea>
        <RawDetails data={rawData ?? data} />
      </Paper>
    );
  }

  const scalarEntries = Object.entries(data).filter(([key, value]) => {
    if (["toml", "canonical_toml"].includes(key)) return false;
    if (typeof value === "string" && value.includes("\n")) return false;
    return typeof value !== "object" || value === null
      || (Array.isArray(value) && value.every((item) => typeof item !== "object" || item === null));
  });
  return (
    <Paper withBorder radius="lg" p="lg">
      <Title order={3} mb="md">
        {title}
      </Title>
      {scalarEntries.length > 0 && (
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} mb="lg">
          {scalarEntries.map(([key, value]) => (
            <Box key={key} className="result-stat">
              <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
                {key.replaceAll("_", " ")}
              </Text>
              <Text fw={700}>{valueText(value)}</Text>
            </Box>
          ))}
        </SimpleGrid>
      )}
      {scalarEntries.length === 0 && <Text size="sm" c="dimmed">No summary fields are available.</Text>}
      <RawDetails data={rawData ?? data} />
    </Paper>
  );
}

function renderTable(rows: Record<string, unknown>[]) {
  if (rows.length === 0) return <Text c="dimmed" size="sm">No rows to display.</Text>;
  const columns = Array.from(new Set(rows.flatMap((row) => Object.keys(row)))).slice(0, 12);
  return (
    <ScrollArea>
      <Table striped highlightOnHover className="result-table">
        <Table.Thead><Table.Tr>{columns.map((column) => <Table.Th key={column}>{column.replaceAll("_", " ")}</Table.Th>)}</Table.Tr></Table.Thead>
        <Table.Tbody>{rows.slice(0, 500).map((row, index) => <Table.Tr key={index}>{columns.map((column) => <Table.Td key={column}>{valueText(row[column])}</Table.Td>)}</Table.Tr>)}</Table.Tbody>
      </Table>
    </ScrollArea>
  );
}

function renderTableWithColumns(rows: Record<string, unknown>[], columns: string[]) {
  if (rows.length === 0) return <Text c="dimmed" size="sm">No rows to display.</Text>;
  return (
    <ScrollArea>
      <Table striped highlightOnHover className="result-table">
        <Table.Thead><Table.Tr>{columns.map((column) => <Table.Th key={column}>{column.replaceAll("_", " ")}</Table.Th>)}</Table.Tr></Table.Thead>
        <Table.Tbody>{rows.slice(0, 500).map((row, index) => <Table.Tr key={index}>{columns.map((column) => <Table.Td key={column}>{valueText(row[column])}</Table.Td>)}</Table.Tr>)}</Table.Tbody>
      </Table>
    </ScrollArea>
  );
}
