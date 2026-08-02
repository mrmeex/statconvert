import { useEffect, useRef, useState } from "react";
import { Alert, Badge, Button, Group, Select, Stack, Text, Textarea } from "@mantine/core";
import { IconBraces, IconColumns, IconInfoCircle } from "@tabler/icons-react";

import { postJson } from "../lib/api";
import type { ExpressionValidationResponse } from "../lib/types";
import { FunctionPicker } from "./FunctionPicker";

interface ExpressionEditorProps {
  value: string;
  onChange: (value: string) => void;
  purpose: "derive" | "filter";
  columns: string[];
}

function columnReference(column: string): string {
  return /^[A-Za-z_][A-Za-z0-9_]*$/.test(column) ? column : `[${column}]`;
}

export function ExpressionEditor({ value, onChange, purpose, columns }: ExpressionEditorProps) {
  const textarea = useRef<HTMLTextAreaElement>(null);
  const [column, setColumn] = useState<string | null>(null);
  const [pickerOpened, setPickerOpened] = useState(false);
  const [analysis, setAnalysis] = useState<ExpressionValidationResponse["data"] | null>(null);

  useEffect(() => {
    if (!value.trim()) { setAnalysis(null); return; }
    let active = true;
    const timer = window.setTimeout(() => {
      void postJson<ExpressionValidationResponse>("/api/transform/validate-expression", { expression: value, purpose })
        .then((response) => { if (active) setAnalysis(response.data); })
        .catch(() => { if (active) setAnalysis(null); });
    }, 300);
    return () => { active = false; window.clearTimeout(timer); };
  }, [purpose, value]);

  const insert = (text: string) => {
    const element = textarea.current;
    const start = element?.selectionStart ?? value.length;
    const end = element?.selectionEnd ?? start;
    onChange(`${value.slice(0, start)}${text}${value.slice(end)}`);
    window.setTimeout(() => {
      element?.focus();
      element?.setSelectionRange(start + text.length, start + text.length);
    }, 0);
  };

  return (
    <Stack gap="xs">
      <Textarea ref={textarea} label={purpose === "derive" ? "Expression" : "Filter expression"} autosize minRows={3} maxRows={8} value={value} onChange={(event) => onChange(event.currentTarget.value)} placeholder={purpose === "derive" ? "lower(strip(name))" : "age >= 18 and status == 'A'"} />
      <Group align="end" gap="xs">
        <Select label="Projected input column" placeholder="Choose column" searchable data={columns} value={column} onChange={setColumn} style={{ flex: 1 }} />
        <Button variant="light" leftSection={<IconColumns size={16} />} disabled={!column} onClick={() => column && insert(columnReference(column))}>Insert column</Button>
        <Button variant="light" leftSection={<IconBraces size={16} />} onClick={() => setPickerOpened(true)}>Functions</Button>
        {value.trim() && <Badge color={analysis?.valid ? "green" : analysis ? "red" : "gray"}>{analysis?.valid ? `${analysis.result_kind} · valid` : analysis ? "invalid" : "checking"}</Badge>}
      </Group>
      {analysis?.errors.map((issue) => (
        <Alert key={`${issue.code}-${issue.start}`} color="red" icon={<IconInfoCircle size={16} />} py="xs">
          <Text size="sm">{issue.message} <Text component="span" ff="monospace">[{issue.start}:{issue.end})</Text></Text>
        </Alert>
      ))}
      <FunctionPicker opened={pickerOpened} onClose={() => setPickerOpened(false)} purpose={purpose} onInsert={insert} />
    </Stack>
  );
}
