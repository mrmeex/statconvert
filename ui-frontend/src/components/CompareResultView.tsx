import {
  Badge, Group, Paper, ScrollArea, SimpleGrid, Stack, Table,
  Text, Title,
} from "@mantine/core";
import type { ReactNode } from "react";

import { RawDetails } from "./RawDetails";

interface CompareResultViewProps {
  data: Record<string, unknown>;
}

type Row = Record<string, unknown>;

const text = (value: unknown): string => {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "None";
  if (typeof value === "object") return `${Object.keys(value as Row).length} fields`;
  return String(value);
};

const record = (value: unknown): Row =>
  typeof value === "object" && value !== null && !Array.isArray(value) ? value as Row : {};

function changeRows(section: Row, names: string[]): Row[] {
  return names.flatMap((name) => Object.entries(record(section[name])).map(([column, values]) => {
    const pair = Array.isArray(values) ? values : [values, null];
    return { difference: name.replaceAll("_", " "), column, left: pair[0], right: pair[1] };
  }));
}

function DataTable({ rows, empty }: { rows: Row[]; empty: string }) {
  if (!rows.length) return <Text size="sm" c="dimmed">{empty}</Text>;
  const columns = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
  return (
    <ScrollArea>
      <Table striped highlightOnHover className="result-table">
        <Table.Thead><Table.Tr>{columns.map((column) => <Table.Th key={column}>{column.replaceAll("_", " ")}</Table.Th>)}</Table.Tr></Table.Thead>
        <Table.Tbody>{rows.slice(0, 200).map((row, index) => <Table.Tr key={index}>{columns.map((column) => <Table.Td key={column}>{text(row[column])}</Table.Td>)}</Table.Tr>)}</Table.Tbody>
      </Table>
    </ScrollArea>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return <Paper withBorder radius="md" p="md"><Title order={4} mb="sm">{title}</Title>{children}</Paper>;
}

export function CompareResultView({ data }: CompareResultViewProps) {
  const comparison = record(data.comparison);
  const summary = record(comparison.summary);
  const shape = record(comparison.shape);
  const columns = record(comparison.columns);
  const schema = record(comparison.schema);
  const metadata = record(comparison.metadata);
  const values = record(comparison.values);
  const differences = Array.isArray(comparison.differences) ? comparison.differences as Row[] : [];
  const issues = Array.isArray(comparison.issues) ? comparison.issues as Row[] : [];
  const schemaRows = changeRows(schema, ["storage_type_changes", "display_format_changes", "measurement_level_changes"]);
  const metadataRows = changeRows(metadata, ["variable_label_changes", "value_label_changes", "missing_value_changes"]);
  const valueRows = differences.map((difference) => ({
    kind: difference.kind, row: difference.row, key: difference.key,
    column: difference.column, left: difference.left, right: difference.right,
    message: difference.message,
  }));

  return (
    <Paper withBorder radius="lg" p="lg">
      <Stack gap="md">
        <Group justify="space-between"><Title order={3}>Comparison result</Title><Badge color={data.is_identical ? "green" : data.has_errors ? "red" : "orange"}>{data.is_identical ? "Identical" : data.is_compatible ? "Compatible with differences" : "Not compatible"}</Badge></Group>
        <Section title="Comparison Summary">
          <SimpleGrid cols={{ base: 2, md: 4 }}>
            {["identical", "compatible", "errors", "warnings", "cells_compared", "cells_different", "detailed_differences_total", "report_path"].map((key) => (
              <div key={key}><Text size="xs" c="dimmed" tt="uppercase" fw={700}>{key.replaceAll("_", " ")}</Text><Text fw={600}>{text(key === "report_path" ? data.report_path : summary[key] ?? data[`is_${key}`])}</Text></div>
            ))}
          </SimpleGrid>
          {issues.length > 0 && <DataTable rows={issues} empty="No comparison issues." />}
        </Section>
        <Section title="Inputs"><DataTable rows={[{ side: "Left", source: comparison.left_source ?? summary.left_source }, { side: "Right", source: comparison.right_source ?? summary.right_source }]} empty="Input identifiers are unavailable." /></Section>
        <Section title="Shape"><DataTable rows={[{ metric: "Rows", left: shape.left_rows, right: shape.right_rows, match: shape.rows_match }, { metric: "Columns", left: shape.left_columns, right: shape.right_columns, match: shape.columns_match }]} empty="Shape details are unavailable." /></Section>
        <Section title="Columns"><DataTable rows={[{ metric: "Shared columns", value: columns.common_columns }, { metric: "Left only", value: columns.left_only_columns }, { metric: "Right only", value: columns.right_only_columns }, { metric: "Same order", value: columns.same_order }]} empty="Column details are unavailable." /></Section>
        <Section title="Schema"><DataTable rows={schemaRows} empty="No schema differences found." /></Section>
        <Section title="Metadata"><DataTable rows={metadataRows} empty="No metadata differences found." /></Section>
        <Section title="Values">
          <SimpleGrid cols={{ base: 2, md: 4 }} mb="sm">
            {["compared_rows", "compared_columns", "cells_compared", "differing_cells", "same_values", "sampled"].map((key) => <div key={key}><Text size="xs" c="dimmed" tt="uppercase" fw={700}>{key.replaceAll("_", " ")}</Text><Text fw={600}>{text(values[key])}</Text></div>)}
          </SimpleGrid>
          <DataTable rows={valueRows} empty={comparison.values ? "No bounded value differences found." : "Value comparison was skipped."} />
        </Section>
        <RawDetails data={data} />
      </Stack>
    </Paper>
  );
}
