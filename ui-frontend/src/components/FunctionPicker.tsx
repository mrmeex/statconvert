import { useEffect, useMemo, useState } from "react";
import {
  Badge, Button, Card, Drawer, Group, Loader, ScrollArea, Select, Stack,
  Text, TextInput,
} from "@mantine/core";
import { IconBraces, IconSearch } from "@tabler/icons-react";

import type { ExpressionFunction, TransformFunctionResponse } from "../lib/types";
import { ErrorAlert } from "./ErrorAlert";

interface FunctionPickerProps {
  opened: boolean;
  onClose: () => void;
  purpose: "derive" | "filter";
  onInsert: (value: string) => void;
}

let cachedFunctions: ExpressionFunction[] | null = null;

function insertion(functionSpec: ExpressionFunction): string {
  const names = functionSpec.arguments.map((argument) => argument.name);
  while (names.length < functionSpec.minimum_arguments) {
    names.push(names.length === 0 ? "value" : `value${names.length + 1}`);
  }
  const argumentsText = names.join(", ");
  return `${functionSpec.name}(${argumentsText})`;
}

export function FunctionPicker({ opened, onClose, purpose, onInsert }: FunctionPickerProps) {
  const [functions, setFunctions] = useState<ExpressionFunction[]>(cachedFunctions ?? []);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string | null>(null);
  const [loading, setLoading] = useState(!cachedFunctions);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (!opened || cachedFunctions) return;
    setLoading(true);
    void fetch("/api/transform/functions", { headers: { Accept: "application/json" } })
      .then(async (response) => {
        if (!response.ok) throw new Error("Unable to load transform functions.");
        return response.json() as Promise<TransformFunctionResponse>;
      })
      .then((response) => { cachedFunctions = response.data.functions; setFunctions(response.data.functions); setError(null); })
      .catch(setError)
      .finally(() => setLoading(false));
  }, [opened]);

  const categories = useMemo(() => Array.from(new Set(functions.map((item) => item.category))).sort(), [functions]);
  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return functions.filter((item) => {
      const suitable = purpose === "derive" ? item.derive_allowed : item.filter_suitability !== "unsupported";
      return suitable && (!category || item.category === category) && (!needle || `${item.name} ${item.description ?? ""} ${item.signature ?? ""}`.toLowerCase().includes(needle));
    });
  }, [category, functions, purpose, query]);

  return (
    <Drawer opened={opened} onClose={onClose} position="right" size="lg" title={`Function picker · ${functions.length || 43} active helpers`}>
      <Stack h="calc(100vh - 100px)">
        <Group grow align="start">
          <TextInput leftSection={<IconSearch size={16} />} placeholder="Search name or description" value={query} onChange={(event) => setQuery(event.currentTarget.value)} />
          <Select clearable placeholder="All categories" data={categories} value={category} onChange={setCategory} />
        </Group>
        <ErrorAlert error={error} />
        {loading ? <Loader /> : (
          <ScrollArea style={{ flex: 1 }}>
            <Stack gap="sm" pr="sm">
              {visible.map((item) => (
                <Card key={item.name} withBorder radius="md" p="md">
                  <Group justify="space-between" align="start">
                    <div>
                      <Text fw={700} ff="monospace">{item.signature ?? `${item.name}(…)`}</Text>
                      <Group gap="xs" mt={6}><Badge variant="light">{item.category.replaceAll("_", " ")}</Badge><Badge variant="outline">→ {item.return_type}</Badge></Group>
                    </div>
                    <Button size="xs" leftSection={<IconBraces size={15} />} onClick={() => { onInsert(insertion(item)); onClose(); }}>Insert</Button>
                  </Group>
                  {item.description && <Text size="sm" c="dimmed" mt="sm">{item.description}</Text>}
                  {item.arguments.length > 0 && <Text size="xs" mt="sm"><strong>Arguments:</strong> {item.arguments.map((argument) => `${argument.name}: ${argument.accepted_types.join("/")}`).join("; ")}</Text>}
                  {item.examples[0] && <Text size="xs" ff="monospace" mt="xs">{item.examples[0]}</Text>}
                  {item.null_behavior && <Text size="xs" c="dimmed" mt="xs"><strong>Nulls:</strong> {item.null_behavior}</Text>}
                  {item.error_behavior && <Text size="xs" c="dimmed"><strong>Errors:</strong> {item.error_behavior}</Text>}
                </Card>
              ))}
            </Stack>
          </ScrollArea>
        )}
      </Stack>
    </Drawer>
  );
}
