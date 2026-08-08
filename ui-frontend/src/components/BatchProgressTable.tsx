import { Badge, Group, ScrollArea, Table, Text } from "@mantine/core";

import type { JobEvent } from "../lib/types";
import { jobStatusColor } from "../lib/status";

interface BatchRow { item_index: number; input_path: string; output_path?: string | null; status: string; message?: string | null }

export function BatchProgressTable({ events }: { events: JobEvent[] }) {
  const rows = new Map<number, BatchRow>();
  let completed = 0;
  let total = 0;
  for (const event of events) {
    if (event.kind === "batch_items_initialized") {
      total = Number(event.data.total ?? 0);
      for (const row of (event.data.items as BatchRow[] | undefined) ?? []) rows.set(row.item_index, { ...row });
    }
    if ((event.kind === "item_started" || event.kind === "item_finished") && typeof event.data.item_index === "number") {
      const index = event.data.item_index;
      const current = rows.get(index) ?? { item_index: index, input_path: String(event.data.input_path ?? ""), status: "queued" };
      rows.set(index, {
        ...current,
        output_path: String(event.data.output_path ?? current.output_path ?? "") || null,
        status: String(event.data.ui_status ?? current.status),
        message: String(event.data.message ?? event.message ?? current.message ?? "") || null,
      });
      completed = Number(event.data.completed ?? completed);
      total = Number(event.data.total ?? total);
    }
  }
  if (rows.size === 0) return null;
  const values = Array.from(rows.values());
  const failed = values.filter((row) => row.status === "failed").length;
  const current = values.find((row) => row.status === "running");
  return (
    <>
      <Group gap="lg" mt="md">
        <Text size="sm"><strong>{completed}</strong> / {total} complete</Text>
        <Text size="sm" c={failed ? "red" : "dimmed"}>{failed} failed</Text>
        {current && <Text size="sm" c="dimmed" truncate>Current: {current.input_path}</Text>}
      </Group>
      <ScrollArea mt="md">
        <Table striped highlightOnHover className="result-table">
          <Table.Thead><Table.Tr><Table.Th>Input</Table.Th><Table.Th>Output</Table.Th><Table.Th>Status</Table.Th><Table.Th>Message</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>{values.map((row) => (
            <Table.Tr key={row.item_index}>
              <Table.Td title={row.input_path}>{row.input_path}</Table.Td>
              <Table.Td title={row.output_path ?? ""}>{row.output_path ?? "—"}</Table.Td>
              <Table.Td><Badge variant="light" color={jobStatusColor(row.status)}>{row.status}</Badge></Table.Td>
              <Table.Td title={row.message ?? ""}>{row.message ?? "—"}</Table.Td>
            </Table.Tr>
          ))}</Table.Tbody>
        </Table>
      </ScrollArea>
    </>
  );
}
