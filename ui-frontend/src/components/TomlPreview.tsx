import { ActionIcon, Code, CopyButton, Group, Paper, Text, Tooltip } from "@mantine/core";
import { IconCheck, IconCopy } from "@tabler/icons-react";

export function TomlPreview({ toml }: { toml: string }) {
  if (!toml) return null;
  return <Paper withBorder radius="lg" p="md">
    <Group justify="space-between" mb="xs"><Text fw={700}>Canonical ordered TOML</Text><CopyButton value={toml}>{({ copied, copy }) => <Tooltip label={copied ? "Copied" : "Copy TOML"}><ActionIcon variant="subtle" onClick={copy} aria-label="Copy TOML">{copied ? <IconCheck size={17} /> : <IconCopy size={17} />}</ActionIcon></Tooltip>}</CopyButton></Group>
    <Code block className="toml-preview">{toml}</Code>
  </Paper>;
}
