import {
  Accordion,
  Box,
  Paper,
  ScrollArea,
  SimpleGrid,
  Table,
  Text,
  Title,
} from "@mantine/core";

import { ResultView } from "./ResultView";
import { RawDetails } from "./RawDetails";

interface InspectResultViewProps {
  tab: string;
  data: Record<string, unknown> | null;
  title: string;
}

interface TableColumn {
  key: string;
  label: string;
}

function asRows(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
    : [];
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return `${Object.keys(value as Record<string, unknown>).length} fields`;
  return String(value);
}

function DataTable({ rows, columns, empty }: { rows: Record<string, unknown>[]; columns: TableColumn[]; empty: string }) {
  if (rows.length === 0) return <Text c="dimmed" size="sm">{empty}</Text>;
  return (
    <ScrollArea>
      <Table striped highlightOnHover className="result-table">
        <Table.Thead><Table.Tr>{columns.map((column) => <Table.Th key={column.key}>{column.label}</Table.Th>)}</Table.Tr></Table.Thead>
        <Table.Tbody>
          {rows.slice(0, 500).map((row, index) => (
            <Table.Tr key={index}>{columns.map((column) => <Table.Td key={column.key}>{displayValue(row[column.key])}</Table.Td>)}</Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </ScrollArea>
  );
}

function StatCards({ entries }: { entries: Array<[string, unknown]> }) {
  return (
    <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} mb="lg">
      {entries.map(([label, value]) => (
        <Box key={label} className="result-stat">
          <Text size="xs" c="dimmed" tt="uppercase" fw={700}>{label}</Text>
          <Text fw={700}>{displayValue(value)}</Text>
        </Box>
      ))}
    </SimpleGrid>
  );
}

function OverviewResult({ data, title }: { data: Record<string, unknown>; title: string }) {
  const columns = asRows(data.column_details);
  const scalarEntries = Object.entries(data)
    .filter(([key, value]) => key !== "column_details" && key !== "metadata" && (typeof value !== "object" || value === null))
    .map(([key, value]) => [key.replaceAll("_", " "), value] as [string, unknown]);
  return (
    <Paper withBorder radius="lg" p="lg">
      <Title order={3} mb="md">{title}</Title>
      <StatCards entries={scalarEntries} />
      <Title order={4} mb="xs">Columns</Title>
      <DataTable
        rows={columns}
        columns={[{ key: "name", label: "Column" }, { key: "storage_type", label: "Type" }, { key: "label", label: "Label" }]}
        empty="This dataset has no columns."
      />
      <RawDetails data={data} />
    </Paper>
  );
}

function MetadataResult({ data, title }: { data: Record<string, unknown>; title: string }) {
  const dataset = (data.dataset ?? {}) as Record<string, unknown>;
  const summary = (data.summary ?? {}) as Record<string, unknown>;
  const notes = Array.isArray(dataset.notes) ? dataset.notes : [];
  const entries: Array<[string, unknown]> = [
    ["Source format", dataset.source_format],
    ["Source backend", dataset.source_backend],
    ["Dataset label", dataset.dataset_label],
    ["Notes", notes.length],
    ["Metadata source", dataset.metadata_source],
    ["Column sources", dataset.column_sources],
    ...Object.entries(summary).map(([key, value]) => [key.replaceAll("_", " "), value] as [string, unknown]),
  ];
  const variables = asRows(data.variables).map((variable) => ({
    ...variable,
    value_label_count: Array.isArray(variable.value_labels) ? variable.value_labels.length : 0,
  }));
  return (
    <Paper withBorder radius="lg" p="lg">
      <Title order={3} mb="md">{title}</Title>
      <Title order={4} mb="xs">Metadata summary</Title>
      <StatCards entries={entries} />
      {notes.length > 0 && <Text size="sm" mb="lg"><Text span fw={700}>Notes: </Text>{notes.map(String).join(" | ")}</Text>}
      <Title order={4} mb="xs">Variables</Title>
      <DataTable
        rows={variables}
        columns={[
          { key: "name", label: "Variable" }, { key: "label", label: "Label" },
          { key: "storage_type", label: "Type" }, { key: "display_format", label: "Format" },
          { key: "measure", label: "Measure" }, { key: "role", label: "Role" },
          { key: "value_label_count", label: "Value labels" },
        ]}
        empty="No normalized variable metadata is available."
      />
      <RawDetails data={data} />
    </Paper>
  );
}

export function formatMemoryUsage(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "Not available";
  const megabytes = value / (1024 * 1024);
  if (megabytes < 100) return `${megabytes.toFixed(1)} MB`;
  return `${(megabytes / 1024).toFixed(1)} GB`;
}

function SummaryResult({ data, title }: { data: Record<string, unknown>; title: string }) {
  const entries = Object.entries(data).map(([key, value]) => [
    key === "memory_usage_bytes" ? "Memory usage" : key.replaceAll("_", " "),
    key === "memory_usage_bytes" ? formatMemoryUsage(value) : value,
  ] as [string, unknown]);
  return <Paper withBorder radius="lg" p="lg"><Title order={3} mb="md">{title}</Title><StatCards entries={entries} /></Paper>;
}

function DescribeResult({ data, title }: { data: Record<string, unknown>; title: string }) {
  const sections: Array<{ title: string; rows: Record<string, unknown>[]; columns: TableColumn[]; empty: string }> = [
    {
      title: "Column profiles", rows: asRows(data.column_profiles), empty: "No column profiles to display.",
      columns: [
        { key: "name", label: "Column" }, { key: "storage_type", label: "Type" }, { key: "label", label: "Label" },
        { key: "profile_type", label: "Profile" }, { key: "non_missing_count", label: "Non-missing" },
        { key: "missing_count", label: "Missing" }, { key: "missing_percent", label: "Missing %" }, { key: "unique_count", label: "Unique" },
      ],
    },
    {
      title: "Numeric statistics", rows: asRows(data.numeric_statistics), empty: "No numeric columns are present.",
      columns: [
        { key: "column", label: "Column" }, { key: "mean", label: "Mean" }, { key: "std", label: "Std dev" },
        { key: "min", label: "Min" }, { key: "q1", label: "Q1" }, { key: "median", label: "Median" },
        { key: "q3", label: "Q3" }, { key: "max", label: "Max" },
      ],
    },
    {
      title: "Categorical statistics", rows: asRows(data.categorical_statistics), empty: "No categorical columns are present.",
      columns: [
        { key: "column", label: "Column" }, { key: "top_value", label: "Top value" }, { key: "top_label", label: "Top label" },
        { key: "top_count", label: "Top count" }, { key: "top_percent", label: "Top %" }, { key: "unique_count", label: "Unique" },
      ],
    },
  ];
  return (
    <Paper withBorder radius="lg" p="lg">
      <Title order={3} mb="md">{title}</Title>
      {sections.map((section, index) => <Box key={section.title} mt={index ? "xl" : 0}><Title order={4} mb="xs">{section.title}</Title><DataTable {...section} /></Box>)}
    </Paper>
  );
}

function FrequenciesResult({ data, title }: { data: Record<string, unknown>; title: string }) {
  const tables = asRows(data.tables);
  return (
    <Paper withBorder radius="lg" p="lg">
      <Title order={3} mb="md">{title}</Title>
      {tables.length === 0 ? <Text c="dimmed" size="sm">No frequency tables are available.</Text> : (
        <Accordion multiple variant="separated" defaultValue={tables.slice(0, 3).map((_, index) => String(index))}>
          {tables.map((table, index) => (
            <Accordion.Item key={`${displayValue(table.column)}-${index}`} value={String(index)}>
              <Accordion.Control>{displayValue(table.column)}{table.label ? ` — ${displayValue(table.label)}` : ""}</Accordion.Control>
              <Accordion.Panel>
                <Text size="xs" c="dimmed" mb="xs">Total: {displayValue(table.total_count)} · Missing/null: {displayValue(table.missing_count)}</Text>
                <DataTable
                  rows={asRows(table.items).map((item) => ({ ...item, value: item.value === null ? "Missing / null" : item.value }))}
                  columns={[{ key: "value", label: "Value" }, { key: "label", label: "Label" }, { key: "count", label: "Count" }, { key: "percent", label: "Percent" }]}
                  empty="No values are available for this variable."
                />
              </Accordion.Panel>
            </Accordion.Item>
          ))}
        </Accordion>
      )}
    </Paper>
  );
}

function MissingResult({ data, title }: { data: Record<string, unknown>; title: string }) {
  return (
    <Paper withBorder radius="lg" p="lg">
      <Title order={3} mb="md">{title}</Title>
      <DataTable
        rows={asRows(data.profiles)}
        columns={[
          { key: "column", label: "Column" }, { key: "label", label: "Label" },
          { key: "missing_count", label: "Missing" }, { key: "missing_percent", label: "Missing %" },
          { key: "metadata_missing_values", label: "Metadata missing values" },
        ]}
        empty="No missing-value profiles are available."
      />
    </Paper>
  );
}

export function InspectResultView({ tab, data, title }: InspectResultViewProps) {
  if (!data) return null;
  if (tab === "info") return <OverviewResult data={data} title={title} />;
  if (tab === "metadata") return <MetadataResult data={data} title={title} />;
  if (tab === "summary") return <SummaryResult data={data} title={title} />;
  if (tab === "describe") return <DescribeResult data={data} title={title} />;
  if (tab === "frequencies") return <FrequenciesResult data={data} title={title} />;
  if (tab === "missing") return <MissingResult data={data} title={title} />;
  return <ResultView data={data} title={title} />;
}
